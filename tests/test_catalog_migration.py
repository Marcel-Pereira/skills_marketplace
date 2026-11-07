"""Upgrade the database used before categories, through the public seed command."""

import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.seed import CATALOG


# The schema on main before categories were introduced. Keep this independent of
# the current models so the test always starts with a real old database.
OLD_SCHEMA = """
CREATE TABLE users (
    id INTEGER NOT NULL PRIMARY KEY, email VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(50) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL,
    bio TEXT, country_code VARCHAR(2), timezone VARCHAR(50), created_at DATETIME NOT NULL
);
CREATE INDEX ix_users_timezone ON users(timezone);
CREATE INDEX ix_users_country_code ON users(country_code);
CREATE TABLE skills (id INTEGER NOT NULL PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE);
CREATE TABLE listings (
    id INTEGER NOT NULL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
    skill_id INTEGER NOT NULL REFERENCES skills(id), type VARCHAR(5) NOT NULL,
    level VARCHAR(12), description TEXT, is_active BOOLEAN NOT NULL, created_at DATETIME NOT NULL,
    CONSTRAINT uq_listing_user_skill_type UNIQUE (user_id, skill_id, type),
    CONSTRAINT ck_listing_type CHECK (type IN ('teach', 'learn')),
    CONSTRAINT ck_listing_level CHECK (level IN ('beginner', 'intermediate', 'advanced'))
);
CREATE INDEX ix_listings_skill_type ON listings(skill_id, type);
"""


@pytest.fixture
def old_database(tmp_path):
    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(OLD_SCHEMA)
        password_hash = generate_password_hash("old-password")
        for user_id, name in [(3, "learner"), (5, "teacher")]:
            connection.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, 'Original bio', 'AR', "
                "'America/Argentina/Buenos_Aires', '2026-01-01 10:00:00')",
                (user_id, f"{name}@example.test", name, password_hash),
            )
        connection.executemany("INSERT INTO skills VALUES (?, ?)", [
            (101, "Python"), (203, "Design"), (312, "Writing"),
            (487, "Mandarin"), (602, "Repairing old typewriters"),
        ])
        connection.executemany(
            "INSERT INTO listings VALUES (?, ?, ?, ?, ?, ?, ?, '2026-02-02 11:00:00')", [
                (11, 3, 101, "learn", "beginner", "Before the catalog", 1),
                (12, 3, 203, "teach", "advanced", "Design lessons", 1),
                (13, 5, 101, "teach", "advanced", "Teaching Python", 1),
                (14, 5, 312, "learn", None, None, 1),
                (15, 5, 487, "teach", "intermediate", "Paused lesson", 0),
                (16, 3, 602, "teach", "advanced", "Previously saved custom skill", 1),
            ],
        )
        connection.commit()
    return path


def application(path):
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}"})


def run_seed(app):
    result = app.test_cli_runner().invoke(args=["seed"])
    assert result.exit_code == 0, result.exception


def stored_data(connection):
    return tuple(connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
                 for table in ("users", "listings"))


