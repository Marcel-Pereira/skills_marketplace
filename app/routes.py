from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.sample_data import SKILL_OPTIONS, CURRENT_USER, PEOPLE, MESSAGES
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import User, Skill, Listing

main = Blueprint("main", __name__)

def get_user_skills(user, listing_type):
    """Get the skills this user wants to learn or can teach."""

    listings = Listing.query.filter_by(
        user_id=user.id,
        type=listing_type,
        is_active=True
    ).all()

    return sorted(listing.skill.name for listing in listings)


def save_user_skills(user, listing_type, skill_names, commit=True):
    """Save a user's skills using the existing Skill and Listing tables."""

    # Remove duplicate or empty skill names.
    names = list(dict.fromkeys(
        name.strip()
        for name in skill_names
        if name.strip()
    ))

    # The Skill model allows names up to 100 characters.
    names = [name for name in names if len(name) <= 100]

    # Remove the user's previous listings of this type.
    # Their other type (learn or teach) is not affected.
    existing = Listing.query.filter_by(
        user_id=user.id,
        type=listing_type
    ).all()

    for listing in existing:
        db.session.delete(listing)

    db.session.flush()

    for name in names:
        # Reuse a skill if it already exists.
        skill = Skill.query.filter_by(name=name).first()

        if skill is None:
            skill = Skill(name=name)
            db.session.add(skill)
            db.session.flush()

        # Connect this user to this skill as a learner or teacher.
        db.session.add(
            Listing(
                user_id=user.id,
                skill_id=skill.id,
                type=listing_type,
                is_active=True
            )
        )

    # Allow the profile to save both categories in one transaction.
    if commit:
        db.session.commit()

# Main user flow: sign up -> onboarding -> dashboard -> connect -> chat.
# Onboarding and profile skills are saved using the existing database models.
# The dashboard uses those saved skills to find matching users.


@main.route("/")
def index():
    return render_template("index.html")


# --- Accounts ---

@main.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.onboarding_learn"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        bio = request.form.get("bio", "").strip() or None
        country_code = request.form.get("country_code", "").strip().upper() or None
        timezone = request.form.get("timezone", "").strip() or None

        if not email or not username or not password:
            flash("Email, username, and password are required.", "error")
            return render_template("signup.html"), 400

        existing_user = User.query.filter(
            or_(User.email == email, User.username == username)
        ).first()
        if existing_user:
            flash("That email or username is already registered.", "error")
            return render_template("signup.html"), 409

        user = User(
            email=email,
            username=username,
            bio=bio,
            country_code=country_code,
            timezone=timezone,
        )
        user.set_password(password)
        db.session.add(user)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("That email or username is already registered.", "error")
            return render_template("signup.html"), 409

        login_user(user)
        return redirect(url_for("main.onboarding_learn"))

    return render_template("signup.html")

@main.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("login.html"), 401

        login_user(user)
        return redirect(url_for("main.dashboard"))

    return render_template("login.html")

@main.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.login"))

# --- Onboarding ---
# Both steps share onboarding.html; only the question, the field name and the next page change.

@main.route("/onboarding/learn", methods=["GET", "POST"])
@login_required
def onboarding_learn():
    """Save the skills the current user wants to learn."""

    if request.method == "POST":
        # Save these skills for the signed-in user.
        save_user_skills(
            current_user,
            "learn",
            request.form.getlist("learns")
        )

        return redirect(url_for("main.onboarding_teach"))

    return render_template(
        "onboarding.html",
        step=1,
        question="What do you want to learn?",
        field="learns",
        options=SKILL_OPTIONS
    )


@main.route("/onboarding/teach", methods=["GET", "POST"])
@login_required
def onboarding_teach():
    """Save the skills the current user can teach."""

    if request.method == "POST":
        # Save teaching skills separately from learning skills.
        save_user_skills(
            current_user,
            "teach",
            request.form.getlist("teaches")
        )

        return redirect(url_for("main.dashboard"))

    return render_template(
        "onboarding.html",
        step=2,
        question="What can you teach?",
        field="teaches",
        options=SKILL_OPTIONS
    )


# --- Dashboard ---

