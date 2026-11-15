from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.sample_data import MESSAGES
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app import db
from app.models import Category, Listing, Skill, User
from app.profile_forms import (
    COUNTRY_CODES, COUNTRY_OPTIONS, TIMEZONE_NAMES, TIMEZONE_OPTIONS,
    profile_values, validate_profile_details,
)

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
    """Update selected skills without replacing unchanged listings."""

    names = list(dict.fromkeys(
        name.strip()
        for name in skill_names
        if name and name.strip() and len(name.strip()) <= 100
    ))

    existing = Listing.query.filter_by(
        user_id=user.id,
        type=listing_type
    ).all()

    # Keep existing listings for skills that remain selected.
    existing_by_name = {
        listing.skill.name: listing for listing in existing
    }

    # Delete only skills the user actually removed.
    for name, listing in existing_by_name.items():
        if name not in names:
            db.session.delete(listing)

    # Add only newly selected skills.
    for name in names:
        if name in existing_by_name:
            continue

        # Skills come from the fixed catalog (see clean_selection), so none are created here.
        skill = Skill.query.filter_by(name=name).first()
        if skill is None:
            continue

        db.session.add(Listing(
            user_id=user.id,
            skill_id=skill.id,
            type=listing_type,
            is_active=True
        ))

    if commit:
        db.session.commit()


# Main user flow: sign up -> onboarding -> dashboard -> connect -> chat.
# Onboarding and profile skills are saved using the existing database models.
# The dashboard uses those saved skills to find matching users.


@main.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("main.login"))


# --- Accounts ---

@main.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.onboarding_learn"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not email or not username or not password:
            flash("Email, username, and password are required.", "error")
            return render_template("signup.html"), 400

        # Typing the password twice catches typos before the account is created.
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup.html"), 400

        existing_user = User.query.filter(
            or_(User.email == email, User.username == username)
        ).first()
        if existing_user:
            flash("That email or username is already registered.", "error")
            return render_template("signup.html"), 409

        user = User(email=email, username=username)
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
        # One box accepts either the email or the username, since people often forget one.
        # Emails are saved in lowercase (see signup), so compare the email in lowercase too.
        login_name = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter(
            or_(User.email == login_name.lower(), User.username == login_name)
        ).first() if login_name else None

        if user is None or not user.check_password(password):
            return render_template(
                "login.html", login_error="Invalid email/username or password."
            ), 401

        login_user(user)
        return redirect(url_for("main.dashboard"))

    return render_template("login.html")

@main.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.login"))

# --- Helper Functions ---
# Used in order to get skills and categories from the database to display in the onboarding and profile pages.


def get_categories():
    """The fixed catalog, for the pickers: every category with its skills."""
    return (Category.query.options(selectinload(Category.skills))
            .order_by(Category.name).all())


def only_catalog_skills(names):
    """Keep only names that exist in the catalog, so a hand-made POST can't add skills."""
    if not names:
        return []
    rows = db.session.query(Skill.name).filter(Skill.name.in_(names)).all()
    known = {name for (name,) in rows}
    return [name for name in names if name in known]


# Every picker (onboarding steps, profile) needs at least this many skills.
MIN_SKILLS = 3


def clean_selection(names):
    """What a user really picked: catalog skills only, each counted once, in the order sent.
    Counting once matters because the same skill can be submitted twice by a hand-made request."""
    return list(dict.fromkeys(only_catalog_skills(names)))


def min_skills_error(skills, purpose):
    """Error message when fewer than MIN_SKILLS were picked, otherwise None.
    purpose finishes the sentence, e.g. "to learn" or "to teach"."""
    if len(skills) >= MIN_SKILLS:
        return None
    return f"Pick at least {MIN_SKILLS} skills {purpose} (you picked {len(skills)})."


def search_skills(categories, query):
    """Skills whose name contains the text (any case), as (skill, category) pairs.
    It searches the categories already loaded for the picker, so it costs no extra query,
    and there is no LIKE pattern for the user to inject (a "%" is just a character)."""
    query = query.strip().lower()
    if not query:
        return []
    return [(skill, category) for category in categories for skill in category.skills
            if query in skill.name.lower()]


def picker_state(field, selected, categories, form=None, searching=False):
    """Everything the chip_picker macro needs for one picker.
    selected: skill names to show as checked. form: the submitted form when the page is
    re-rendered after a POST (None on a plain GET). The search text is only used when the
    user pressed Search; on any other submit it is ignored."""
    query = form.get(f"{field}_q", "").strip() if form is not None and searching else ""
    results = search_skills(categories, query)
    return {
        "selected": selected,
        "open_areas": form.getlist(f"{field}_areas") if form is not None else [],
        "query": query,
        "results": results,
        "result_ids": {skill.id for skill, _ in results},
    }

# --- Onboarding ---
# Both steps share onboarding.html; only the question, the field name and the next page change.

