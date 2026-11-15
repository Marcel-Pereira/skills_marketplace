import sqlite3
from contextlib import closing
from datetime import date

from sqlalchemy import inspect

from app import create_app, db
from app.models import User


def test_upgrade_db_adds_birthday_without_losing_legacy_user(tmp_path):
    database_path = tmp_path / "legacy.db"
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                email VARCHAR(255) NOT NULL UNIQUE,
                username VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                bio TEXT,
                country_code VARCHAR(2),
                timezone VARCHAR(50),
                created_at DATETIME NOT NULL
            )
        """)
        connection.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "legacy@example.com", "legacy-user", "saved-password-hash",
             "Existing bio", "AR", "America/Argentina/Buenos_Aires", "2026-01-01 12:00:00"),
        )
        connection.commit()

    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
    })
    with app.app_context():
        assert "date_of_birth" not in {
            column["name"] for column in inspect(db.engine).get_columns("users")
        }

    runner = app.test_cli_runner()
    upgrade = runner.invoke(args=["upgrade-db"])
    assert upgrade.exit_code == 0, upgrade.output
    assert "Added users.date_of_birth" in upgrade.output
    repeated_upgrade = runner.invoke(args=["upgrade-db"])
    assert repeated_upgrade.exit_code == 0, repeated_upgrade.output
    assert "already up to date" in repeated_upgrade.output

    with app.app_context():
        columns = {column["name"]: column for column in inspect(db.engine).get_columns("users")}
        assert columns["date_of_birth"]["nullable"]
        user = db.session.execute(db.select(User)).scalar_one()
        assert user.id == 1
        assert user.email == "legacy@example.com"
        assert user.username == "legacy-user"
        assert user.password_hash == "saved-password-hash"
        assert user.bio == "Existing bio"
        assert user.country_code == "AR"
        assert user.timezone == "America/Argentina/Buenos_Aires"
        assert user.date_of_birth is None
        db.session.remove()
        db.engine.dispose()


def test_upgrade_db_is_a_noop_for_fresh_schema(app, user_id):
    with app.app_context():
        user = db.session.get(User, user_id)
        user.date_of_birth = date(2000, 4, 12)
        db.session.commit()

    runner = app.test_cli_runner()
    for _ in range(2):
        result = runner.invoke(args=["upgrade-db"])
        assert result.exit_code == 0, result.output
        assert "already up to date" in result.output

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.date_of_birth == date(2000, 4, 12)
