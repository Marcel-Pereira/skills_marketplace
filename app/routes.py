from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.sample_data import SKILL_OPTIONS, CURRENT_USER, PEOPLE
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import User

main = Blueprint("main", __name__)

# The user flow is: sign up -> onboarding (learn, then teach) -> dashboard -> connect -> chat.
# Profile and Messages are reachable from the nav once signed in.
# Forms don't save anything yet. Each POST just moves to the next screen;
# saving users and their skills gets added here once the database models exist.


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


# --- Onboarding ---
# Both steps share onboarding.html; only the question, the field name and the next page change.

@main.route("/onboarding/learn", methods=["GET", "POST"])
@login_required
def onboarding_learn():
    if request.method == "POST":
        return redirect(url_for("main.onboarding_teach"))
    return render_template("onboarding.html", step=1, question="What do you want to learn?",
                           field="learns", options=SKILL_OPTIONS)


@main.route("/onboarding/teach", methods=["GET", "POST"])
@login_required
def onboarding_teach():
    if request.method == "POST":
        return redirect(url_for("main.dashboard"))
    return render_template("onboarding.html", step=2, question="What can you teach?",
                           field="teaches", options=SKILL_OPTIONS)


# --- Dashboard ---

@main.route("/dashboard")
@login_required
def dashboard():
    """Find people to pair with. The page has two modes, switched with ?mode= in the URL:
    - learner: looking for people who can teach me
    - sharer: looking for people who want to learn from me
    With no skills picked it shows everyone, best matches for my own skills first.
    With skills picked (?skill=Spanish&skill=Guitar) it only shows people who teach (learner)
    or want to learn (sharer) at least one of them."""
    mode = request.args.get("mode", "learner")
    picked = request.args.getlist("skill")  # getlist because several skills can be picked

    # In learner mode my "learns" list is matched against their "teaches" list, and the other way round
    if mode == "sharer":
        my_skills, their_list = CURRENT_USER["teaches"], "learns"
    else:
        my_skills, their_list = CURRENT_USER["learns"], "teaches"
    wanted = picked if picked else my_skills

    matches = []
    for person in PEOPLE:
        shared = [s for s in person[their_list] if s in wanted]
        if picked and not shared:
            continue  # skills were picked and this person has none of them
        matches.append({"person": person, "shared": shared})

    # Best pairs first: people who share more skills with me
    matches.sort(key=lambda match: len(match["shared"]), reverse=True)

    return render_template("dashboard.html", mode=mode, picked=picked,
                           skills=SKILL_OPTIONS, matches=matches)

@main.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.login"))
