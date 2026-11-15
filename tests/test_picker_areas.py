"""The areas-first picker and its search (issue #18). It works without JavaScript:
the area chips are labels for hidden checkboxes and the search is a normal form POST."""
from app.models import Category, Skill


def category_id_of(app, skill_name):
    with app.app_context():
        return Skill.query.filter_by(name=skill_name).one().category_id


def test_every_category_gets_an_area_chip_and_the_skills_are_not_headings(authenticated_client, catalog, app):
    page = authenticated_client.get("/onboarding/learn").data.decode()
    with app.app_context():
        categories = Category.query.count()
    assert page.count('class="area-toggle"') == categories
    assert "<details" not in page  # the old collapsible headings are gone


def test_area_with_a_selected_skill_starts_open_and_others_closed(app, authenticated_client, catalog):
    learns = ["Spanish", "Guitar", "Cooking"]
    authenticated_client.post("/profile", data={"learns": learns, "teaches": ["Python", "Statistics", "Marketing"]})
    page = authenticated_client.get("/profile?tab=skills").data.decode()
    open_ids = {category_id_of(app, name) for name in learns}
    with app.app_context():
        closed_id = Category.query.filter(~Category.id.in_(open_ids)).first().id

    for cid in open_ids:
        assert f'name="learns_areas" value="{cid}" checked' in page
    assert f'name="learns_areas" value="{closed_id}" checked' not in page


def test_search_shows_matching_skills_below_the_area_chips(authenticated_client, catalog):
    response = authenticated_client.post(
        "/onboarding/learn", data={"action": "search", "learns_q": "SPAN", "learns": ["Guitar"]}
    )
    page = response.data.decode()

    assert response.status_code == 200
    assert 'class="search-results"' in page
    # Interests (area chips) come first, then the skills section: instruction, search, results
    assert page.index('class="chip area-chip"') < page.index('class="pick-hint"') < page.index('class="search-results"')
    assert page.count('value="Spanish"') == 1  # in the results only, not again in its area
    assert 'value="Guitar" checked' in page  # earlier picks survive the search
    assert 'value="Guitar"' in page and "No skills match" not in page


def test_search_with_no_match_says_so(authenticated_client, catalog):
    response = authenticated_client.post("/onboarding/learn", data={"action": "search", "learns_q": "zzzzqq"})
    assert response.status_code == 200
    assert b"No skills match that search." in response.data


def test_search_text_is_not_a_pattern(authenticated_client, catalog):
    # a "%" or "_" must be matched as a plain character, not as "match everything"
    for text in ("%", "_"):
        response = authenticated_client.post("/onboarding/learn", data={"action": "search", "learns_q": text})
        assert b"No skills match that search." in response.data


def test_search_does_not_run_the_minimum_check(authenticated_client, catalog):
    response = authenticated_client.post("/onboarding/learn", data={"action": "search", "learns_q": "py"})
    assert response.status_code == 200  # not the 400 of a too-short Continue
    assert b"you picked" not in response.data


def test_search_keeps_open_areas_open(app, authenticated_client, catalog):
    cid = category_id_of(app, "Cooking")
    page = authenticated_client.post(
        "/onboarding/learn",
        data={"action": "search", "learns_q": "py", "learns_areas": [str(cid)]},
    ).data.decode()
    assert f'name="learns_areas" value="{cid}" checked' in page


def test_profile_search_keeps_the_other_list_and_searches_both_boxes(authenticated_client, catalog):
    response = authenticated_client.post(
        "/profile",
        data={"action": "search", "learns": ["Cooking", "Piano", "Spanish"],
              "teaches": ["Python", "Statistics", "Marketing"], "teaches_q": "guit"},
    )
    page = response.data.decode()

    assert response.status_code == 200
    assert 'value="Python" checked' in page and 'value="Cooking" checked' in page
    assert page.count('class="search-results"') == 1  # only the teaches box had text
    assert page.count('name="teaches" value="Guitar"') == 1


def test_search_button_comes_before_the_submit_button_so_enter_searches(authenticated_client, catalog):
    # Enter in a text box presses the first submit button of the form
    for path, last_button in (("/onboarding/learn", ">Continue<"), ("/profile?tab=skills", ">Save skills<")):
        page = authenticated_client.get(path).data.decode()
        assert page.index('value="search"') < page.index(last_button)


def test_picker_explains_that_areas_are_not_picks(authenticated_client, catalog):
    """Areas only open a list of skills; the page says so, so people don't stop after opening areas."""
    page = authenticated_client.get("/onboarding/learn").data.decode()

    assert "Open a few areas to browse their skills, then pick at least 3." in page
