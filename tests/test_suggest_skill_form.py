"""Suggest-a-skill form on the profile Skills tab (issue #20). It is frontend only for now:
the button is disabled and nothing is saved."""
import re

from app.models import Category, Skill


def skills_page(client):
    return client.get("/profile?tab=skills").get_data(as_text=True)


def suggest_form(page):
    """The HTML of the suggest form, or None when the page does not have it."""
    match = re.search(r'<form\b[^>]*id="suggest-skill".*?</form>', page, re.S)
    return match.group() if match else None


def test_skills_tab_shows_the_suggest_form(authenticated_client, catalog):
    form = suggest_form(skills_page(authenticated_client))

    assert form is not None
    for field in ("suggested_name", "suggested_category_id", "suggested_note"):
        assert f'name="{field}"' in form


def test_submit_button_is_disabled_and_form_has_no_action(authenticated_client, catalog):
    form = suggest_form(skills_page(authenticated_client))

    assert "disabled" in re.search(r"<button\b[^>]*>", form).group()
    assert "action=" not in re.search(r"<form\b[^>]*>", form).group()


def test_category_choices_come_from_the_catalog(authenticated_client, app, catalog):
    form = suggest_form(skills_page(authenticated_client))
    category_select = re.search(r"<select\b.*?</select>", form, re.S).group()

    with app.app_context():
        expected = Category.query.count()
    # One option per category, plus "Not sure"
    assert category_select.count("<option") == expected + 1


def test_suggest_form_is_not_inside_the_skills_form(authenticated_client, catalog):
    """HTML forms can't be nested; the browser would silently drop the inner <form> tag."""
    page = skills_page(authenticated_client)
    skills_form = next(part for part in page.split("</form>") if "profile-skills" in part)

    assert 'id="suggest-skill"' not in skills_form


def test_suggest_form_is_only_on_the_skills_tab(authenticated_client, catalog):
    page = authenticated_client.get("/profile?tab=details").get_data(as_text=True)

    assert suggest_form(page) is None


def test_suggested_fields_do_not_add_a_skill_to_the_catalog(authenticated_client, app, catalog):
    """There is no logic behind the form: even if its fields are posted, the catalog is unchanged."""
    with app.app_context():
        before = Skill.query.count()

    response = authenticated_client.post(
        "/profile",
        data={
            "section": "skills",
            "learns": ["Cooking", "Drawing", "Photography"],
            "teaches": ["Chess", "Excel", "Graphic Design"],
            "suggested_name": "Underwater Basket Weaving",
            "suggested_category_id": "1",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        assert Skill.query.count() == before
        assert Skill.query.filter_by(name="Underwater Basket Weaving").first() is None
