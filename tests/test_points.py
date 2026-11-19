"""Exercise lesson points through booking, confirmation, cancellation and upgrades."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
import sqlite3
from threading import Barrier, local
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import create_app, db
from app.lessons import confirm_lesson, existing_booking, schedule_lesson
from app.models import Category, Lesson, Listing, Skill, User


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def add_people(app, learner_id):
    with app.app_context():
        teacher = User(username="points-teacher", email="teacher@example.test")
        outsider = User(username="points-outsider", email="outsider@example.test")
        for user in (teacher, outsider):
            user.set_password("secret-password")
        category = Category(name="Points test skills")
        skill = Skill(name="Piano", category=category)
        db.session.add_all([teacher, outsider, skill])
        db.session.flush()
        db.session.add(Listing(user_id=teacher.id, skill_id=skill.id, type="teach"))
        db.session.commit()
        return {"learner": learner_id, "teacher": teacher.id,
                "outsider": outsider.id, "skill": skill.id}


@pytest.fixture
def people(app, user_id):
    return add_people(app, user_id)


def signed_in_client(app, username):
    client = app.test_client()
    response = client.post("/login", data={"username": username, "password": "secret-password"})
    assert response.status_code == 302
    return client


def lesson_post(client, path, data=None):
    assert client.get("/lessons").status_code == 200
    with client.session_transaction() as session:
        token = session["lesson_form_token"]
    return client.post(path, data={**(data or {}), "lesson_form_token": token})


def balances(app, people):
    with app.app_context():
        return {
            role: (user.points, user.reserved_points, user.available_points)
            for role in ("learner", "teacher", "outsider")
            for user in [db.session.get(User, people[role])]
        }


def book(client, people, **overrides):
    values = {
        "skill_id": str(people["skill"]),
        "scheduled_at": (now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
        "booking_key": str(uuid4()),
    }
    values.update(overrides)
    return lesson_post(client, f"/lessons/book/{people['teacher']}", data=values)


def booked_lesson(app, client, people, *, past=False):
    assert book(client, people).status_code == 302
    with app.app_context():
        lesson = db.session.execute(db.select(Lesson)).scalar_one()
        if past:
            lesson.scheduled_at = now() - timedelta(hours=1)
            db.session.commit()
        return lesson.id


def test_signup_starts_with_three_points_and_balance_is_visible(client, app, user_data):
    response = client.post("/signup", data=user_data)
    assert response.status_code == 302
    with app.app_context():
        user = db.session.execute(db.select(User)).scalar_one()
        assert (user.points, user.reserved_points, user.available_points) == (3, 0, 3)
    response = client.get("/lessons")
    assert response.status_code == 200
    assert "3 points" in response.get_data(as_text=True)


def test_booking_reserves_one_point_without_transferring_it(app, authenticated_client, people):
    lesson_id = booked_lesson(app, authenticated_client, people)
    assert balances(app, people) == {
        "learner": (3, 1, 2), "teacher": (3, 0, 3), "outsider": (3, 0, 3)
    }
    with app.app_context():
        lesson = db.session.get(Lesson, lesson_id)
        assert lesson.status == "scheduled"
        assert (lesson.learner_id, lesson.teacher_id, lesson.skill_id) == (
            people["learner"], people["teacher"], people["skill"]
        )
        assert lesson.teacher_confirmed_at is None
        assert lesson.learner_confirmed_at is None


def test_repeated_booking_submission_keeps_one_reservation(app, authenticated_client, people):
    key = str(uuid4())
    for _ in range(2):
        assert book(authenticated_client, people, booking_key=key).status_code == 302
    with app.app_context():
        assert db.session.query(Lesson).count() == 1
    assert balances(app, people)["learner"] == (3, 1, 2)


@pytest.mark.parametrize("first", ["learner", "teacher"])
def test_both_people_confirm_and_points_move_only_once(app, authenticated_client, people, first):
    lesson_id = booked_lesson(app, authenticated_client, people, past=True)
    clients = {
        "learner": authenticated_client,
        "teacher": signed_in_client(app, "points-teacher"),
    }
    second = "teacher" if first == "learner" else "learner"
    path = f"/lessons/{lesson_id}/confirm"
    assert lesson_post(clients[first], path).status_code == 302
    assert balances(app, people)["learner"] == (3, 1, 2)
    assert balances(app, people)["teacher"] == (3, 0, 3)
    assert lesson_post(clients[second], path).status_code == 302
    expected = {"learner": (2, 0, 2), "teacher": (4, 0, 4), "outsider": (3, 0, 3)}
    assert balances(app, people) == expected
    for client in clients.values():
        lesson_post(client, path)
    assert balances(app, people) == expected
    with app.app_context():
        lesson = db.session.get(Lesson, lesson_id)
        assert lesson.status == "completed"
        assert lesson.completed_at is not None
        assert lesson.teacher_confirmed_at is not None
        assert lesson.learner_confirmed_at is not None


def test_future_lesson_cannot_be_confirmed(app, authenticated_client, people):
    lesson_id = booked_lesson(app, authenticated_client, people)
    assert lesson_post(authenticated_client, f"/lessons/{lesson_id}/confirm").status_code == 400
    assert balances(app, people)["learner"] == (3, 1, 2)
    with app.app_context():
        assert db.session.get(Lesson, lesson_id).learner_confirmed_at is None


@pytest.mark.parametrize("role", ["learner", "teacher"])
def test_either_person_can_cancel_once_and_release_the_point(app, authenticated_client, people, role):
    lesson_id = booked_lesson(app, authenticated_client, people)
    client = authenticated_client if role == "learner" else signed_in_client(app, "points-teacher")
    path = f"/lessons/{lesson_id}/cancel"
    assert lesson_post(client, path).status_code == 302
    lesson_post(client, path)
    assert balances(app, people) == {
        "learner": (3, 0, 3), "teacher": (3, 0, 3), "outsider": (3, 0, 3)
    }
    with app.app_context():
        assert db.session.get(Lesson, lesson_id).status == "cancelled"
    assert lesson_post(client, f"/lessons/{lesson_id}/confirm").status_code == 400


def test_pending_confirmation_keeps_reservation_and_prevents_cancellation(app, authenticated_client, people):
    lesson_id = booked_lesson(app, authenticated_client, people, past=True)
    teacher = signed_in_client(app, "points-teacher")
    assert lesson_post(teacher, f"/lessons/{lesson_id}/confirm").status_code == 302
    for client in (authenticated_client, teacher):
        assert lesson_post(client, f"/lessons/{lesson_id}/cancel").status_code == 400
    assert balances(app, people)["learner"] == (3, 1, 2)
    assert balances(app, people)["teacher"] == (3, 0, 3)


@pytest.mark.parametrize("starting_points", [0, 1, 3])
def test_bookings_cannot_spend_more_than_available_points(app, authenticated_client, people, starting_points):
    with app.app_context():
        db.session.get(User, people["learner"]).points = starting_points
        db.session.commit()
    for day in range(starting_points):
        date = (now() + timedelta(days=day + 1)).strftime("%Y-%m-%dT%H:%M")
        assert book(authenticated_client, people, scheduled_at=date).status_code == 302
    assert book(authenticated_client, people).status_code == 400
    assert balances(app, people)["learner"] == (starting_points, starting_points, 0)
    with app.app_context():
        assert db.session.query(Lesson).count() == starting_points


def test_only_participants_see_and_change_their_lessons(app, authenticated_client, people):
    lesson_id = booked_lesson(app, authenticated_client, people, past=True)
    outsider = signed_in_client(app, "points-outsider")
    page = outsider.get("/lessons").get_data(as_text=True)
    assert "points-teacher" not in page
    assert "Piano" not in page
    for action in ("confirm", "cancel"):
        assert lesson_post(outsider, f"/lessons/{lesson_id}/{action}").status_code == 404
        assert lesson_post(outsider, f"/lessons/999999/{action}").status_code == 404
    assert balances(app, people)["learner"] == (3, 1, 2)


@pytest.mark.parametrize("path", ["/lessons", "/lessons/book/1", "/lessons/1/confirm", "/lessons/1/cancel"])
def test_lesson_pages_require_login(client, path):
    method = "POST" if path.endswith(("confirm", "cancel")) else "GET"
    assert client.open(path, method=method).status_code == 302


@pytest.mark.parametrize("action", ["book", "confirm", "cancel"])
@pytest.mark.parametrize("token_source", ["missing", "another_session"])
def test_lesson_changes_require_a_token_from_the_signed_in_session(
    app, authenticated_client, people, action, token_source
):
    lesson_id = booked_lesson(app, authenticated_client, people, past=True)
    if action == "confirm":
        teacher = signed_in_client(app, "points-teacher")
        assert lesson_post(teacher, f"/lessons/{lesson_id}/confirm").status_code == 302
    before = balances(app, people)
    data = {}
    if action == "book":
        path = f"/lessons/book/{people['teacher']}"
        data = {
            "skill_id": str(people["skill"]),
            "scheduled_at": (now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "booking_key": str(uuid4()),
        }
    else:
        path = f"/lessons/{lesson_id}/{action}"
    if token_source == "another_session":
        outsider = signed_in_client(app, "points-outsider")
        outsider.get("/lessons")
        with outsider.session_transaction() as session:
            data["lesson_form_token"] = session["lesson_form_token"]
    response = authenticated_client.post(path, data=data)
    assert response.status_code == 400
    assert balances(app, people) == before
    with app.app_context():
        assert db.session.query(Lesson).count() == 1
        lesson = db.session.get(Lesson, lesson_id)
        assert lesson.status == "scheduled"
        assert lesson.learner_confirmed_at is None


@pytest.mark.parametrize("field,value", [
    ("scheduled_at", "not-a-date"),
    ("scheduled_at", "2020-01-01T12:00"),
    ("skill_id", "999999"),
    ("skill_id", "Piano"),
    ("booking_key", "not-a-uuid"),
])
def test_invalid_booking_changes_neither_points_nor_lessons(app, authenticated_client, people, field, value):
    assert book(authenticated_client, people, **{field: value}).status_code == 400
    assert balances(app, people)["learner"] == (3, 0, 3)
    with app.app_context():
        assert db.session.query(Lesson).count() == 0


def test_only_an_active_teaching_skill_can_be_booked(app, authenticated_client, people):
    with app.app_context():
        listing = db.session.execute(db.select(Listing)).scalar_one()
        listing.is_active = False
        db.session.commit()
    assert book(authenticated_client, people).status_code == 400
    assert balances(app, people)["learner"] == (3, 0, 3)


def test_completion_rolls_back_both_accounts_if_crediting_teacher_fails(app, authenticated_client, people):
    lesson_id = booked_lesson(app, authenticated_client, people, past=True)
    with app.app_context():
        confirm_lesson(lesson_id, people["learner"])
        db.session.execute(text(f"""
            CREATE TRIGGER fail_teacher_credit BEFORE UPDATE OF points ON users
            WHEN NEW.id = {people['teacher']} AND NEW.points > OLD.points
            BEGIN SELECT RAISE(ABORT, 'test credit failure'); END
        """))
        db.session.commit()
        with pytest.raises(SQLAlchemyError):
            confirm_lesson(lesson_id, people["teacher"])
    assert balances(app, people)["learner"] == (3, 1, 2)
    assert balances(app, people)["teacher"] == (3, 0, 3)
    with app.app_context():
        lesson = db.session.get(Lesson, lesson_id)
        assert lesson.status == "scheduled"
        assert lesson.teacher_confirmed_at is None
        db.session.execute(text("DROP TRIGGER fail_teacher_credit"))
        db.session.commit()
        confirm_lesson(lesson_id, people["teacher"])
    assert balances(app, people)["learner"] == (2, 0, 2)
    assert balances(app, people)["teacher"] == (4, 0, 4)


@pytest.fixture
def persistent_app(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'points.db'}"})
    with app.app_context():
        learner = User(username="points-learner", email="learner@example.test")
        learner.set_password("secret-password")
        db.session.add(learner)
        db.session.commit()
        learner_id = learner.id
    people = add_people(app, learner_id)
    yield app, people
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def test_concurrent_bookings_cannot_reserve_the_last_point_twice(persistent_app):
    app, people = persistent_app
    with app.app_context():
        db.session.get(User, people["learner"]).points = 1
        db.session.commit()
    barrier = Barrier(2)

    def reserve(day):
        with app.app_context():
            barrier.wait(timeout=10)
            try:
                schedule_lesson(people["learner"], people["teacher"], people["skill"],
                                now() + timedelta(days=day), str(uuid4()))
                return "booked"
            except ValueError:
                return "unavailable"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, [1, 2]))
    assert sorted(results) == ["booked", "unavailable"]
    assert balances(app, people)["learner"] == (1, 1, 0)
    with app.app_context():
        assert db.session.query(Lesson).count() == 1


def test_simultaneous_confirmations_transfer_one_point(persistent_app):
    app, people = persistent_app
    with app.app_context():
        lesson = schedule_lesson(people["learner"], people["teacher"], people["skill"],
                                 now() + timedelta(days=1), str(uuid4()))
        lesson_id = lesson.id
        lesson.scheduled_at = now() - timedelta(hours=1)
        db.session.commit()
    barrier = Barrier(2)

    def confirm(user_id):
        with app.app_context():
            barrier.wait(timeout=10)
            confirm_lesson(lesson_id, user_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(confirm, [people["learner"], people["teacher"]]))
    assert balances(app, people)["learner"] == (2, 0, 2)
    assert balances(app, people)["teacher"] == (4, 0, 4)
    with app.app_context():
        assert db.session.get(Lesson, lesson_id).status == "completed"


def test_simultaneous_retries_return_the_same_last_point_booking(persistent_app, monkeypatch):
    app, people = persistent_app
    with app.app_context():
        db.session.get(User, people["learner"]).points = 1
        db.session.commit()
    barrier = Barrier(2)
    lookups = local()
    booking_key = str(uuid4())
    scheduled_at = now() + timedelta(days=1)

    def simultaneous_lookup(*args):
        lesson = existing_booking(*args)
        if not getattr(lookups, "started", False):
            lookups.started = True
            barrier.wait(timeout=10)
        return lesson

    monkeypatch.setattr("app.lessons.existing_booking", simultaneous_lookup)

    def reserve():
        with app.app_context():
            lesson = schedule_lesson(people["learner"], people["teacher"], people["skill"],
                                     scheduled_at, booking_key)
            return lesson.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(reserve) for _ in range(2)]
        lesson_ids = [future.result() for future in futures]
    assert lesson_ids[0] == lesson_ids[1]
    assert balances(app, people)["learner"] == (1, 1, 0)
    with app.app_context():
        assert db.session.query(Lesson).count() == 1


def test_existing_accounts_receive_initial_points_and_upgrade_preserves_later_balances(tmp_path):
    database_path = tmp_path / "old_points.db"
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("""CREATE TABLE users (
            id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL UNIQUE,
            username VARCHAR(50) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL,
            bio TEXT, country_code VARCHAR(2), timezone VARCHAR(50), date_of_birth DATE,
            created_at DATETIME NOT NULL
        )""")
        connection.execute("INSERT INTO users VALUES (1, 'old@example.test', 'old-user', 'saved-hash', 'Saved bio', NULL, NULL, NULL, '2026-01-01 12:00:00')")
        connection.commit()
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}"})
    runner = app.test_cli_runner()
    result = runner.invoke(args=["upgrade-db"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        user = db.session.get(User, 1)
        assert (user.points, user.reserved_points, user.available_points) == (3, 0, 3)
        assert (user.bio, user.password_hash) == ("Saved bio", "saved-hash")
        user.points = 1
        db.session.commit()
    result = runner.invoke(args=["upgrade-db"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        user = db.session.get(User, 1)
        assert (user.points, user.reserved_points) == (1, 0)
        db.session.remove()
        db.engine.dispose()
