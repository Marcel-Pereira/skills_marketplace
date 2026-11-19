"""Explicit database upgrades for existing installations."""
import click
from flask.cli import with_appcontext
from sqlalchemy import inspect

from app import db


@click.command("upgrade-db")
@with_appcontext
def upgrade_db_command():
    """Add missing profile and points columns while preserving saved balances."""
    added = []
    with db.engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        for name, definition in (
            ("date_of_birth", "DATE"),
            ("points", "INTEGER NOT NULL DEFAULT 3 CHECK (points >= 0)"),
            ("reserved_points", "INTEGER NOT NULL DEFAULT 0 "
             "CHECK (reserved_points >= 0 AND reserved_points <= points)"),
        ):
            if name not in columns:
                connection.exec_driver_sql(f"ALTER TABLE users ADD COLUMN {name} {definition}")
                added.append(name)
    for name in added:
        click.echo(f"Added users.{name}. Existing account data was preserved.")
    if not added:
        click.echo("Database is already up to date.")
