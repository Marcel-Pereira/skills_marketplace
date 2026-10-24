import pytest


@pytest.mark.parametrize("path", ["/signup", "/login", "/onboarding/learn", "/onboarding/teach",
                                  "/dashboard", "/dashboard?mode=sharer"])
def test_screens_load(client, path):
    assert client.get(path).status_code == 200


def test_signup_flow_goes_through_onboarding_to_dashboard(client):
    assert client.post("/signup").headers["Location"] == "/onboarding/learn"
    assert client.post("/onboarding/learn").headers["Location"] == "/onboarding/teach"
    assert client.post("/onboarding/teach").headers["Location"] == "/dashboard"


def test_no_filter_shows_everyone_best_matches_first(client):
    # The sample user wants to learn Spanish, Guitar and Design.
    # Mateo teaches two of those, Jiwoo one, Sam none (but still shows up).
    page = client.get("/dashboard?mode=learner").data
    assert b"Sam" in page
    assert page.index(b"Mateo") < page.index(b"Jiwoo") < page.index(b"Sam")


def test_learner_skill_filter_shows_people_who_teach_it(client):
    page = client.get("/dashboard?mode=learner&skill=Spanish").data
    assert b"Mateo" in page
    assert b"Linh" not in page  # Linh wants to learn Spanish, doesn't teach it


def test_picking_several_skills_shows_anyone_with_one_of_them(client):
    page = client.get("/dashboard?mode=learner&skill=Spanish&skill=Design").data
    assert b"Mateo" in page and b"Jiwoo" in page
    assert b"Sam" not in page


def test_sharer_skill_filter_shows_people_who_want_to_learn_it(client):
    page = client.get("/dashboard?mode=sharer&skill=Spanish").data
    assert b"Linh" in page
    assert b"Mateo" not in page


def test_removing_one_picked_skill_keeps_the_others(client):
    page = client.get("/dashboard?mode=learner&skill=Spanish&skill=Design").data.decode()
    # The × on Spanish links to the page with only Design still picked
    assert 'href="/dashboard?mode=learner&amp;skill=Design" title="Remove Spanish"' in page


def test_logo_links_to_dashboard_when_signed_in(client):
    assert b'<a class="brand" href="/dashboard">Skills Marketplace</a>' in client.get("/dashboard").data
    assert b'<a class="brand" href="/">Skills Marketplace</a>' in client.get("/login").data
