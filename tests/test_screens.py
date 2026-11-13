import pytest

from app.sample_data import PEOPLE

@pytest.fixture
def matching_data(app, authenticated_client, user_id):
    """Create real database users and listings for dashboard tests."""

    from app import db
    from app.models import User, Skill, Listing

    # Give the signed-in user skills to match against.
    authenticated_client.post(
        "/profile",
        data={
            "learns": ["Spanish", "Guitar", "Graphic Design"],
            "teaches": ["Python", "Statistics"],
        },
    )

    with app.app_context():
        # Reuse the familiar example people, but save them in the database.
        for person in PEOPLE:
            user = User(
                email=f"{person['name'].lower()}@example.com",
                username=person["name"],
            )
            user.set_password("test-password")
            db.session.add(user)
            db.session.flush()

            for listing_type, field in [
                ("teach", "teaches"),
                ("learn", "learns"),
            ]:
                for skill_name in person[field]:
                    skill = Skill.query.filter_by(name=skill_name).one()

                    db.session.add(
                        Listing(
                            user_id=user.id,
                            skill_id=skill.id,
                            type=listing_type,
                            is_active=True,
                        )
                    )

        db.session.commit()


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


def test_learner_shows_only_matching_people(authenticated_client, matching_data):
    # The sample user wants to learn Spanish, Guitar, and Graphic Design.
    # Mateo and Jiwoo teach matching skills, but Sam does not.
    page = authenticated_client.get(
        "/dashboard?mode=learner&filter=profile"
    ).data

    assert b"<h3>Mateo</h3>" in page
    assert b"<h3>Jiwoo</h3>" in page
    assert b"<h3>Sam</h3>" not in page

    # People with more matching skills should appear first.
    assert page.index(b"Mateo") < page.index(b"Jiwoo")

def test_sharer_shows_only_matching_people(authenticated_client, matching_data):
    # The sample user teaches Python and Statistics.
    # Only people who want to learn those skills should appear.
    page = authenticated_client.get(
        "/dashboard?mode=sharer&filter=profile"
    ).data

    # These people want to learn skills the user can teach.
    assert b"<h3>Mateo</h3>" in page
    assert b"<h3>Sam</h3>" in page

    # These people do not want to learn the user's teaching skills.
    assert b"<h3>Linh</h3>" not in page
    assert b"<h3>Jiwoo</h3>" not in page


def test_learner_skill_filter_shows_people_who_teach_it(authenticated_client, matching_data):
    page = authenticated_client.get("/dashboard?mode=learner&skill=Spanish").data
    assert b"<h3>Mateo</h3>" in page
    assert b"<h3>Linh</h3>" not in page  # Linh wants to learn Spanish, doesn't teach it


def test_single_skill_filter_shows_only_relevant_people(
    authenticated_client, matching_data
):
    """A single skill filter shows only matching people for that skill."""

    # Mateo teaches Spanish, while Jiwoo teaches Graphic Design.
    spanish_page = authenticated_client.get(
        "/dashboard?mode=learner&filter=skill&skill=Spanish"
    ).data

    assert b"<h3>Mateo</h3>" in spanish_page
    assert b"<h3>Jiwoo</h3>" not in spanish_page

    # Selecting Graphic Design should show Jiwoo instead of Mateo.
    design_page = authenticated_client.get(
        "/dashboard?mode=learner&filter=skill&skill=Graphic%20Design"
    ).data

    assert b"<h3>Jiwoo</h3>" in design_page
    assert b"<h3>Mateo</h3>" not in design_page


def test_sharer_skill_filter_shows_people_who_want_to_learn_it(
    authenticated_client, matching_data
):
    """By Skill shows people requesting the chosen skill, regardless of profile."""
    python_page = authenticated_client.get(
        "/dashboard?mode=sharer&filter=skill&skill=Python"
    ).data
    assert b"<h3>Mateo</h3>" in python_page
    assert b"<h3>Linh</h3>" not in python_page

    spanish_page = authenticated_client.get(
        "/dashboard?mode=sharer&filter=skill&skill=Spanish"
    ).data
    assert b"<h3>Linh</h3>" in spanish_page
    assert b"<h3>Mateo</h3>" not in spanish_page