@main.route("/dashboard")
@login_required
def dashboard():
    """Find people whose skills match the signed-in user's interests."""

    mode = request.args.get("mode", "learner")
    if mode not in ("learner", "sharer"):
        mode = "learner"

    # Learners look for teachers. Sharers look for learners.
    if mode == "sharer":
        my_skills = get_user_skills(current_user, "teach")
        their_type = "learn"
    else:
        my_skills = get_user_skills(current_user, "learn")
        their_type = "teach"

    # Choose how to filter people on the Learner or Sharer dashboard.
    filter_mode = request.args.get("filter", "default")

    if filter_mode not in ("default", "skill", "profile"):
        filter_mode = "default"

    # Keep supporting the MVP's existing ?skill=... links.
    picked = request.args.getlist("skill")


    if filter_mode == "skill" or (filter_mode == "default" and picked):
        # By Skill: show people offering/requesting the selected skill.
        # Keep compatibility with the MVP's existing ?skill=... links.
        selected_skill = picked[0] if picked else ""
        wanted = [selected_skill] if selected_skill else []
        picked = [selected_skill] if selected_skill else []

    elif filter_mode == "profile":
        # My Profile: use skills saved in the signed-in user's profile.
        wanted = my_skills
        picked = []

    else:
        # Default: show all active listings in the chosen direction.
        wanted = None
        picked = []

    # Find active listings from other users in the database.
    listings = Listing.query.filter(
        Listing.type == their_type,
        Listing.is_active.is_(True),
        Listing.user_id != current_user.id
    ).all()

    matches_by_user = {}

    for listing in listings:
        skill_name = listing.skill.name

        # In filtered views, skip skills outside the selected set.
        # Default browsing has no skill restriction.
        # Hide people without a matching skill in every filter mode.
        if wanted is not None and skill_name not in wanted:
            continue

        user = listing.user

        # Show each matching person only once, even if several skills match.
        if user.id not in matches_by_user:
            matches_by_user[user.id] = {
                "person": {
                    "name": user.username,
                    "teaches": get_user_skills(user, "teach"),
                    "learns": get_user_skills(user, "learn"),
                },
                "shared": [],
                "profile_shared": [],
            }

        # Highlight only genuine profile matches, even in Default browsing.
        # Display the skills relevant to the selected filter.
        matches_by_user[user.id]["shared"].append(skill_name)

        # Highlight skills that also match the signed-in user's profile.
        if skill_name in my_skills:
            matches_by_user[user.id]["profile_shared"].append(skill_name)

    matches = list(matches_by_user.values())

    # People with more matching skills appear first.
    matches.sort(
        key=lambda match: (
            -len(match["shared"]),
            match["person"]["name"].lower()
        )
    )

    return render_template(
        "dashboard.html",
        mode=mode,
        filter_mode=filter_mode,
        picked=picked,
        skills=SKILL_OPTIONS,
        matches=matches
    )

# --- Profile ---

@main.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """View and update the signed-in user's learning and teaching skills."""

    if request.method == "POST":
        # Save the skills for the current account, not a shared sample user.
        # Save both skill categories together, or neither if saving fails.
        try:
            save_user_skills(
                current_user,
                "learn",
                request.form.getlist("learns"),
                commit=False
            )

            save_user_skills(
                current_user,
                "teach",
                request.form.getlist("teaches"),
                commit=False
            )

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        # Open the dashboard using the skills saved in this profile.
        # Open the Learner dashboard with My Profile filtering selected.
        if request.form.get("then") == "filter":
            return redirect(
                url_for("main.dashboard", mode="learner", filter="profile")
            )

        return redirect(url_for("main.dashboard"))

    # Read the saved skills belonging to the signed-in user.
    profile_data = {
        "name": current_user.username,
        "learns": get_user_skills(current_user, "learn"),
        "teaches": get_user_skills(current_user, "teach"),
    }

    return render_template(
        "profile.html",
        user=profile_data,
        options=SKILL_OPTIONS
    )


# --- Messages ---

@main.route("/messages")
@login_required
def messages():
    """Everyone I have a chat with."""
    return render_template("messages.html", conversations=MESSAGES)


@main.route("/chat/<name>", methods=["GET", "POST"])
@login_required
def chat(name):
    """My chat with one person. "Connect" on the dashboard opens this page."""
    # Check that the person exists in the database.
    # The dashboard now displays real users instead of sample people.
    other_user = User.query.filter_by(username=name).first()

    if other_user is None or other_user.id == current_user.id:
        abort(404)

    # Start an empty chat the first time someone connects
    conversation = MESSAGES.setdefault(name, [])

    if request.method == "POST":
        # Messages are only kept in memory for now, so they disappear when the server restarts
        conversation.append({"sender": "You", "text": request.form["text"]})
        # Redirect after sending, so refreshing the page doesn't send the message twice
        return redirect(url_for("main.chat", name=name))

    return render_template("chat.html", name=name, conversation=conversation)
