"""Exercise the fixed catalog together with saved accounts and matching."""

import datetime as dt
from html.parser import HTMLParser

import pytest

from app import db
from app.models import Category, Listing, Skill, User


class FormParser(HTMLParser):
    """Read form values and result names without relying on HTML whitespace."""

    def __init__(self, page):
        super().__init__()
        self.inputs = []
        self.options = []
        self.groups = []
        self.names = []
        self.select = None
        self.heading = None
        self.feed(page.decode() if isinstance(page, bytes) else page)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input":
            self.inputs.append(attrs)
        elif tag == "select":
            self.select = attrs.get("name")
        elif tag == "option":
            self.options.append((self.select, attrs))
        elif tag == "optgroup":
            self.groups.append(attrs.get("label"))
        elif tag == "h3":
            self.heading = []

    def handle_data(self, data):
        if self.heading is not None:
            self.heading.append(data)

    def handle_endtag(self, tag):
        if tag == "select":
            self.select = None
        elif tag == "h3" and self.heading is not None:
            self.names.append("".join(self.heading).strip())
            self.heading = None

    def choices(self, name, checked=False):
        return {
            int(item["value"])
            for item in self.inputs
            if item.get("name") == name
            and item.get("type") == "checkbox"
            and (not checked or "checked" in item)
        }


def skill_ids(app, *names):
    with app.app_context():
        return [Skill.query.filter_by(name=name).one().id for name in names]


def active_skills(app, user_id, listing_type):
    with app.app_context():
        return {
            listing.skill_id
            for listing in Listing.query.filter_by(
                user_id=user_id, type=listing_type, is_active=True
            )
        }


def add_person(app, name, learns=(), teaches=()):
    with app.app_context():
        user = User(username=name, email=f"{name}@example.test")
        user.set_password("test-password")
        db.session.add(user)
        db.session.flush()
        for listing_type, ids in (("learn", learns), ("teach", teaches)):
            db.session.add_all(
                Listing(user_id=user.id, skill_id=skill_id, type=listing_type)
                for skill_id in ids
            )
        db.session.commit()
        return user.id


def save_profile(client, learns=(), teaches=(), **extra):
    return client.post(
        "/profile",
        data={
            "learns": [str(value) for value in learns],
            "teaches": [str(value) for value in teaches],
            **extra,
        },
    )


def test_every_skill_picker_uses_the_same_category_catalog(app, authenticated_client):
    with app.app_context():
        expected_ids = {skill.id for skill in Skill.query.all()}
        expected_categories = {category.name for category in Category.query.all()}

    assert expected_ids
    for path, fields in (
        ("/onboarding/learn", ("learns",)),
        ("/onboarding/teach", ("teaches",)),
        ("/profile", ("learns", "teaches")),
    ):
        response = authenticated_client.get(path)
        assert response.status_code == 200
        form = FormParser(response.data)
        for field in fields:
            assert form.choices(field) == expected_ids
        assert not any("custom-skill" in item.get("class", "") for item in form.inputs)

    dashboard = FormParser(authenticated_client.get("/dashboard").data)
    assert {
        int(attrs["value"])
        for name, attrs in dashboard.options
        if name == "skill" and attrs.get("value")
    } == expected_ids
    assert set(dashboard.groups) == expected_categories


