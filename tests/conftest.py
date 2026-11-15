import pytest

from app import create_app, db
from app.models import User
from app.sample_data import CURRENT_USER
from app.seed import seed_skills


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def catalog(app):
    """Load the fixed categories and skills. The test database starts empty, and the skill
    pickers (and the check that drops unknown skills) need the catalog to be there."""
    with app.app_context():
        seed_skills()


@pytest.fixture
def current_user_skills(monkeypatch):
    """The sample user's skills live in a module-level dict. Put them back after the test."""
    monkeypatch.setitem(CURRENT_USER, "learns", list(CURRENT_USER["learns"]))
    monkeypatch.setitem(CURRENT_USER, "teaches", list(CURRENT_USER["teaches"]))


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user_data():
    return {
        "email": "test@example.com",
        "username": "test-user",
        "password": "secret-password",
    }


@pytest.fixture
def user_id(app, user_data):
    with app.app_context():
        user = User(email=user_data["email"], username=user_data["username"])
        user.set_password(user_data["password"])
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def authenticated_client(client, user_id, user_data):
    response = client.post("/login", data=user_data)
    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"
    return client
