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
    assert b"Logged in" in response.data
    assert b"learner" in response.data

    with app.app_context():
        user = db.session.execute(db.select(User)).scalar_one()
        assert user.email == "learner@example.com"
        assert user.country_code == "AR"
        assert user.password_hash != "secret-password"
        assert user.check_password("secret-password")


def test_protected_page_redirects_to_login(client):
    response = client.get("/logged-in")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_user_can_log_out_and_log_back_in(client):
    client.post(
        "/signup",
        data={
            "email": "teacher@example.com",
            "username": "teacher",
            "password": "correct-password",
        },
    )
    client.post("/logout")

    wrong_password = client.post(
        "/login",
        data={"email": "teacher@example.com", "password": "wrong-password"},
    )
    assert wrong_password.status_code == 401

    response = client.post(
        "/login",
        data={"email": "teacher@example.com", "password": "correct-password"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Logged in" in response.data
