from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import User

main = Blueprint("main", __name__)


@main.route("/")
def index():
    return render_template("index.html")


@main.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.logged_in"))

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
        return redirect(url_for("main.logged_in"))

    return render_template("signup.html")


@main.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.logged_in"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return render_template("login.html"), 401

        login_user(user)
        return redirect(url_for("main.logged_in"))

    return render_template("login.html")


@main.route("/logged-in")
@login_required
def logged_in():
    return render_template("logged_in.html")


@main.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.login"))
