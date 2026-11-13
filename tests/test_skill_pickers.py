"""The skill pickers offer the fixed catalog and refuse custom choices (issue #18)."""

import pytest

from app.models import Category, Listing, Skill


def test_profile_picker_lists_the_catalog_and_has_no_free_text_box(authenticated_client, skill_ids):
    page = authenticated_client.get("/profile").get_data(as_text=True)

    assert "Programming" in page
    assert f'value="{skill_ids["Python"]}"' in page
    assert "custom-skill" not in page
    assert "chips.js" not in page


@pytest.mark.parametrize("path", ["/onboarding/learn", "/onboarding/teach"])
def test_onboarding_pickers_list_the_catalog(authenticated_client, skill_ids, path):
    page = authenticated_client.get(path).get_data(as_text=True)
    assert f'value="{skill_ids["Spanish"]}"' in page
    assert "custom-skill" not in page


def test_saved_choices_stay_selected(authenticated_client, skill_ids):
    response = authenticated_client.post(
        "/profile",
        data={
            "learns": [skill_ids["Cooking"], skill_ids["Piano"]],
            "teaches": [skill_ids["Python"]],
        },
    )
    assert response.status_code == 302
    page = authenticated_client.get("/profile").get_data(as_text=True)
    for name in ("Cooking", "Piano", "Python"):
        assert f'value="{skill_ids[name]}" checked' in page
    for name in ("Spanish", "Guitar"):
        assert f'value="{skill_ids[name]}" checked' not in page


@pytest.mark.parametrize(
    "edits",
    [
        {"learns": ["Spanish", "Totally Fake Skill"], "teaches": ["Made Up Teaching", "Python"]},
        {"learns": ["Spanish", "Totally Fake Skill"], "then": "filter"},
        {"learns": ["Only Fake"]},
    ],
    ids=["mixed", "save-and-filter", "all-invalid"],
)
def test_unknown_skills_are_rejected(app, authenticated_client, user_id, skill_ids, edits):
    saved = authenticated_client.post(
        "/profile", data={"learns": [skill_ids["Piano"]], "teaches": [skill_ids["Guitar"]]}
    )
    assert saved.status_code == 302
    with app.app_context():
        skills_before = Skill.query.count()
        categories_before = Category.query.count()

    response = authenticated_client.post("/profile", data=edits)
    assert response.status_code == 400
    assert "Location" not in response.headers

    with app.app_context():
        choices = Listing.query.filter_by(user_id=user_id, is_active=True)
        assert {(row.type, row.skill.name) for row in choices} == {
            ("learn", "Piano"),
            ("teach", "Guitar"),
        }
        assert Skill.query.count() == skills_before
        assert Category.query.count() == categories_before
