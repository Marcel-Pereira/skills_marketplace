import pytest

from app.sample_data import CURRENT_USER


@pytest.mark.parametrize("path", ["/signup", "/login"])
def test_public_screens_load(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/onboarding/learn", "/onboarding/teach",
                                  "/dashboard", "/dashboard?mode=sharer"])
def test_protected_screens_load(authenticated_client, path):
    assert authenticated_client.get(path).status_code == 200


def test_signup_flow_goes_through_onboarding_to_dashboard(client, user_data):
    signup = client.post("/signup", data=user_data)
    assert signup.status_code == 302
    assert signup.headers["Location"] == "/onboarding/learn"

    learn = client.post("/onboarding/learn", data={"learns": ["Spanish", "Guitar"]})
    assert learn.status_code == 302
    assert learn.headers["Location"] == "/onboarding/teach"

    teach = client.post("/onboarding/teach", data={"teaches": ["Python"]})
    assert teach.status_code == 302
    assert teach.headers["Location"] == "/dashboard"
    assert client.get("/dashboard").status_code == 200


def test_no_filter_shows_everyone_best_matches_first(authenticated_client):
    # The sample user wants to learn Spanish, Guitar and Design.
    # Mateo teaches two of those, Jiwoo one, Sam none (but still shows up).
    page = authenticated_client.get("/dashboard?mode=learner").data
    assert b"Sam" in page
    assert page.index(b"Mateo") < page.index(b"Jiwoo") < page.index(b"Sam")


def test_learner_skill_filter_shows_people_who_teach_it(authenticated_client):
    page = authenticated_client.get("/dashboard?mode=learner&skill=Spanish").data
    assert b"Mateo" in page
    assert b"Linh" not in page  # Linh wants to learn Spanish, doesn't teach it


def test_picking_several_skills_shows_anyone_with_one_of_them(authenticated_client):
    page = authenticated_client.get("/dashboard?mode=learner&skill=Spanish&skill=Design").data
    assert b"Mateo" in page and b"Jiwoo" in page
    assert b"Sam" not in page


def test_sharer_skill_filter_shows_people_who_want_to_learn_it(authenticated_client):
    page = authenticated_client.get("/dashboard?mode=sharer&skill=Spanish").data
    assert b"Linh" in page
    assert b"Mateo" not in page


def test_removing_one_picked_skill_keeps_the_others(authenticated_client):
    page = authenticated_client.get("/dashboard?mode=learner&skill=Spanish&skill=Design").data.decode()
    # The × on Spanish links to the page with only Design still picked
    assert 'href="/dashboard?mode=learner&amp;skill=Design" title="Remove Spanish"' in page


def test_logo_links_to_dashboard_when_signed_in(client):
    assert b'<a class="brand" href="/dashboard">Skills Marketplace</a>' in client.get("/dashboard").data
    assert b'<a class="brand" href="/">Skills Marketplace</a>' in client.get("/signin").data


def test_profile_preselects_my_skills(authenticated_client):
    page = authenticated_client.get("/profile").data.decode()
    assert 'value="Spanish" checked' in page
    assert 'value="JavaScript" checked' not in page


def test_profile_save_and_filter(authenticated_client, monkeypatch):
    # monkeypatch puts the sample user's skills back after the test
    monkeypatch.setitem(CURRENT_USER, "learns", CURRENT_USER["learns"])
    monkeypatch.setitem(CURRENT_USER, "teaches", CURRENT_USER["teaches"])

    response = authenticated_client.post("/profile", data={"learns": ["Cooking"], "teaches": ["Python"]})
    assert response.headers["Location"] == "/dashboard"
    assert CURRENT_USER["learns"] == ["Cooking"]

    response = authenticated_client.post("/profile", data={"learns": ["Cooking"], "then": "filter"})
    assert response.headers["Location"] == "/dashboard?mode=learner&skill=Cooking"

def test_logo_links_to_dashboard_when_signed_in(authenticated_client):
    assert b'<a class="brand" href="/dashboard">Skills Marketplace</a>' in authenticated_client.get("/dashboard").data


def test_logo_links_home_on_login_page(client):
    assert b'<a class="brand" href="/">Skills Marketplace</a>' in client.get("/login").data
