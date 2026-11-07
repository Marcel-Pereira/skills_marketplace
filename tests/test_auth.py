from urllib.parse import parse_qs, urlsplit

import pytest

from app import db
from app.models import User


@pytest.mark.parametrize("profile_fields", [
    {},
    {
        "bio": "Learning Flask",
        "country_code": "ar",
        "timezone": "America/Argentina/Buenos_Aires",
    },
])
def test_signup_uses_account_fields_hashes_password_and_logs_user_in(client, app, profile_fields):
    response = client.post(
        "/signup",
        data={
            "email": " Learner@Example.com ",
            "username": " learner ",
            "password": "secret-password",
            **profile_fields,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.path == "/onboarding/learn"
    assert b"What do you want to learn?" in response.data

    with app.app_context():
        user = db.session.execute(db.select(User)).scalar_one()
        assert user.email == "learner@example.com"
        assert user.username == "learner"
        assert user.bio is None
        assert user.country_code is None
        assert user.timezone is None
        assert user.password_hash != "secret-password"
        assert user.check_password("secret-password")
        user_id = user.id

    with client.session_transaction() as session:
        assert session["_user_id"] == str(user_id)


@pytest.mark.parametrize("method,path", [
    ("GET", "/dashboard"),
    ("GET", "/dashboard?mode=sharer"),
    ("GET", "/onboarding/learn"),
    ("GET", "/onboarding/teach"),
    ("POST", "/onboarding/learn"),
    ("POST", "/onboarding/teach"),
    ("POST", "/logout"),
])
def test_protected_page_redirects_to_login(client, method, path):
    response = client.open(path, method=method)

    assert response.status_code == 302
    location = urlsplit(response.headers["Location"])
    assert location.path == "/login"
    assert parse_qs(location.query)["next"] == [path]


def test_user_can_log_out_and_log_back_in(authenticated_client, user_id, user_data):
    client = authenticated_client
    response = client.post("/logout", follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == "/login"
    assert b"You have been logged out." in response.data

    with client.session_transaction() as session:
        assert "_user_id" not in session

    protected_page = client.get("/dashboard")
    assert protected_page.status_code == 302
    assert urlsplit(protected_page.headers["Location"]).path == "/login"

    response = client.post(
        "/login",
        data={"username": user_data["username"], "password": user_data["password"]},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert response.request.path == "/dashboard"
    assert b"Find someone to learn from" in response.data
    with client.session_transaction() as session:
        assert session["_user_id"] == str(user_id)


@pytest.mark.parametrize("credentials", [
    {"username": "unknown-user", "password": "secret-password"},
    {"username": "test-user", "password": "wrong-password"},
    {"username": "TEST-USER", "password": "secret-password"},
    {"email": "test@example.com", "password": "secret-password"},
    {"username": "test@example.com", "password": "secret-password"},
    {"username": "", "password": "secret-password"},
    {"username": "test-user", "password": ""},
])
def test_login_rejects_invalid_credentials(client, user_id, credentials):
    response = client.post("/login", data=credentials)

    assert response.status_code == 401
    assert b"Invalid username or password." in response.data
    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_login_trims_username(client, user_id, user_data):
    response = client.post(
        "/login",
        data={"username": f"  {user_data['username']}  ", "password": user_data["password"]},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"
    with client.session_transaction() as session:
        assert session["_user_id"] == str(user_id)


@pytest.mark.parametrize("missing_field", ["email", "username", "password"])
def test_signup_requires_account_fields(client, app, user_data, missing_field):
    data = {key: value for key, value in user_data.items() if key != missing_field}
    response = client.post("/signup", data=data)

    assert response.status_code == 400
    assert b"Email, username, and password are required." in response.data
    with app.app_context():
        assert db.session.execute(db.select(User)).scalars().all() == []
    with client.session_transaction() as session:
        assert "_user_id" not in session


@pytest.mark.parametrize("duplicate_field", ["email", "username"])
def test_signup_rejects_duplicate_accounts(client, app, user_id, user_data, duplicate_field):
    data = {
        "email": "another@example.com",
        "username": "another-user",
        "password": "another-password",
    }
    data[duplicate_field] = user_data[duplicate_field]

    response = client.post("/signup", data=data)

    assert response.status_code == 409
    assert b"That email or username is already registered." in response.data
    with app.app_context():
        assert db.session.execute(db.select(User.id)).scalars().all() == [user_id]
    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_login_and_signup_preserve_existing_profile_data(client, app, user_id, user_data):
    with app.app_context():
        user = db.session.get(User, user_id)
        user.bio = "Learning Flask"
        user.country_code = "AR"
        user.timezone = "America/Argentina/Buenos_Aires"
        db.session.commit()

    login = client.post(
        "/login",
        data={"username": user_data["username"], "password": user_data["password"]},
    )
    assert login.status_code == 302
    client.post("/logout")

    signup = client.post(
        "/signup",
        data={
            "username": "new-user",
            "email": "new@example.com",
            "password": "new-password",
        },
    )
    assert signup.status_code == 302

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.bio == "Learning Flask"
        assert user.country_code == "AR"
        assert user.timezone == "America/Argentina/Buenos_Aires"
