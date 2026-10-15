"""Database models for the skills marketplace (users, skills, listings)."""
import datetime as dt

from app import db


# Simple function to get the current UTC time. Used as a default value for created_at columns.
def utcnow():
    return dt.datetime.now(dt.timezone.utc)


# User table, has login info and profile info
class User(db.Model):
    __tablename__ = "users"  # "user" is a reserved word in PostgreSQL

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.Text)
    country_code = db.Column(db.String(2), index=True)  # ISO 3166, e.g. 'AR'
    timezone = db.Column(db.String(50), index=True)     # IANA name
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    listings = db.relationship("Listing", back_populates="user")


# Skill table, has info about possible skills that users can teach or learn. Each skill can have multiple listings.
class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

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
