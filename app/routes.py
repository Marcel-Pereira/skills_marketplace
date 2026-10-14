from flask import Blueprint, render_template, request, redirect, url_for, abort

from app.sample_data import SKILL_OPTIONS, CURRENT_USER, PEOPLE, MESSAGES

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
    if request.method == "POST":
        # A new user counts as logged in, so they go straight to onboarding
        return redirect(url_for("main.onboarding_learn"))
    return render_template("signup.html")


@main.route("/signin", methods=["GET", "POST"])
def signin():
    if request.method == "POST":
        return redirect(url_for("main.dashboard"))
    return render_template("signin.html")


# --- Onboarding ---
# Both steps share onboarding.html; only the question, the field name and the next page change.

@main.route("/onboarding/learn", methods=["GET", "POST"])
def onboarding_learn():
    if request.method == "POST":
        return redirect(url_for("main.onboarding_teach"))
    return render_template("onboarding.html", step=1, question="What do you want to learn?",
                           field="learns", options=SKILL_OPTIONS)


@main.route("/onboarding/teach", methods=["GET", "POST"])
def onboarding_teach():
    if request.method == "POST":
        return redirect(url_for("main.dashboard"))
    return render_template("onboarding.html", step=2, question="What can you teach?",
                           field="teaches", options=SKILL_OPTIONS)


# --- Dashboard ---

@main.route("/dashboard")
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


# --- Profile ---

@main.route("/profile", methods=["GET", "POST"])
def profile():
    """Change what you picked during onboarding. Uses the same chip pickers, pre-selected."""
    if request.method == "POST":
        # Kept in memory for now (like chat messages), so changes are lost when the server restarts
        CURRENT_USER["learns"] = request.form.getlist("learns")
        CURRENT_USER["teaches"] = request.form.getlist("teaches")

        # "Save and filter by these" opens the dashboard already filtered by what I want to learn
        if request.form.get("then") == "filter":
            return redirect(url_for("main.dashboard", mode="learner", skill=CURRENT_USER["learns"]))
        return redirect(url_for("main.dashboard"))
    return render_template("profile.html", user=CURRENT_USER, options=SKILL_OPTIONS)
