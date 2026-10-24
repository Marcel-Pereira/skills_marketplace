from urllib.parse import parse_qs, urlsplit

import pytest

from app import db
from app.models import User


def test_signup_hashes_password_and_logs_user_in(client, app):
    response = client.post(
        "/signup",
        data={
            "email": "learner@example.com",
            "username": "learner",
            "password": "secret-password",
            "bio": "Learning Flask",
            "country_code": "ar",
            "timezone": "America/Argentina/Buenos_Aires",
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
        assert user.bio == "Learning Flask"
        assert user.country_code == "AR"
        assert user.timezone == "America/Argentina/Buenos_Aires"
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

    wrong_password = client.post(
        "/login",
        data={"email": user_data["email"], "password": "wrong-password"},
    )
    assert wrong_password.status_code == 401
    assert b"Invalid email or password." in wrong_password.data
    with client.session_transaction() as session:
        assert "_user_id" not in session

    response = client.post(
        "/login",
        data=user_data,
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert response.request.path == "/dashboard"
    assert b"Find someone to learn from" in response.data
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
