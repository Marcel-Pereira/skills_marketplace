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


def test_search_opens_the_area_and_picks_a_single_match(app, authenticated_client, catalog):
    """Searching "SPAN" opens Languages and picks Spanish, the only match. No separate results list."""
    response = authenticated_client.post(
        "/onboarding/learn", data={"action": "search", "learns_q": "SPAN", "learns": ["Guitar"]}
    )
    page = response.data.decode()
    languages = category_id_of(app, "Spanish")

    assert response.status_code == 200
    assert f'name="learns_areas" value="{languages}" checked' in page  # its area is open
    assert 'value="Spanish" checked' in page                           # and it is picked
    assert page.count('value="Spanish"') == 1                          # shown once, in its area
    assert 'value="Guitar" checked' in page                            # earlier picks survive
    assert "No skills match" not in page


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


def test_profile_search_with_several_matches_opens_their_area_without_picking(app, authenticated_client, catalog):
    """"guit" matches Guitar and Bass Guitar: Music opens in the teach picker, but nothing is picked for you."""
    response = authenticated_client.post(
        "/profile",
        data={"action": "search", "learns": ["Cooking", "Piano", "Spanish"],
              "teaches": ["Python", "Statistics", "Marketing"], "teaches_q": "guit"},
    )
    page = response.data.decode()
    music = category_id_of(app, "Guitar")

    assert response.status_code == 200
    assert 'value="Python" checked' in page and 'value="Cooking" checked' in page
    assert f'name="teaches_areas" value="{music}" checked' in page
    assert 'name="teaches" value="Guitar" checked' not in page


def test_closing_an_area_deselects_its_skills(app, authenticated_client, catalog, saved_skills):
    """The picker sends which areas are open; a picked skill in a closed area is dropped."""
    languages, music = category_id_of(app, "Spanish"), category_id_of(app, "Guitar")
    response = authenticated_client.post(
        "/profile",
        data={"learns_shown": "1", "learns_areas": [str(music)],          # Languages was closed
              "learns": ["Spanish", "Guitar", "Piano", "Drums"],
              "teaches": ["Python", "Statistics", "Marketing"]},
    )

    assert response.status_code == 302
    assert saved_skills("learn") == ["Drums", "Guitar", "Piano"]  # Spanish left with its area
    assert str(languages) != str(music)


def test_search_button_comes_before_the_submit_button_so_enter_searches(authenticated_client, catalog):
    # Enter in a text box presses the first submit button of the form
    for path, last_button in (("/onboarding/learn", ">Continue<"), ("/profile?tab=skills", ">Save skills<")):
        page = authenticated_client.get(path).data.decode()
        assert page.index('value="search"') < page.index(last_button)


def test_picker_explains_that_areas_are_not_picks(authenticated_client, catalog):
    """Areas only open a list of skills; the page says so, so people don't stop after opening areas."""
    page = authenticated_client.get("/onboarding/learn").data.decode()

    assert "Pick a few areas you're interested in." in page
    assert "Pick at least 3 skills." in page
