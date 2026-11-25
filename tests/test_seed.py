"""Tests for the fixed catalog (issue #19): Category/Skill constraints and seed_skills()."""
import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Category, Skill
from app.seed import CATALOG, seed_skills


# --- CATALOG data ---------------------------------------------------------

def test_catalog_has_no_duplicate_skill_names_within_a_category():
    """seed_skills() skips names it already has, so a duplicate would be silently dropped."""
    for category_name, skill_names in CATALOG.items():
        assert len(skill_names) == len(set(skill_names)), category_name


# --- seed_skills() --------------------------------------------------------

def test_seed_loads_every_category_and_skill(app):
    with app.app_context():
        seed_skills()

        assert Category.query.count() == len(CATALOG)
        assert Skill.query.count() == sum(len(names) for names in CATALOG.values())


def test_seed_puts_each_skill_in_the_right_category(app):
    with app.app_context():
        seed_skills()

        for category_name, skill_names in CATALOG.items():
            category = Category.query.filter_by(name=category_name).one()
            assert sorted(s.name for s in category.skills) == sorted(skill_names)


def test_seed_is_idempotent(app):
    """Running the command twice must not create duplicates or fail."""
    with app.app_context():
        seed_skills()
        categories, skills = Category.query.count(), Skill.query.count()

        seed_skills()

        assert Category.query.count() == categories
        assert Skill.query.count() == skills


def test_seed_restores_only_what_is_missing(app):
    """Deleting a skill and re-seeding brings it back without touching the rest."""
    with app.app_context():
        seed_skills()
        total = Skill.query.count()
        kept = Skill.query.filter_by(name="Python").one()
        kept_id = kept.id
        db.session.delete(Skill.query.filter_by(name="Flask").one())
        db.session.commit()

        seed_skills()

        assert Skill.query.count() == total
        assert Skill.query.filter_by(name="Flask").count() == 1
        assert db.session.get(Skill, kept_id).name == "Python"  # same row, not recreated


def test_seed_cli_command(app):
    result = app.test_cli_runner().invoke(args=["seed"])

    assert result.exit_code == 0
    assert "Seeded" in result.output
    with app.app_context():
        assert Category.query.count() == len(CATALOG)


# --- Model constraints ----------------------------------------------------

def test_category_name_must_be_unique(app):
    with app.app_context():
        db.session.add(Category(name="Music"))
        db.session.commit()

        db.session.add(Category(name="Music"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_skill_requires_a_category(app):
    with app.app_context():
        db.session.add(Skill(name="Orphan skill"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_skill_name_must_be_unique_within_a_category(app):
    with app.app_context():
        category = Category(name="Music")
        db.session.add(category)
        db.session.commit()
        db.session.add(Skill(name="Guitar", category_id=category.id))
        db.session.commit()

        db.session.add(Skill(name="Guitar", category_id=category.id))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_same_skill_name_is_allowed_in_different_categories(app):
    """Uniqueness is per category, not global (see PROJECT_STATE.md, section 4)."""
    with app.app_context():
        music, sports = Category(name="Music"), Category(name="Sports")
        db.session.add_all([music, sports])
        db.session.commit()

        db.session.add_all([
            Skill(name="Conditioning", category_id=music.id),
            Skill(name="Conditioning", category_id=sports.id),
        ])
        db.session.commit()

        assert Skill.query.filter_by(name="Conditioning").count() == 2