def test_skill_filter_shows_selected_skills(authenticated_client, skill_ids):
    spanish_id = skill_ids["Spanish"]
    response = authenticated_client.get(
        "/dashboard", query_string={"mode": "learner", "filter": "skill", "skill": spanish_id}
    )
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert f'name="remove_skill" value="{spanish_id}"' in page
    assert "By Skill (1)" in page
    assert 'name="filter" value="skill"' in page
    assert "Everyone" in page
    assert "My Profile" in page


def test_profile_preselects_my_skills(authenticated_client, skill_ids):
    """The profile shows skills saved for the signed-in user."""

    # Save skills through onboarding.
    authenticated_client.post(
        "/onboarding/learn",
        data={"learns": ["Spanish", "Guitar"]}
    )

    authenticated_client.post(
        "/onboarding/teach",
        data={"teaches": ["Python"]}
    )

    page = authenticated_client.get("/profile").data.decode()

    assert f'value="{skill_ids["Spanish"]}" checked' in page
    assert f'value="{skill_ids["Guitar"]}" checked' in page
    assert f'value="{skill_ids["Python"]}" checked' in page
    assert f'value="{skill_ids["JavaScript"]}" checked' not in page


def test_profile_save_and_filter(authenticated_client, app, user_id, skill_ids):
    """Profile changes are saved in the database and used for filtering."""

    from app.models import Listing

    # Change the user's skills through the profile page.
    response = authenticated_client.post(
        "/profile",
        data={
            "learns": ["Cooking"],
            "teaches": ["Python"],
            "then": "filter",
        }
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard?mode=learner&filter=profile"

    # Verify the changes were saved for the correct account.
    with app.app_context():
        listings = Listing.query.filter_by(user_id=user_id, is_active=True).all()

        learning_skills = {
            listing.skill.name
            for listing in listings
            if listing.type == "learn"
        }

        teaching_skills = {
            listing.skill.name
            for listing in listings
            if listing.type == "teach"
        }

        assert learning_skills == {"Cooking"}
        assert teaching_skills == {"Python"}

    # The profile should display the newly saved selections.
    page = authenticated_client.get("/profile").data.decode()

    assert f'value="{skill_ids["Cooking"]}" checked' in page
    assert f'value="{skill_ids["Python"]}" checked' in page
    assert f'value="{skill_ids["Spanish"]}" checked' not in page

def test_connect_opens_chat_and_sending_adds_message(authenticated_client, matching_data):
    # Mateo matches the sample user's learning interests,
    # so their Connect button should appear on the dashboard.
    dashboard = authenticated_client.get("/dashboard").data
    assert b"/chat/Mateo" in dashboard

    # Wei does not match the current learner profile,
    # but an existing chat route should still work.
    response = authenticated_client.post(
        "/chat/Wei",
        data={"text": "Hi Wei, can you teach me Mandarin?"}
    )

    assert response.headers["Location"] == "/chat/Wei"
    assert b"can you teach me Mandarin?" in authenticated_client.get("/chat/Wei").data
    assert b"Wei" in authenticated_client.get("/messages").data


def test_chat_with_unknown_person_is_404(authenticated_client):
    assert authenticated_client.get("/chat/Nobody").status_code == 404

def test_logo_links_to_dashboard_when_signed_in(authenticated_client):
    assert b'<a class="brand" href="/dashboard">Skills Marketplace</a>' in authenticated_client.get("/dashboard").data


def test_logo_links_home_on_login_page(client):
    assert b'<a class="brand" href="/">Skills Marketplace</a>' in client.get("/login").data

def test_onboarding_saves_skills_to_database(authenticated_client, app, user_id):
    """Check that onboarding saves learning and teaching skills for the user."""

    from app.models import Listing

    # Save the skills the user wants to learn.
    response = authenticated_client.post(
        "/onboarding/learn",
        data={"learns": ["Spanish", "Guitar"]}
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/onboarding/teach"

    # Save the skills the user can teach.
    response = authenticated_client.post(
        "/onboarding/teach",
        data={"teaches": ["Python", "Statistics"]}
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"

    # Verify that the selected skills were actually saved in the database.
    with app.app_context():
        listings = Listing.query.filter_by(user_id=user_id, is_active=True).all()

        learning_skills = {
            listing.skill.name
            for listing in listings
            if listing.type == "learn"
        }

        teaching_skills = {
            listing.skill.name
            for listing in listings
            if listing.type == "teach"
        }

        assert learning_skills == {"Spanish", "Guitar"}
        assert teaching_skills == {"Python", "Statistics"}

def test_users_have_separate_skill_profiles(app, client, user_id, skill_ids):
    """Changing one user's skills must not change another user's profile."""

    from app import db
    from app.models import User

    # Log in as the first user and save their learning skills.
    response = client.post(
        "/login",
        data={
            "email": "test@example.com",
            "password": "secret-password"
        }
    )
    assert response.status_code == 302

    client.post(
        "/profile",
        data={
            "learns": ["Spanish"],
            "teaches": ["Python"]
        }
    )

    # Create a second user in the database.
    with app.app_context():
        second_user = User(
            email="second@example.com",
            username="second-user"
        )
        second_user.set_password("second-password")

        db.session.add(second_user)
        db.session.commit()

    # Log out of the first account.
    client.post("/logout")

    # Log in as the second user.
    response = client.post(
        "/login",
        data={
            "email": "second@example.com",
            "password": "second-password"
        }
    )
    assert response.status_code == 302

    # The second user's profile should not contain the first user's skills.
    page = client.get("/profile").data.decode()

    assert f'value="{skill_ids["Spanish"]}" checked' not in page
    assert f'value="{skill_ids["Python"]}" checked' not in page

    # The second user can save different skills.
    client.post(
        "/profile",
        data={
            "learns": ["Guitar"],
            "teaches": ["Statistics"]
        }
    )

    page = client.get("/profile").data.decode()

    assert f'value="{skill_ids["Guitar"]}" checked' in page
    assert f'value="{skill_ids["Statistics"]}" checked' in page

    # Return to the first user and check their skills are unchanged.
    client.post("/logout")

    client.post(
        "/login",
        data={
            "email": "test@example.com",
            "password": "secret-password"
        }
    )

    page = client.get("/profile").data.decode()

    assert f'value="{skill_ids["Spanish"]}" checked' in page
    assert f'value="{skill_ids["Python"]}" checked' in page
    assert f'value="{skill_ids["Guitar"]}" checked' not in page

def test_dashboard_matches_real_users(app, authenticated_client, user_id):
    """Show matching database users, not unrelated sample people."""

    from app import db
    from app.models import User, Skill, Listing

    with app.app_context():
        # Create two other users.
        teacher = User(
            email="teacher@example.com",
            username="real-spanish-teacher"
        )
        teacher.set_password("password123")

        unrelated = User(
            email="unrelated@example.com",
            username="real-java-teacher"
        )
        unrelated.set_password("password123")

        db.session.add_all([teacher, unrelated])
        db.session.flush()

        # Use the same approved catalog as onboarding and the profile.
        spanish = Skill.query.filter_by(name="Spanish").one()
        java = Skill.query.filter_by(name="Java").one()

        db.session.add_all([
            Listing(
                user_id=teacher.id,
                skill_id=spanish.id,
                type="teach"
            ),
            Listing(
                user_id=unrelated.id,
                skill_id=java.id,
                type="teach"
            )
        ])

        db.session.commit()

    # The signed-in user wants to learn Spanish.
    authenticated_client.post(
        "/profile",
        data={"learns": ["Spanish"]}
    )

    # Check the Learner dashboard using personalized matching.
    page = authenticated_client.get(
        "/dashboard?mode=learner&filter=profile"
    ).data

    # Show the real user teaching Spanish.
    assert b"<h3>real-spanish-teacher</h3>" in page

    # Hide the unrelated user.
    assert b"<h3>real-java-teacher</h3>" not in page

    # Do not show the signed-in user as their own match.
    assert b"<h3>test-user</h3>" not in page

def test_single_skill_filter_matches_correct_people(
    authenticated_client, matching_data
):
    """A selected skill should show only people matching that skill."""

    # Mateo teaches Spanish and Guitar.
    # Jiwoo teaches Graphic Design.
    # Selecting Spanish should show Mateo, but not Jiwoo.
    page = authenticated_client.get(
        "/dashboard?mode=learner&filter=skill&skill=Spanish"
    ).data

    assert b"<h3>Mateo</h3>" in page
    assert b"<h3>Jiwoo</h3>" not in page
    assert b"<h3>Sam</h3>" not in page

    # Switching to Graphic Design should show Jiwoo instead.
    page = authenticated_client.get(
        "/dashboard?mode=learner&filter=skill&skill=Graphic%20Design"
    ).data

    assert b"<h3>Jiwoo</h3>" in page
    assert b"<h3>Mateo</h3>" not in page

def test_sharer_single_skill_filter(
    authenticated_client, matching_data
):
    """Show only people who want to learn the selected skill."""

    # Mateo wants to learn Python.
    # Sam wants to learn Statistics.

    # Selecting Python should show Mateo, but not Sam.
    page = authenticated_client.get(
        "/dashboard?mode=sharer&filter=skill&skill=Python"
    ).data

    assert b"<h3>Mateo</h3>" in page
    assert b"<h3>Sam</h3>" not in page

    # Selecting Statistics should show Sam, but not Mateo.
    page = authenticated_client.get(
        "/dashboard?mode=sharer&filter=skill&skill=Statistics"
    ).data

    assert b"<h3>Sam</h3>" in page
    assert b"<h3>Mateo</h3>" not in page

def test_by_skill_works_independently_of_profile(
    authenticated_client, matching_data
):
    """Selecting Mandarin Chinese finds Mandarin Chinese teachers without requiring it in my profile."""
    page = authenticated_client.get(
        "/dashboard?mode=learner&filter=skill&skill=Mandarin%20Chinese"
    ).data
    assert b"<h3>Wei</h3>" in page
    assert b"<h3>Mateo</h3>" not in page

def test_inactive_skill_listing_is_not_a_match(
    app, authenticated_client, matching_data
):
    """Inactive teaching listings must not produce learner matches."""

    from app import db
    from app.models import Listing, User, Skill

    with app.app_context():
        # Find Mateo's Spanish teaching listing.
        mateo = User.query.filter_by(username="Mateo").first()
        spanish = Skill.query.filter_by(name="Spanish").first()

        listing = Listing.query.filter_by(
            user_id=mateo.id,
            skill_id=spanish.id,
            type="teach"
        ).first()

        # Disable only the Spanish listing.
        listing.is_active = False
        db.session.commit()

    # Mateo still teaches Guitar, so he can appear for Guitar.
    guitar_page = authenticated_client.get(
        "/dashboard?mode=learner&filter=skill&skill=Guitar"
    ).data

    assert b"<h3>Mateo</h3>" in guitar_page

    # Mateo should not appear for Spanish anymore.
    spanish_page = authenticated_client.get(
        "/dashboard?mode=learner&filter=skill&skill=Spanish"
    ).data

    assert b"<h3>Mateo</h3>" not in spanish_page


def test_empty_profile_shows_no_matches(
    authenticated_client, matching_data
):
    """A user with no saved skills should have no personalized matches."""

    # Remove all learning and teaching skills from the current profile.
    response = authenticated_client.post(
        "/profile",
        data={"learns": [], "teaches": []}
    )

    assert response.status_code == 302

    # Neither Learner nor Sharer should show unrelated people.
    for mode in ("learner", "sharer"):
        page = authenticated_client.get(
            f"/dashboard?mode={mode}&filter=profile"
        )

        assert page.status_code == 200
        assert b"No one matches these skills yet" in page.data

        # Existing sample people should not appear as matches.
        assert b"<h3>Mateo</h3>" not in page.data
        assert b"<h3>Jiwoo</h3>" not in page.data
        assert b"<h3>Sam</h3>" not in page.data

def test_default_and_profile_have_distinct_results(
    authenticated_client, matching_data
):
    """Default shows everyone; My Profile only shows matching teachers."""
    default_page = authenticated_client.get(
        "/dashboard?mode=learner&filter=default"
    ).data
    profile_page = authenticated_client.get(
        "/dashboard?mode=learner&filter=profile"
    ).data

    assert b"<h3>Mateo</h3>" in default_page
    assert b"<h3>Jiwoo</h3>" in default_page
    assert b"<h3>Wei</h3>" in default_page
    assert b"<h3>Sam</h3>" in default_page

    assert b"<h3>Mateo</h3>" in profile_page
    assert b"<h3>Jiwoo</h3>" in profile_page
    assert b"<h3>Wei</h3>" not in profile_page
    assert b"<h3>Sam</h3>" not in profile_page


@pytest.mark.parametrize(
    "mode,skills,expected",
    [
        ("learner", ("Spanish", "Guitar", "Graphic Design"), {"Mateo", "Jiwoo"}),
        ("sharer", ("Spanish", "Guitar", "Python"), {"Linh", "Mateo"}),
    ],
)
def test_multiple_skill_filters(
    authenticated_client, matching_data, skill_ids, mode, skills, expected
):
    """Match any selected skill and show each matching person once."""
    ids = [skill_ids[name] for name in skills]
    page = authenticated_client.get(
        "/dashboard",
        query_string={"mode": mode, "filter": "skill", "skill": [*ids, ids[0]]},
    ).get_data(as_text=True)
    for person in PEOPLE:
        name = person["name"]
        assert page.count(f"<h3>{name}</h3>") == int(name in expected)


def test_removing_one_skill_keeps_other_filters(authenticated_client, matching_data, skill_ids):
    spanish, design = skill_ids["Spanish"], skill_ids["Graphic Design"]
    page = authenticated_client.get(
        "/dashboard",
        query_string={
            "mode": "learner",
            "filter": "skill",
            "skill": [spanish, design],
            "remove_skill": spanish,
        },
    ).data
    assert b"<h3>Jiwoo</h3>" in page
    assert b"<h3>Mateo</h3>" not in page


def test_profile_save_preserves_listing_details(
    authenticated_client, app, user_id
):
    """Saving unchanged skills must preserve listing details and IDs."""
    from app import db
    from app.models import Listing

    authenticated_client.post(
        "/profile",
        data={"learns": ["Spanish"], "teaches": ["Python"]}
    )

    with app.app_context():
        listing = Listing.query.filter_by(
            user_id=user_id, type="learn"
        ).first()

        original_id = listing.id
        listing.level = "advanced"
        listing.description = "I want to practice conversation."
        db.session.commit()

    authenticated_client.post(
        "/profile",
        data={"learns": ["Spanish"], "teaches": ["Python"]}
    )

    with app.app_context():
        listing = Listing.query.filter_by(
            user_id=user_id, type="learn"
        ).first()

        assert listing.id == original_id
        assert listing.level == "advanced"
        assert listing.description == "I want to practice conversation."
