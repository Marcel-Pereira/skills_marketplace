from datetime import date, timedelta
import re
from urllib.parse import parse_qs, urlsplit

import pytest

from app import db
from app.models import User
from app.sample_data import CURRENT_USER


PROFILE_FIELDS = ("bio", "country_code", "timezone", "date_of_birth")


def profile_values(app, user_id):
    with app.app_context():
        user = db.session.get(User, user_id)
        return {field: getattr(user, field) for field in PROFILE_FIELDS}


@pytest.fixture
def saved_profile(app, user_id):
    values = {
        "bio": "I enjoy learning languages.",
        "country_code": "AR",
        "timezone": "America/Argentina/Buenos_Aires",
        "date_of_birth": date(1995, 6, 15),
    }
    with app.app_context():
        user = db.session.get(User, user_id)
        for field, value in values.items():
            setattr(user, field, value)
        db.session.commit()
    return values


@pytest.fixture
def sample_skills(monkeypatch):
    values = {"learns": ["Spanish", "Guitar"], "teaches": ["Python"]}
    for field, value in values.items():
        monkeypatch.setitem(CURRENT_USER, field, value.copy())
    return values


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_profile_requires_login(client, method):
    response = client.open("/profile", method=method, data={"section": "details"})

    assert response.status_code == 302
    destination = urlsplit(response.headers["Location"])
    assert destination.path == "/login"
    assert parse_qs(destination.query)["next"] == ["/profile"]


@pytest.mark.parametrize("query", ["", "?tab=details", "?tab=unknown"])
def test_profile_defaults_to_personal_details(authenticated_client, user_data, query):
    response = authenticated_client.get("/profile" + query)
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Your profile" in page
    assert user_data["username"] in page
    assert 'href="/profile?tab=details"' in page
    assert 'href="/profile?tab=skills"' in page
    active_link = re.search(r'<a\b[^>]*href="/profile\?tab=details"[^>]*>', page)
    assert 'aria-current="page"' in active_link.group()
    assert 'name="section" value="details"' in page
    assert "About you" in page
    assert "Location and time" in page
    assert "Save profile" in page
    assert 'name="learns"' not in page
    for field in PROFILE_FIELDS:
        assert f'name="{field}"' in page


def test_skills_tab_shows_existing_skill_form(authenticated_client, sample_skills):
    response = authenticated_client.get("/profile?tab=skills")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    active_link = re.search(r'<a\b[^>]*href="/profile\?tab=skills"[^>]*>', page)
    assert 'aria-current="page"' in active_link.group()
    assert 'name="section" value="skills"' in page
    assert "What do you want to learn?" in page
    assert "What can you teach?" in page
    assert 'value="Spanish" checked' in page
    assert "Save and filter by these" in page
    assert 'name="bio"' not in page


def test_personal_details_are_populated_from_saved_account(
    authenticated_client, saved_profile
):
    page = authenticated_client.get("/profile").get_data(as_text=True)

    assert saved_profile["bio"] in page
    assert 'value="1995-06-15"' in page
    assert re.search(r'<option\b[^>]*value="AR"[^>]*selected', page)
    assert re.search(
        r'<option\b[^>]*value="America/Argentina/Buenos_Aires"[^>]*selected', page
    )
    expected_age = date.today().year - 1995 - ((date.today().month, date.today().day) < (6, 15))
    assert re.search(rf"Age[^<]*</[^>]+>\s*{expected_age}\b|Age:\s*{expected_age}\b", page)


