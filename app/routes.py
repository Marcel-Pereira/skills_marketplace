from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app import db
from app.models import Category, Listing, Skill, User
from app.sample_data import MESSAGES

main = Blueprint("main", __name__)


def get_categories():
    """Load the shared catalog and its alphabetically sorted skills."""
    return (Category.query.options(selectinload(Category.skills))
            .order_by(Category.name).all())


def catalog_skill_ids(values):
    """Validate selections without creating skills or guessing ambiguous names.

    New forms use IDs. Unique names from older forms and links still work.
    """
    skills = Skill.query.all()
    by_id = {str(skill.id): skill.id for skill in skills}
    by_name = {}
    for skill in skills:
        by_name.setdefault(skill.name, []).append(skill.id)

    selected = set()
    for value in values:
        value = value.strip()
        if not value:
            continue
        if value in by_id:
            selected.add(by_id[value])
        elif len(by_name.get(value, [])) == 1:
            selected.add(by_name[value][0])
        else:
            raise ValueError("Choose skills from the available list.")
    return selected


def get_user_skill_ids(user, listing_type):
    """Return this account's active learning or teaching selections."""
    return {listing.skill_id for listing in Listing.query.filter_by(
        user_id=user.id, type=listing_type, is_active=True
    ).all()}


def save_user_skills(user, listing_type, skill_ids, commit=True):
    """Apply validated catalog IDs while keeping existing listing details."""
    existing = {listing.skill_id: listing for listing in Listing.query.filter_by(
        user_id=user.id, type=listing_type
    ).all()}

    # Deactivate removed choices so reselecting them restores their details.
    for skill_id, listing in existing.items():
        listing.is_active = skill_id in skill_ids

    for skill_id in skill_ids - existing.keys():
        db.session.add(Listing(
            user_id=user.id, skill_id=skill_id,
            type=listing_type, is_active=True
        ))

    if commit:
        db.session.commit()


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

@main.route("/onboarding/learn", methods=["GET", "POST"])
@login_required
def onboarding_learn():
    """Save only approved learning skills for the signed-in account."""
    status = 200
    if request.method == "POST":
        try:
            selected = catalog_skill_ids(request.form.getlist("learns"))
        except ValueError as error:
            flash(str(error), "error")
            status = 400
        else:
            save_user_skills(current_user, "learn", selected)
            return redirect(url_for("main.onboarding_teach"))

    return render_template(
        "onboarding.html", step=1, question="What do you want to learn?",
        field="learns", categories=get_categories(),
        selected=get_user_skill_ids(current_user, "learn")
    ), status


@main.route("/onboarding/teach", methods=["GET", "POST"])
@login_required
def onboarding_teach():
    """Save approved teaching skills without changing learning selections."""
    status = 200
    if request.method == "POST":
        try:
            selected = catalog_skill_ids(request.form.getlist("teaches"))
        except ValueError as error:
            flash(str(error), "error")
            status = 400
        else:
            save_user_skills(current_user, "teach", selected)
            return redirect(url_for("main.dashboard"))

    return render_template(
        "onboarding.html", step=2, question="What can you teach?",
        field="teaches", categories=get_categories(),
        selected=get_user_skill_ids(current_user, "teach")
    ), status


# --- Dashboard ---

@main.route("/dashboard")
@login_required
def dashboard():
    """Match active listings using catalog IDs in either learning direction."""
    mode = request.args.get("mode", "learner")
    if mode not in ("learner", "sharer"):
        mode = "learner"

    my_type, their_type = ("teach", "learn") if mode == "sharer" else ("learn", "teach")
    my_skills = get_user_skill_ids(current_user, my_type)
    filter_mode = request.args.get("filter", "default")
    if filter_mode not in ("default", "skill", "profile"):
        filter_mode = "default"

    picked = []
    # Keep older ?skill=Spanish links working when the name is unambiguous.
    if filter_mode == "skill" or (filter_mode == "default" and request.args.get("skill")):
        filter_mode = "skill"
        try:
            picked = sorted(catalog_skill_ids([request.args.get("skill", "")]))
        except ValueError:
            pass  # An unknown or ambiguous selection must not show everyone.
        wanted = set(picked)
    elif filter_mode == "profile":
        wanted = my_skills
    else:
        wanted = None

    listings = Listing.query.filter(
        Listing.type == their_type, Listing.is_active.is_(True),
        Listing.user_id != current_user.id
    ).options(selectinload(Listing.skill), selectinload(Listing.user))
    if wanted is not None:
        listings = listings.filter(Listing.skill_id.in_(wanted))

    matches_by_user = {}
    for listing in listings.all():
        match = matches_by_user.setdefault(listing.user_id, {
            "person": {"name": listing.user.username},
            "shared": [], "profile_shared": my_skills,
        })
        match["shared"].append(listing.skill)

    matches = sorted(matches_by_user.values(), key=lambda match: (
        -len(match["shared"]), match["person"]["name"].lower()
    ))
    return render_template(
        "dashboard.html", mode=mode, filter_mode=filter_mode,
        picked=picked, categories=get_categories(), matches=matches
    )


# --- Profile ---

@main.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Validate both selections before updating either set of saved skills."""
    status = 200
    if request.method == "POST":
        try:
            learns = catalog_skill_ids(request.form.getlist("learns"))
            teaches = catalog_skill_ids(request.form.getlist("teaches"))
        except ValueError as error:
            flash(str(error), "error")
            status = 400
        else:
            try:
                save_user_skills(current_user, "learn", learns, commit=False)
                save_user_skills(current_user, "teach", teaches, commit=False)
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            if request.form.get("then") == "filter":
                return redirect(url_for("main.dashboard", mode="learner", filter="profile"))
            return redirect(url_for("main.dashboard"))

    profile_data = {
        "name": current_user.username,
        "learns": get_user_skill_ids(current_user, "learn"),
        "teaches": get_user_skill_ids(current_user, "teach"),
    }
    return render_template(
        "profile.html", user=profile_data, categories=get_categories()
    ), status


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
