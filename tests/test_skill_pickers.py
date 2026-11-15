"""The skill pickers only offer the fixed catalog, and the server refuses anything else (issue #18)."""
from app import db
from app.models import Category, Skill


def test_profile_picker_lists_the_catalog_and_has_no_free_text_box(authenticated_client, catalog):
    page = authenticated_client.get("/profile").data.decode()

    assert "Programming" in page  # a category heading
    assert 'value="Python"' in page  # a catalog skill
    assert "custom-skill" not in page  # the "type your own skill" box is gone
    assert "chips.js" not in page  # and so is the script that powered it


def test_onboarding_pickers_list_the_catalog(authenticated_client, catalog):
    for path in ("/onboarding/learn", "/onboarding/teach"):
        page = authenticated_client.get(path).data.decode()
        assert 'value="Spanish"' in page
        assert "custom-skill" not in page


def test_saved_choices_stay_selected(authenticated_client, catalog):
    authenticated_client.post(
        "/profile",
        data={"learns": ["Cooking", "Piano", "Photography"], "teaches": ["Python", "Statistics", "Marketing"]},
    )

    page = authenticated_client.get("/profile").data.decode()
    assert 'value="Cooking" checked' in page
    assert 'value="Piano" checked' in page
    assert 'value="Python" checked' in page
    # what I did not pick is not selected
    assert 'value="Spanish" checked' not in page
    assert 'value="Guitar" checked' not in page


def test_unknown_skills_are_rejected(app, authenticated_client, catalog, saved_skills):
    with app.app_context():
        skills_before = Skill.query.count()
        categories_before = Category.query.count()

    response = authenticated_client.post(
        "/profile",
        data={"learns": ["Spanish", "Guitar", "Cooking", "Totally Fake Skill"],
              "teaches": ["Made Up Teaching", "Python", "Statistics", "Marketing"]},
    )
    assert response.status_code == 302

    # Only the catalog skills were kept
    assert saved_skills("learn") == ["Cooking", "Guitar", "Spanish"]
    assert saved_skills("teach") == ["Marketing", "Python", "Statistics"]

    page = authenticated_client.get("/profile").data.decode()
    assert "Totally Fake Skill" not in page
    assert "Made Up Teaching" not in page

    # And nothing new was added to the catalog
    with app.app_context():
        assert Skill.query.count() == skills_before
        assert Category.query.count() == categories_before
        assert Skill.query.filter_by(name="Totally Fake Skill").first() is None


def test_unknown_skills_are_left_out_of_save_and_filter(authenticated_client, catalog, saved_skills):
    response = authenticated_client.post(
        "/profile",
        data={"learns": ["Spanish", "Guitar", "Cooking", "Totally Fake Skill"],
              "teaches": ["Python", "Statistics", "Marketing"], "then": "filter"},
    )
    # "Save and filter" opens My Profile, which matches on the saved (catalog-only) skills
    assert response.headers["Location"] == "/dashboard?mode=learner&filter=profile"
    assert saved_skills("learn") == ["Cooking", "Guitar", "Spanish"]


def test_nothing_valid_submitted_is_refused_and_keeps_the_old_skills(
        authenticated_client, catalog, saved_skills):
    before = {"learns": saved_skills("learn"), "teaches": saved_skills("teach")}

    response = authenticated_client.post("/profile", data={"learns": ["Only Fake"], "teaches": []})

    assert response.status_code == 400
    assert saved_skills("learn") == before["learns"]
    assert saved_skills("teach") == before["teaches"]