def test_profile_save_persists_details_and_preserves_skills(
    authenticated_client, app, user_id, sample_skills
):
    response = authenticated_client.post(
        "/profile",
        data={
            "section": "details",
            "bio": "  Learning Flask and Spanish.  ",
            "country_code": " ar ",
            "timezone": "America/Argentina/Buenos_Aires",
            "date_of_birth": "2000-01-02",
            "learns": ["Cooking"],
            "teaches": ["Design"],
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/profile?tab=details"
    assert profile_values(app, user_id) == {
        "bio": "Learning Flask and Spanish.",
        "country_code": "AR",
        "timezone": "America/Argentina/Buenos_Aires",
        "date_of_birth": date(2000, 1, 2),
    }
    assert CURRENT_USER["learns"] == sample_skills["learns"]
    assert CURRENT_USER["teaches"] == sample_skills["teaches"]

    page = authenticated_client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Profile saved." in page
    assert "Learning Flask and Spanish." in page
    assert 'value="2000-01-02"' in page


def test_explicitly_empty_personal_fields_are_cleared(
    authenticated_client, app, user_id, saved_profile
):
    response = authenticated_client.post(
        "/profile", data={"section": "details", **dict.fromkeys(PROFILE_FIELDS, " ")}
    )

    assert response.status_code == 302
    assert profile_values(app, user_id) == dict.fromkeys(PROFILE_FIELDS)


def test_omitted_personal_fields_keep_existing_values(
    authenticated_client, app, user_id, saved_profile
):
    response = authenticated_client.post(
        "/profile", data={"section": "details", "bio": "Updated bio"}
    )

    assert response.status_code == 302
    assert profile_values(app, user_id) == {**saved_profile, "bio": "Updated bio"}


def test_existing_legacy_country_and_timezone_survive_form_roundtrip(
    authenticated_client, app, user_id, saved_profile
):
    legacy_values = {"country_code": "AN", "timezone": "Legacy/Timezone"}
    with app.app_context():
        user = db.session.get(User, user_id)
        user.country_code = legacy_values["country_code"]
        user.timezone = legacy_values["timezone"]
        db.session.commit()

    page = authenticated_client.get("/profile").get_data(as_text=True)
    for value in legacy_values.values():
        assert re.search(rf'<option\b[^>]*value="{value}"[^>]*selected', page)

    response = authenticated_client.post(
        "/profile", data={"section": "details", "bio": "New bio", **legacy_values}
    )

    assert response.status_code == 302
    assert profile_values(app, user_id) == {**saved_profile, **legacy_values, "bio": "New bio"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("country_code", "ZZ"),
        ("country_code", "Argentina"),
        ("timezone", "Mars/Olympus_Mons"),
        ("date_of_birth", "not-a-date"),
        ("date_of_birth", "2000-02-30"),
        ("date_of_birth", "20000102"),
        ("date_of_birth", (date.today() + timedelta(days=1)).isoformat()),
    ],
)
def test_invalid_personal_fields_show_accessible_errors_without_partial_save(
    authenticated_client, app, user_id, saved_profile, field, value
):
    response = authenticated_client.post(
        "/profile",
        data={
            "section": "details",
            "bio": "Unsaved bio <script>",
            "country_code": "US",
            "timezone": "Europe/London",
            "date_of_birth": "2000-01-02",
            field: value,
        },
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 400
    assert profile_values(app, user_id) == saved_profile
    assert "Unsaved bio &lt;script&gt;" in page
    assert value in page
    control = re.search(rf'<(?:input|select|textarea)\b[^>]*id="{field}"[^>]*>', page)
    assert control is not None
    assert 'aria-invalid="true"' in control.group()
    assert f'aria-describedby="{field}-error"' in control.group()
    error = re.search(rf'<[^>]*id="{field}-error"[^>]*>', page)
    assert error is not None
    assert 'role="alert"' in error.group()


def test_birth_date_today_is_allowed_without_minimum_age(authenticated_client, app, user_id):
    response = authenticated_client.post(
        "/profile", data={"section": "details", "date_of_birth": date.today().isoformat()}
    )

    assert response.status_code == 302
    assert profile_values(app, user_id)["date_of_birth"] == date.today()
    with app.app_context():
        assert db.session.get(User, user_id).age == 0


def test_personal_details_are_isolated_to_the_signed_in_account(
    authenticated_client, app, user_id, saved_profile
):
    with app.app_context():
        other_user = User(
            email="other@example.com",
            username="other-user",
            bio="Another account's bio",
            country_code="US",
            timezone="America/New_York",
            date_of_birth=date(1980, 1, 1),
        )
        other_user.set_password("another-password")
        db.session.add(other_user)
        db.session.commit()
        other_user_id = other_user.id
    other_values = profile_values(app, other_user_id)

    response = authenticated_client.post(
        "/profile",
        data={"section": "details", "bio": "My new bio", "user_id": other_user_id},
    )

    assert response.status_code == 302
    assert profile_values(app, user_id) == {**saved_profile, "bio": "My new bio"}
    assert profile_values(app, other_user_id) == other_values


@pytest.mark.parametrize("section", [None, "skills"])
@pytest.mark.parametrize("filter_skills", [False, True])
def test_skill_submissions_preserve_personal_details_and_destinations(
    authenticated_client, app, user_id, saved_profile, sample_skills, section, filter_skills
):
    data = {
        "learns": ["Cooking"],
        "teaches": ["Design"],
        "bio": "Do not save this from the skills form",
        "country_code": "US",
    }
    if section is not None:
        data["section"] = section
    if filter_skills:
        data["then"] = "filter"
    response = authenticated_client.post("/profile", data=data)

    assert response.status_code == 302
    expected_destination = "/dashboard?mode=learner&skill=Cooking" if filter_skills else "/dashboard"
    assert response.headers["Location"] == expected_destination
    assert CURRENT_USER["learns"] == ["Cooking"]
    assert CURRENT_USER["teaches"] == ["Design"]
    assert profile_values(app, user_id) == saved_profile


def test_unknown_section_does_not_save_any_profile_or_skills(
    authenticated_client, app, user_id, saved_profile, sample_skills
):
    response = authenticated_client.post(
        "/profile", data={"section": "unknown", "bio": "Unsaved", "learns": ["Cooking"]}
    )

    assert response.status_code == 400
    assert profile_values(app, user_id) == saved_profile
    assert CURRENT_USER["learns"] == sample_skills["learns"]
    assert CURRENT_USER["teaches"] == sample_skills["teaches"]
