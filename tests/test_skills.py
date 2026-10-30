"""Tests for browsing and filtering skill listings."""

import pytest

from app import db
from app.models import Listing, Skill, User


@pytest.fixture
def sample_listings(app):
    """Create isolated listings covering both types and inactive records."""
    with app.app_context():
        user = User(email="browse@example.com", username="browse-user")
        user.set_password("test-password")

        python_skill = Skill(name="Python")
        guitar_skill = Skill(name="Guitar")
        cooking_skill = Skill(name="Cooking")

        db.session.add_all([user, python_skill, guitar_skill, cooking_skill])
        db.session.flush()

        db.session.add_all([
            Listing(
                user_id=user.id,
                skill_id=python_skill.id,
                type="teach",
                description="Python tutoring",
                is_active=True,
            ),
            Listing(
                user_id=user.id,
                skill_id=guitar_skill.id,
                type="learn",
                description="Looking for guitar lessons",
                is_active=True,
            ),
            Listing(
                user_id=user.id,
                skill_id=cooking_skill.id,
                type="teach",
                description="Inactive cooking listing",
                is_active=False,
            ),
        ])
        db.session.commit()


def test_browse_page_loads(client):
    response = client.get("/skills")

    assert response.status_code == 200
    assert b"Browse Skills" in response.data
    assert b"Search by skill:" in response.data
    assert b"Reset filters" in response.data


def test_browse_shows_active_listings_only(client, sample_listings):
    response = client.get("/skills")

    assert b"Python tutoring" in response.data
    assert b"Looking for guitar lessons" in response.data
    assert b"Inactive cooking listing" not in response.data


def test_keyword_search_is_case_insensitive(client, sample_listings):
    response = client.get("/skills?keyword=python")

    assert response.status_code == 200
    assert b"Python tutoring" in response.data
    assert b"Looking for guitar lessons" not in response.data


def test_keyword_search_matches_partial_names(client, sample_listings):
    response = client.get("/skills?keyword=yth")

    assert b"Python tutoring" in response.data
    assert b"Looking for guitar lessons" not in response.data


def test_teach_filter(client, sample_listings):
    response = client.get("/skills?type=teach")

    assert b"Python tutoring" in response.data
    assert b"Looking for guitar lessons" not in response.data


def test_learn_filter(client, sample_listings):
    response = client.get("/skills?type=learn")

    assert b"Looking for guitar lessons" in response.data
    assert b"Python tutoring" not in response.data


def test_combined_filters(client, sample_listings):
    response = client.get("/skills?keyword=Python&type=teach")

    assert b"Python tutoring" in response.data
    assert b"Looking for guitar lessons" not in response.data


def test_combined_filters_with_no_matches(client, sample_listings):
    response = client.get("/skills?keyword=Python&type=learn")

    assert b"No matching skills." in response.data
    assert b"Python tutoring" not in response.data


def test_no_results_message(client, sample_listings):
    response = client.get("/skills?keyword=Nonexistent")

    assert response.status_code == 200
    assert b"No matching skills." in response.data


def test_reset_link_points_to_unfiltered_page(client, sample_listings):
    response = client.get("/skills?keyword=Python&type=teach")

    assert b'href="/skills"' in response.data

    reset_response = client.get("/skills")
    assert b"Python tutoring" in reset_response.data
    assert b"Looking for guitar lessons" in reset_response.data


def test_search_preserves_keyword(client, sample_listings):
    response = client.get("/skills?keyword=Python")

    assert b'value="Python"' in response.data


def test_browse_shows_listing_owner(client, sample_listings):
    response = client.get("/skills")

    assert b"browse-user" in response.data