def test_onboarding_profile_and_both_matching_modes_keep_accounts_separate(
    app, authenticated_client, user_id, user_data
):
    spanish, python, guitar, cooking = skill_ids(
        app, "Spanish", "Python", "Guitar", "Cooking"
    )
    assert authenticated_client.post(
        "/onboarding/learn", data={"learns": [str(spanish)]}
    ).status_code == 302
    assert authenticated_client.post(
        "/onboarding/teach", data={"teaches": [str(python)]}
    ).status_code == 302

    other = app.test_client()
    assert other.post(
        "/signup",
        data={
            "username": "catalog-partner",
            "email": "catalog-partner@example.test",
            "password": "test-password",
        },
    ).status_code == 302
    assert other.post(
        "/onboarding/learn", data={"learns": [str(python)]}
    ).status_code == 302
    assert other.post(
        "/onboarding/teach", data={"teaches": [str(spanish)]}
    ).status_code == 302

    assert authenticated_client.post("/logout").status_code == 302
    assert authenticated_client.post("/login", data=user_data).status_code == 302
    profile = FormParser(authenticated_client.get("/profile").data)
    assert profile.choices("learns", checked=True) == {spanish}
    assert profile.choices("teaches", checked=True) == {python}
    for mode in ("learner", "sharer"):
        names = FormParser(
            authenticated_client.get(f"/dashboard?mode={mode}&filter=profile").data
        ).names
        assert names == ["catalog-partner"]

    response = save_profile(other, learns=[guitar], teaches=[cooking], then="filter")
    assert response.status_code == 302
    assert "filter=profile" in response.headers["Location"]
    assert active_skills(app, user_id, "learn") == {spanish}
    assert active_skills(app, user_id, "teach") == {python}
    for mode in ("learner", "sharer"):
        assert FormParser(
            authenticated_client.get(f"/dashboard?mode={mode}&filter=profile").data
        ).names == []
        assert FormParser(
            authenticated_client.get(f"/dashboard?mode={mode}&filter=default").data
        ).names == ["catalog-partner"]


@pytest.mark.parametrize("invalid", ["999999999", "new unapproved skill"])
def test_invalid_profile_choice_does_not_partially_save_or_create_skills(
    app, authenticated_client, user_id, invalid
):
    spanish, python, guitar = skill_ids(app, "Spanish", "Python", "Guitar")
    assert save_profile(authenticated_client, [spanish], [python]).status_code == 302
    with app.app_context():
        original_count = Skill.query.count()
        original_rows = {
            listing.id for listing in Listing.query.filter_by(user_id=user_id)
        }

    # A valid learning change must not be saved when the teaching choice is invalid.
    response = save_profile(authenticated_client, [guitar], [invalid])
    assert response.status_code == 400
    assert active_skills(app, user_id, "learn") == {spanish}
    assert active_skills(app, user_id, "teach") == {python}
    with app.app_context():
        assert Skill.query.count() == original_count
        assert {
            listing.id for listing in Listing.query.filter_by(user_id=user_id)
        } == original_rows


def test_onboarding_rejects_unknown_choices_and_clears_only_its_own_side(
    app, authenticated_client, user_id
):
    spanish, python = skill_ids(app, "Spanish", "Python")
    other_id = add_person(app, "unaffected-person", learns=[spanish], teaches=[python])
    assert save_profile(authenticated_client, [spanish], [python]).status_code == 302

    for path, field in (
        ("/onboarding/learn", "learns"),
        ("/onboarding/teach", "teaches"),
    ):
        response = authenticated_client.post(path, data={field: ["999999999"]})
        assert response.status_code == 400
        assert active_skills(app, user_id, "learn") == {spanish}
        assert active_skills(app, user_id, "teach") == {python}

    assert authenticated_client.post("/onboarding/learn", data={}).status_code == 302
    assert active_skills(app, user_id, "learn") == set()
    assert active_skills(app, user_id, "teach") == {python}
    assert active_skills(app, other_id, "learn") == {spanish}
    assert active_skills(app, other_id, "teach") == {python}


