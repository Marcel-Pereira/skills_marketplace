import pytest

from app import create_app, db
from app.models import Listing, User
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
def saved_skills(app, user_id):
    """Read what the signed-in test user has saved: saved_skills("learn") gives skill names."""
    def read(listing_type):
        with app.app_context():
            listings = Listing.query.filter_by(user_id=user_id, type=listing_type).all()
            return sorted(listing.skill.name for listing in listings)
    return read


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