def onboarding_step(step, question, field, purpose, next_endpoint):
    """One onboarding step. A POST does one of two things, told apart by the button pressed:
    - Search (action=search): show the same step again with the matching skills, keeping the picks.
    - Continue: needs at least MIN_SKILLS picks, otherwise flash an error and show the step again."""
    categories = get_categories()
    listing_type = "learn" if field == "learns" else "teach"  # how Listing.type stores it

    def render(selected, searching=False, status=200):
        form = request.form if request.method == "POST" else None
        pickers = {field: picker_state(field, selected, categories, form, searching)}
        return render_template("onboarding.html", step=step, question=question, field=field,
                               categories=categories, pickers=pickers,
                               min_skills=MIN_SKILLS), status

    if request.method == "POST":
        chosen = clean_selection(request.form.getlist(field))
        if request.form.get("action") == "search":
            return render(chosen, searching=True)
        error = min_skills_error(chosen, purpose)
        if error is None:
            save_user_skills(current_user, listing_type, chosen)
            return redirect(url_for(next_endpoint))
        flash(error, "error")
        return render(chosen, status=400)  # the picks stay selected so they aren't lost
    return render(get_user_skills(current_user, listing_type))  # saved skills start selected


@main.route("/onboarding/learn", methods=["GET", "POST"])
@login_required
def onboarding_learn():
    return onboarding_step(1, "What do you want to learn?", "learns", "to learn",
                           "main.onboarding_teach")


@main.route("/onboarding/teach", methods=["GET", "POST"])
@login_required
def onboarding_teach():
    return onboarding_step(2, "What can you teach?", "teaches", "to teach", "main.dashboard")


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

    # Primary filter: Everyone ("default") or My Profile ("profile"); one is always selected.
    # Older links used filter=skill for By Skill; those now mean Everyone plus the picked skills.
    filter_mode = request.args.get("filter", "default")
    if filter_mode not in ("default", "profile"):
        filter_mode = "default"

    # Secondary filter: By Skill narrows the primary one. In My Profile, only my own
    # skills can be picked. Clicking a chip's x removes only that skill.
    picked = clean_selection(request.args.getlist("skill"))
    if filter_mode == "profile":
        picked = [skill for skill in picked if skill in my_skills]
    removed = request.args.get("remove_skill")
    if removed in picked:
        picked.remove(removed)

    if picked:
        wanted = picked            # people with at least one of the picked skills
    elif filter_mode == "profile":
        wanted = my_skills         # people matching my saved skills
    else:
        wanted = None              # everyone with an active listing

    # The By Skill list: every catalog skill for Everyone, only my own skills for My Profile.
    skill_groups = []
    for category in get_categories():
        names = [skill.name for skill in category.skills
                 if filter_mode != "profile" or skill.name in my_skills]
        if names:
            skill_groups.append((category.name, names))

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
        skill_groups=skill_groups,
        matches=matches
    )

# --- Profile ---

@main.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """The profile has two tabs, each with its own form:
    - details: bio, date of birth, country and timezone, saved on the account.
    - skills: the same pickers as onboarding; both lists need at least MIN_SKILLS skills.
    The hidden "section" field says which form was sent. The Search button in the skills
    tab re-renders the page without saving or validating."""
    active_tab = request.args.get("tab", "details")
    if active_tab not in ("details", "skills"):
        active_tab = "details"
    categories = get_categories()
    values = profile_values(current_user)
    errors = {}

    def render(learns, teaches, searching=False, status=200):
        # Search text and open areas only come from a submitted skills form
        sent_skills = request.method == "POST" and request.form.get("section", "skills") == "skills"
        form = request.form if sent_skills else None
        pickers = {"learns": picker_state("learns", learns, categories, form, searching),
                   "teaches": picker_state("teaches", teaches, categories, form, searching)}
        return render_template(
            "profile.html", user=current_user, active_tab=active_tab,
            values=values, errors=errors,
            country_options=COUNTRY_OPTIONS, country_codes=COUNTRY_CODES,
            timezone_options=TIMEZONE_OPTIONS, timezone_names=TIMEZONE_NAMES,
            today=date.today().isoformat(),
            categories=categories, pickers=pickers, min_skills=MIN_SKILLS,
        ), status

    if request.method == "POST":
        section = request.form.get("section", "skills")

        if section == "details":
            active_tab = "details"
            values, changes, errors = validate_profile_details(request.form, current_user)
            if not errors:
                for field, value in changes.items():
                    setattr(current_user, field, value)
                db.session.commit()
                flash("Profile saved.", "success")
                return redirect(url_for("main.profile", tab="details"))
            return render(get_user_skills(current_user, "learn"),
                          get_user_skills(current_user, "teach"), status=400)

        if section != "skills":
            abort(400)

        active_tab = "skills"
        learns = clean_selection(request.form.getlist("learns"))
        teaches = clean_selection(request.form.getlist("teaches"))
        if request.form.get("action") == "search":
            return render(learns, teaches, searching=True)

        skill_errors = [min_skills_error(learns, "to learn"), min_skills_error(teaches, "to teach")]
        skill_errors = [error for error in skill_errors if error]
        if skill_errors:
            for error in skill_errors:
                flash(error, "error")
            return render(learns, teaches, status=400)  # keep both lists as submitted

        # Save both lists for the signed-in account together, or neither if saving fails.
        try:
            save_user_skills(current_user, "learn", learns, commit=False)
            save_user_skills(current_user, "teach", teaches, commit=False)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        # "Save and filter by these" opens the Learner dashboard with My Profile filtering.
        if request.form.get("then") == "filter":
            return redirect(url_for("main.dashboard", mode="learner", filter="profile"))
        return redirect(url_for("main.dashboard"))

    # Show the details and skills saved for the signed-in account.
    return render(get_user_skills(current_user, "learn"), get_user_skills(current_user, "teach"))


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