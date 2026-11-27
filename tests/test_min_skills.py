"""Onboarding and the profile need at least 3 skills per list, checked on the server (issue #18)."""
import pytest


STEPS = [
    # path, form field, where a valid POST goes next
    ("/onboarding/learn", "learns", "/onboarding/teach"),
    ("/onboarding/teach", "teaches", "/dashboard"),
]


@pytest.mark.parametrize("path, field, next_page", STEPS)
def test_three_skills_continue_to_the_next_step(authenticated_client, catalog, path, field, next_page):
    response = authenticated_client.post(path, data={field: ["Spanish", "Guitar", "Cooking"]})
    assert response.status_code == 302
    assert response.headers["Location"] == next_page


@pytest.mark.parametrize("path, field, next_page", STEPS)
def test_empty_submit_stays_on_the_step_with_an_error(authenticated_client, catalog, path, field, next_page):
    response = authenticated_client.post(path, data={})  # the field is missing entirely
    assert response.status_code == 400
    assert b"Pick at least 3 skills" in response.data
    assert b"(you picked 0)" in response.data
    assert b"Step" in response.data  # it is the onboarding page again, not a redirect


@pytest.mark.parametrize("path, field, next_page", STEPS)
def test_two_skills_are_refused_but_stay_selected(authenticated_client, catalog, path, field, next_page):
    response = authenticated_client.post(path, data={field: ["Spanish", "Guitar"]})
    page = response.data.decode()

    assert response.status_code == 400
    assert "(you picked 2)" in page
    assert 'value="Spanish" checked' in page  # the user doesn't have to pick them again
    assert 'value="Guitar" checked' in page


@pytest.mark.parametrize("path, field, next_page", STEPS)
def test_the_same_skill_sent_three_times_counts_once(authenticated_client, catalog, path, field, next_page):
    response = authenticated_client.post(path, data={field: ["Spanish", "Spanish", "Spanish"]})
    assert response.status_code == 400
    assert b"(you picked 1)" in response.data


@pytest.mark.parametrize("path, field, next_page", STEPS)
def test_unknown_skills_do_not_count(authenticated_client, catalog, path, field, next_page):
    response = authenticated_client.post(path, data={field: ["Spanish", "Guitar", "Not In Catalog"]})
    assert response.status_code == 400
    assert b"(you picked 2)" in response.data


def test_onboarding_says_pick_at_least_3(authenticated_client, catalog):
    page = authenticated_client.get("/onboarding/learn").data.decode()
    assert "Pick at least 3 skills." in page
    assert "Pick as many as you like." not in page


def test_profile_with_too_few_in_one_list_saves_nothing(authenticated_client, catalog, saved_skills):
    before = {"learns": saved_skills("learn"), "teaches": saved_skills("teach")}

    response = authenticated_client.post(
        "/profile",
        data={"learns": ["Cooking", "Piano", "Photography"], "teaches": ["Python", "Marketing"]},
    )
    page = response.data.decode()

    assert response.status_code == 400
    assert "Pick at least 3 skills to teach (you picked 2)" in page
    assert "to learn (you picked" not in page  # the learn list was fine
    # the valid learn list is not lost, and nothing was saved
    assert 'value="Cooking" checked' in page
    assert saved_skills("learn") == before["learns"]
    assert saved_skills("teach") == before["teaches"]


def test_profile_save_and_filter_is_refused_with_too_few(authenticated_client, catalog):
    response = authenticated_client.post(
        "/profile", data={"learns": ["Cooking"], "teaches": ["Python"], "then": "filter"}
    )
    assert response.status_code == 400  # no redirect to the dashboard
    assert b"to learn (you picked 1)" in response.data
    assert b"to teach (you picked 1)" in response.data


def test_too_few_skills_shows_the_error_as_a_styled_alert(authenticated_client, catalog):
    """The error must use the "flash error" box (styled in style.css), not plain text."""
    response = authenticated_client.post("/onboarding/learn", data={"learns": ["Spanish"]})
    page = response.data.decode()

    assert response.status_code == 400
    assert '<div class="flash error" role="alert">Pick at least 3 skills to learn (you picked 1).</div>' in page
