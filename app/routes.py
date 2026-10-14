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