def test_two_seed_commands_can_upgrade_the_same_database(old_database):
    with closing(sqlite3.connect(old_database)) as connection:
        original = stored_data(connection)
    start = Barrier(2)

    def start_and_seed():
        start.wait(timeout=10)
        result = subprocess.run(
            [sys.executable, "-m", "flask", "--app", "app", "seed"],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "DATABASE_URL": f"sqlite:///{old_database}"},
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, result.stderr

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(start_and_seed) for _ in range(2)]
        for job in jobs:
            job.result(timeout=20)

    with closing(sqlite3.connect(old_database)) as connection:
        assert stored_data(connection) == original
        assert connection.execute("SELECT count(*) FROM skills").fetchone() == (
            sum(len(names) for names in CATALOG.values()) + 1,
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_upgrade_preserves_existing_accounts_listings_and_skill_identity(old_database):
    with closing(sqlite3.connect(old_database)) as connection:
        original = stored_data(connection)
    app = application(old_database)
    run_seed(app)
    with closing(sqlite3.connect(old_database)) as connection:
        assert stored_data(connection) == original
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        skills = connection.execute(
            "SELECT s.id, s.name, c.name FROM skills s JOIN categories c ON c.id=s.category_id "
            "ORDER BY s.id"
        ).fetchall()
        assert {(101, "Python", "Programming"), (203, "Graphic Design", "Design"),
                (312, "Creative Writing", "Writing & Communication"),
                (487, "Mandarin Chinese", "Languages")} <= set(skills)
        assert any(row[:2] == (602, "Repairing old typewriters") for row in skills)
        assert {(category, name) for category, names in CATALOG.items() for name in names} <= {
            (category, name) for _, name, category in skills
        }

    run_seed(app)
    with closing(sqlite3.connect(old_database)) as connection:
        assert stored_data(connection) == original
        assert connection.execute(
            "SELECT s.id, s.name, c.name FROM skills s JOIN categories c ON c.id=s.category_id "
            "ORDER BY s.id"
        ).fetchall() == skills

    client = app.test_client()
    assert client.post("/login", data={"email": "learner@example.test", "password": "old-password"}).status_code == 302
    assert b'<h3>teacher</h3>' in client.get("/dashboard?filter=profile").data
    picker = client.get("/profile").data
    assert b'name="learns" value="101" checked' in picker
    assert b'name="teaches" value="203" checked' in picker
    assert b'Teaching Repairing old typewriters' in picker
    assert b'name="teaches" value="602"' not in picker
    response = client.post("/onboarding/teach", data={"teaches": ["602"]})
    assert response.status_code == 400
    # An ordinary profile save cannot submit the archived skill. Its previously
    # saved row must stay untouched even when the user edits their other choices.
    assert client.post("/profile", data={"learns": ["101"], "teaches": ["203"]}).status_code == 302
    with closing(sqlite3.connect(old_database)) as connection:
        assert stored_data(connection) == original


def test_known_alias_colliding_with_an_existing_skill_keeps_both_listings(old_database):
    with closing(sqlite3.connect(old_database)) as connection:
        connection.execute("INSERT INTO skills VALUES (705, 'Graphic Design')")
        connection.execute(
            "INSERT INTO listings VALUES (17, 3, 705, 'teach', 'beginner', 'Second course', "
            "1, '2026-02-03 12:00:00')"
        )
        connection.commit()
        original = stored_data(connection)
    app = application(old_database)
    run_seed(app)
    with closing(sqlite3.connect(old_database)) as connection:
        assert stored_data(connection) == original
        rows = connection.execute(
            "SELECT s.id, s.name, c.name FROM skills s JOIN categories c ON c.id=s.category_id "
            "WHERE s.id IN (203,705) ORDER BY s.id"
        ).fetchall()
        assert rows[0][:2] == (203, "Design")
        assert rows[1] == (705, "Graphic Design", "Design")
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_upgraded_database_enforces_the_new_catalog_constraints(old_database):
    app = application(old_database)
    with app.app_context(), db.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
    run_seed(app)
    with app.app_context(), db.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    with closing(sqlite3.connect(old_database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        assert [row[2] for row in connection.execute("PRAGMA index_info(ix_skills_category_id)")] == ["category_id"]
        programming, = connection.execute("SELECT category_id FROM skills WHERE id=101").fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO skills(name) VALUES ('Missing category')")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO skills(name,category_id) VALUES ('Bad category',-1)")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO skills(name,category_id) VALUES ('Python',?)", (programming,))
        # The previous global UNIQUE(name) constraint must be gone.
        connection.execute("INSERT INTO skills(name,category_id) SELECT 'Python', id FROM categories WHERE name='Music'")
        assert connection.execute("SELECT count(*) FROM skills WHERE name='Python'").fetchone() == (2,)


def test_failed_upgrade_keeps_old_data_and_can_be_retried(old_database):
    app = application(old_database)
    with closing(sqlite3.connect(old_database)) as connection:
        original = stored_data(connection)
        original_skills = connection.execute("SELECT id, name FROM skills ORDER BY id").fetchall()

    # Simulate a write failure while filling the catalog after the old table
    # has been replaced. Both its schema and contents must survive a retry.
    def interrupt_fill(conn, cursor, statement, parameters, context, executemany):
        if statement.upper().startswith("INSERT INTO SKILLS ("):
            assert "category_id" in [row[1] for row in cursor.execute("PRAGMA table_info(skills)")]
            raise sqlite3.OperationalError("simulated update interruption")

    with app.app_context():
        engine = db.engine
    event.listen(engine, "before_cursor_execute", interrupt_fill)
    try:
        interrupted = app.test_cli_runner().invoke(args=["seed"])
    finally:
        event.remove(engine, "before_cursor_execute", interrupt_fill)
    assert interrupted.exit_code != 0
    assert "simulated update interruption" in f"{interrupted.output} {interrupted.exception}"
    with closing(sqlite3.connect(old_database)) as connection:
        assert stored_data(connection) == original
        assert connection.execute("SELECT id, name FROM skills ORDER BY id").fetchall() == original_skills
        assert [row[1] for row in connection.execute("PRAGMA table_info(skills)")] == ["id", "name"]
        assert connection.execute("SELECT count(*) FROM categories").fetchone() == (0,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    run_seed(app)
    with closing(sqlite3.connect(old_database)) as connection:
        assert stored_data(connection) == original
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
