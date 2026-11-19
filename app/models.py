"""Database models for the skills marketplace (users, skills, listings)."""
import datetime as dt

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, login_manager


# Simple function to get the current UTC time. Used as a default value for created_at columns.
def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def calculate_age(date_of_birth, today=None):
    """Return completed years as of today, or None when no birthday is set."""
    if date_of_birth is None:
        return None
    today = today or dt.date.today()
    birthday_pending = (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    return today.year - date_of_birth.year - birthday_pending


# User table, has login info and profile info
class User(UserMixin, db.Model):
    __tablename__ = "users"  # "user" is a reserved word in PostgreSQL
    __table_args__ = (
        db.CheckConstraint("points >= 0", name="ck_users_points"),
        db.CheckConstraint(
            "reserved_points >= 0 AND reserved_points <= points",
            name="ck_users_reserved_points",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.Text)
    country_code = db.Column(db.String(2), index=True)  # ISO 3166, e.g. 'AR'
    timezone = db.Column(db.String(50), index=True)     # IANA name
    date_of_birth = db.Column(db.Date)
    points = db.Column(db.Integer, nullable=False, default=3, server_default="3")
    reserved_points = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    listings = db.relationship("Listing", back_populates="user")

    @property
    def age(self):
        return calculate_age(self.date_of_birth)

    @property
    def available_points(self):
        return self.points - self.reserved_points

    def set_password(self, password):
        """Hash a plaintext password before storing it."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Return whether a plaintext password matches the stored hash."""
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    """Restore the signed-in user from the ID saved in the Flask session."""
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


# Category table, each category can have many skills
class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)

    skills = db.relationship("Skill", back_populates="category", order_by="Skill.name")


# Skill table, each skill belongs to a category and can have many listings
class Skill(db.Model):
    __tablename__ = "skills"
    __table_args__ = (
        db.UniqueConstraint("category_id", "name", name="uq_skill_category_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"),
                            nullable=False, index=True)

    category = db.relationship("Category", back_populates="skills")
    listings = db.relationship("Listing", back_populates="skill")


# Listing table. Has info about posted teaching or learning listings. Each listing is associated with a user and a skill.
class Listing(db.Model):
    __tablename__ = "listings"
    __table_args__ = (
        db.UniqueConstraint("user_id", "skill_id", "type", name="uq_listing_user_skill_type"),
        db.CheckConstraint("type IN ('teach', 'learn')", name="ck_listing_type"),
        db.CheckConstraint(
            "level IN ('beginner', 'intermediate', 'advanced')", name="ck_listing_level"
        ),
        db.Index("ix_listings_skill_type", "skill_id", "type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), nullable=False)
    type = db.Column(db.String(5), nullable=False)  # 'teach' or 'learn'
    level = db.Column(db.String(12))
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="listings")
    skill = db.relationship("Skill", back_populates="listings")


class Lesson(db.Model):
    """A booked lesson reserves one learner point until completion or cancellation."""

    __tablename__ = "lessons"
    __table_args__ = (
        db.CheckConstraint("teacher_id != learner_id", name="ck_lesson_participants"),
        db.CheckConstraint(
            "status IN ('scheduled', 'completed', 'cancelled')", name="ck_lesson_status"
        ),
        db.CheckConstraint(
            "status != 'completed' OR (teacher_confirmed_at IS NOT NULL "
            "AND learner_confirmed_at IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_lesson_completion",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    learner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="scheduled")
    booking_key = db.Column(db.String(36), nullable=False, unique=True)
    teacher_confirmed_at = db.Column(db.DateTime)
    learner_confirmed_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    teacher = db.relationship("User", foreign_keys=[teacher_id])
    learner = db.relationship("User", foreign_keys=[learner_id])
    skill = db.relationship("Skill")

    @property
    def can_confirm(self):
        return self.status == "scheduled" and self.scheduled_at <= utcnow().replace(tzinfo=None)
