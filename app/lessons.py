"""Lesson booking and points transfers shared with the messaging feature."""
from datetime import datetime, timezone
from secrets import compare_digest, token_urlsafe
from uuid import UUID, uuid4

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app import db
from app.models import Lesson, Listing, Skill, User

lessons = Blueprint("lessons", __name__, url_prefix="/lessons")


@lessons.context_processor
def lesson_form_context():
    """Bind point-changing forms to the signed-in browser session."""
    if "lesson_form_token" not in session:
        session["lesson_form_token"] = token_urlsafe(32)
    return {"lesson_form_token": session["lesson_form_token"]}


@lessons.before_request
def protect_lesson_forms():
    if request.method == "POST" and current_user.is_authenticated:
        expected = session.get("lesson_form_token", "")
        supplied = request.form.get("lesson_form_token", "")
        if not expected or not compare_digest(expected.encode(), supplied.encode()):
            abort(400, description="Open the lessons page again and try the form once more.")


def now_utc():
    """Use naive UTC values consistently with database DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def lesson_for_user(lesson_id, user_id):
    lesson = db.session.get(Lesson, lesson_id)
    if lesson is None or user_id not in (lesson.teacher_id, lesson.learner_id):
        abort(404)
    return lesson


def existing_booking(booking_key, learner_id, teacher_id, skill_id, scheduled_at):
    """Return a retried booking only when all of its details match."""
    lesson = Lesson.query.filter_by(booking_key=booking_key).first()
    if lesson is not None and (
        lesson.learner_id, lesson.teacher_id, lesson.skill_id, lesson.scheduled_at
    ) != (learner_id, teacher_id, skill_id, scheduled_at):
        raise ValueError("Open the booking form again to book a different lesson.")
    return lesson


def schedule_lesson(learner_id, teacher_id, skill_id, scheduled_at, booking_key):
    """Reserve a learner's point and save a lesson together; retries keep one booking."""
    booking_key = str(UUID(booking_key))
    if scheduled_at.tzinfo is not None:
        scheduled_at = scheduled_at.astimezone(timezone.utc).replace(tzinfo=None)
    existing = existing_booking(booking_key, learner_id, teacher_id, skill_id, scheduled_at)
    if existing is not None:
        return existing
    if learner_id == teacher_id:
        raise ValueError("Choose another person to teach you.")
    if scheduled_at <= now_utc():
        raise ValueError("Choose a future lesson time.")
    if db.session.get(User, teacher_id) is None or db.session.get(User, learner_id) is None:
        raise ValueError("Choose an existing teacher and learner.")
    offered = Listing.query.filter_by(
        user_id=teacher_id, skill_id=skill_id, type="teach", is_active=True
    ).first()
    if offered is None:
        raise ValueError("Choose a skill this person currently teaches.")

    try:
        reservation = db.session.execute(
            update(User).where(User.id == learner_id, User.points > User.reserved_points)
            .values(reserved_points=User.reserved_points + 1)
        )
        if reservation.rowcount != 1:
            db.session.rollback()
            existing = existing_booking(
                booking_key, learner_id, teacher_id, skill_id, scheduled_at
            )
            if existing is not None:
                return existing
            raise ValueError("You need one available point to book a lesson.")
        lesson = Lesson(
            learner_id=learner_id, teacher_id=teacher_id, skill_id=skill_id,
            scheduled_at=scheduled_at, booking_key=booking_key,
        )
        db.session.add(lesson)
        db.session.commit()
        return lesson
    except IntegrityError:
        # A simultaneous retry may have inserted the same unique booking key.
        db.session.rollback()
        existing = existing_booking(booking_key, learner_id, teacher_id, skill_id, scheduled_at)
        if existing is not None:
            return existing
        raise
    except Exception:
        db.session.rollback()
        raise


def confirm_lesson(lesson_id, user_id):
    """Record one participant's confirmation and pay exactly once when both agree."""
    lesson = lesson_for_user(lesson_id, user_id)
    confirmation = Lesson.learner_confirmed_at
    if user_id == lesson.teacher_id:
        confirmation = Lesson.teacher_confirmed_at
    now = now_utc()
    try:
        # This write serializes competing confirmation/cancellation requests.
        db.session.execute(
            update(Lesson).where(
                Lesson.id == lesson_id, Lesson.status == "scheduled",
                Lesson.scheduled_at <= now, confirmation.is_(None),
            ).values({confirmation: now})
        )
        lesson = db.session.get(Lesson, lesson_id, populate_existing=True)
        if lesson.status == "cancelled":
            raise ValueError("This lesson was cancelled.")
        if lesson.scheduled_at > now:
            raise ValueError("Confirm after the scheduled lesson time.")

        completion = db.session.execute(
            update(Lesson).where(
                Lesson.id == lesson_id, Lesson.status == "scheduled",
                Lesson.teacher_confirmed_at.is_not(None),
                Lesson.learner_confirmed_at.is_not(None),
            ).values(status="completed", completed_at=now)
        )
        if completion.rowcount == 1:
            # Consistent user order also avoids deadlocks on databases with row locks.
            db.session.execute(
                db.select(User.id).where(User.id.in_([lesson.learner_id, lesson.teacher_id]))
                .order_by(User.id).with_for_update()
            ).all()
            debit = db.session.execute(
                update(User).where(
                    User.id == lesson.learner_id, User.points >= 1, User.reserved_points >= 1,
                ).values(points=User.points - 1, reserved_points=User.reserved_points - 1)
            )
            credit = db.session.execute(
                update(User).where(User.id == lesson.teacher_id).values(points=User.points + 1)
            )
            if debit.rowcount != 1 or credit.rowcount != 1:
                raise ValueError("The reserved point could not be transferred. Please try again.")
        db.session.commit()
        return lesson
    except Exception:
        db.session.rollback()
        raise


