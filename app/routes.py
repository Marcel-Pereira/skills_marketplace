from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.sample_data import CURRENT_USER, PEOPLE, MESSAGES
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app import db
from app.models import Category, Skill, User

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
            return redirect(url_for(next_endpoint))
        flash(error, "error")
        return render(chosen, status=400)  # the picks stay selected so they aren't lost
    return render([])


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
                           categories=get_categories(), matches=matches)


# --- Profile ---

@main.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Change what you picked during onboarding. Uses the same chip pickers, pre-selected.
    Both lists need at least MIN_SKILLS skills; nothing is saved unless both do.
    The Search button re-renders the page without saving or validating."""
    categories = get_categories()

    def render(learns, teaches, searching=False, status=200):
        form = request.form if request.method == "POST" else None
        pickers = {"learns": picker_state("learns", learns, categories, form, searching),
                   "teaches": picker_state("teaches", teaches, categories, form, searching)}
        return render_template("profile.html", user=CURRENT_USER, categories=categories,
                               pickers=pickers, min_skills=MIN_SKILLS), status

    if request.method == "POST":
        learns = clean_selection(request.form.getlist("learns"))
        teaches = clean_selection(request.form.getlist("teaches"))
        if request.form.get("action") == "search":
            return render(learns, teaches, searching=True)

        errors = [min_skills_error(learns, "to learn"), min_skills_error(teaches, "to teach")]
        errors = [error for error in errors if error]
        if errors:
            for error in errors:
                flash(error, "error")
            return render(learns, teaches, status=400)  # keep both lists as submitted

        # Kept in memory for now (like chat messages), so changes are lost when the server restarts
        CURRENT_USER["learns"] = learns
        CURRENT_USER["teaches"] = teaches

        # "Save and filter by these" opens the dashboard already filtered by what I want to learn
        if request.form.get("then") == "filter":
            return redirect(url_for("main.dashboard", mode="learner", skill=CURRENT_USER["learns"]))
        return redirect(url_for("main.dashboard"))
    return render(CURRENT_USER["learns"], CURRENT_USER["teaches"])


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
    if name not in [person["name"] for person in PEOPLE]:
        abort(404)

    # Start an empty chat the first time someone connects
    conversation = MESSAGES.setdefault(name, [])

    if request.method == "POST":
        # Messages are only kept in memory for now, so they disappear when the server restarts
        conversation.append({"sender": "You", "text": request.form["text"]})
        # Redirect after sending, so refreshing the page doesn't send the message twice
        return redirect(url_for("main.chat", name=name))

    return render_template("chat.html", name=name, conversation=conversation)