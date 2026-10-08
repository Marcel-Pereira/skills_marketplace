from app import db
from app.models import Skill, User


def test_home_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"No skills posted yet" in response.data


def test_password_is_hashed(app):
    user = User(username="alice")
    user.set_password("secret123")
    assert user.password_hash != "secret123"
    assert user.check_password("secret123")
    assert not user.check_password("wrong")


def test_skill_shows_on_home_page(app, client):
    with app.app_context():
        user = User(username="bob")
        user.set_password("pw")
        db.session.add(user)
        db.session.commit()
        db.session.add(Skill(title="Guitar lessons", description="Beginner chords", owner_id=user.id))
        db.session.commit()
    response = client.get("/")
    assert b"Guitar lessons" in response.data