def cancel_lesson(lesson_id, user_id):
    """Either participant can cancel before any confirmation and release the point."""
    lesson = lesson_for_user(lesson_id, user_id)
    try:
        cancellation = db.session.execute(
            update(Lesson).where(
                Lesson.id == lesson_id, Lesson.status == "scheduled",
                Lesson.teacher_confirmed_at.is_(None), Lesson.learner_confirmed_at.is_(None),
            ).values(status="cancelled")
        )
        if cancellation.rowcount == 1:
            release = db.session.execute(
                update(User).where(User.id == lesson.learner_id, User.reserved_points >= 1)
                .values(reserved_points=User.reserved_points - 1)
            )
            if release.rowcount != 1:
                raise ValueError("The reserved point could not be released. Please try again.")
        else:
            lesson = db.session.get(Lesson, lesson_id, populate_existing=True)
            if lesson.status != "cancelled":
                raise ValueError("A lesson can only be cancelled before either person confirms.")
        db.session.commit()
        return lesson
    except Exception:
        db.session.rollback()
        raise


@lessons.get("")
@login_required
def index():
    saved_lessons = Lesson.query.filter(or_(
        Lesson.teacher_id == current_user.id, Lesson.learner_id == current_user.id,
    )).options(
        selectinload(Lesson.teacher), selectinload(Lesson.learner), selectinload(Lesson.skill),
    ).order_by(Lesson.scheduled_at.desc(), Lesson.id.desc()).all()
    return render_template("lessons.html", lessons=saved_lessons, now=now_utc())


@lessons.route("/book/<int:teacher_id>", methods=["GET", "POST"])
@login_required
def book(teacher_id):
    teacher = db.get_or_404(User, teacher_id)
    if teacher_id == current_user.id:
        abort(404)
    skills = Skill.query.join(Listing).filter(
        Listing.user_id == teacher_id, Listing.type == "teach", Listing.is_active.is_(True),
    ).order_by(Skill.name).all()
    values = request.form
    booking_key = values.get("booking_key") or str(uuid4())
    status = 200
    if request.method == "POST":
        try:
            scheduled_at = datetime.strptime(values.get("scheduled_at", ""), "%Y-%m-%dT%H:%M")
            skill_id = int(values.get("skill_id", ""))
            booking_key = str(UUID(values.get("booking_key", "")))
        except ValueError:
            flash("Choose a skill and a valid lesson time, then try again.", "error")
            booking_key = str(uuid4())
            status = 400
        else:
            try:
                schedule_lesson(current_user.id, teacher_id, skill_id, scheduled_at, booking_key)
            except ValueError as error:
                flash(str(error), "error")
                status = 400
            else:
                flash("Your booking is saved. Its status and points are shown below.", "success")
                return redirect(url_for("lessons.index"))
    return render_template(
        "book_lesson.html", teacher=teacher, skills=skills, values=values,
        booking_key=booking_key, min_time=now_utc().strftime("%Y-%m-%dT%H:%M"),
    ), status


@lessons.post("/<int:lesson_id>/confirm")
@login_required
def confirm(lesson_id):
    try:
        lesson = confirm_lesson(lesson_id, current_user.id)
    except ValueError as error:
        flash(str(error), "error")
        return index(), 400
    if lesson.status == "completed":
        flash("Lesson completed. One point moved from the learner to the teacher.", "success")
    else:
        flash("Your confirmation is saved. Waiting for the other person.", "success")
    return redirect(url_for("lessons.index"))


@lessons.post("/<int:lesson_id>/cancel")
@login_required
def cancel(lesson_id):
    try:
        cancel_lesson(lesson_id, current_user.id)
    except ValueError as error:
        flash(str(error), "error")
        return index(), 400
    flash("Lesson cancelled. The reserved point is available again.", "success")
    return redirect(url_for("lessons.index"))