def test_equal_names_in_different_categories_stay_distinct(
    app, authenticated_client, user_id
):
    with app.app_context():
        first = Skill(name="Shared skill label", category=Category(name="Test Alpha"))
        second = Skill(name="Shared skill label", category=Category(name="Test Beta"))
        db.session.add_all([first, second])
        db.session.commit()
        first_id, second_id = first.id, second.id

    add_person(app, "first-category-person", learns=[first_id], teaches=[first_id])
    add_person(app, "second-category-person", learns=[second_id], teaches=[second_id])
    assert save_profile(authenticated_client, [first_id], [first_id]).status_code == 302
    profile = FormParser(authenticated_client.get("/profile").data)
    assert profile.choices("learns", checked=True) == {first_id}
    assert profile.choices("teaches", checked=True) == {first_id}

    for mode in ("learner", "sharer"):
        assert FormParser(
            authenticated_client.get(f"/dashboard?mode={mode}&filter=profile").data
        ).names == ["first-category-person"]
        filtered = FormParser(
            authenticated_client.get(
                "/dashboard",
                query_string={"mode": mode, "filter": "skill", "skill": second_id},
            ).data
        )
        assert filtered.names == ["second-category-person"]
        assert {
            int(attrs["value"])
            for name, attrs in filtered.options
            if name == "skill" and "selected" in attrs
        } == {second_id}

    # Legacy names are accepted only when they identify exactly one catalog skill.
    assert save_profile(
        authenticated_client, ["Shared skill label"], [first_id]
    ).status_code == 400
    assert active_skills(app, user_id, "learn") == {first_id}
    for invalid in ("Shared skill label", "999999999", "not a catalog skill"):
        filtered = authenticated_client.get(
            "/dashboard", query_string={"filter": "skill", "skill": invalid}
        )
        assert filtered.status_code == 200
        assert FormParser(filtered.data).names == []


def test_repeated_saves_and_reselection_preserve_existing_listing_details(
    app, authenticated_client, user_id
):
    spanish, python = skill_ids(app, "Spanish", "Python")
    created_at = dt.datetime(2025, 1, 2, 3, 4, 5)
    with app.app_context():
        listing = Listing(
            user_id=user_id,
            skill_id=python,
            type="teach",
            level="advanced",
            description="Existing lesson details",
            created_at=created_at,
        )
        db.session.add(listing)
        db.session.commit()
        original_id = listing.id

    # Repeated submissions and duplicate values must reuse the existing row.
    for _ in range(2):
        assert save_profile(
            authenticated_client, [spanish, spanish], [python, python]
        ).status_code == 302
    with app.app_context():
        assert Listing.query.filter_by(user_id=user_id, type="learn").count() == 1
        assert Listing.query.filter_by(user_id=user_id, type="teach").count() == 1
        listing = db.session.get(Listing, original_id)
        assert listing.level == "advanced"
        assert listing.description == "Existing lesson details"
        assert listing.created_at == created_at

    assert save_profile(authenticated_client, [spanish], []).status_code == 302
    with app.app_context():
        listing = db.session.get(Listing, original_id)
        assert listing is not None
        assert listing.is_active is False

    assert save_profile(authenticated_client, [spanish], [python]).status_code == 302
    with app.app_context():
        listing = Listing.query.filter_by(
            user_id=user_id, skill_id=python, type="teach"
        ).one()
        assert listing.id == original_id
        assert listing.is_active is True
        assert listing.level == "advanced"
        assert listing.description == "Existing lesson details"
        assert listing.created_at == created_at


def test_unique_legacy_names_resolve_to_catalog_ids(app, authenticated_client, user_id):
    spanish, python = skill_ids(app, "Spanish", "Python")
    add_person(app, "legacy-link-person", teaches=[spanish])
    assert save_profile(authenticated_client, ["Spanish"], ["Python"]).status_code == 302
    assert active_skills(app, user_id, "learn") == {spanish}
    assert active_skills(app, user_id, "teach") == {python}
    profile = FormParser(authenticated_client.get("/profile").data)
    assert profile.choices("learns", checked=True) == {spanish}
    for value in (str(spanish), "Spanish"):
        page = authenticated_client.get("/dashboard", query_string={"skill": value})
        assert page.status_code == 200
        assert FormParser(page.data).names == ["legacy-link-person"]
