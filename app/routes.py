from flask import Blueprint, render_template, request, redirect, url_for

from app.sample_data import SKILL_OPTIONS, CURRENT_USER, PEOPLE

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
