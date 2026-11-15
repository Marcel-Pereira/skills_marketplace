"""Explicit database upgrades for existing installations."""
import click
from flask.cli import with_appcontext
from sqlalchemy import inspect

from app import db


@click.command("upgrade-db")
@with_appcontext
def upgrade_db_command():
    """Add profile columns without replacing existing account data."""
    with db.engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        if "date_of_birth" in columns:
            click.echo("Database is already up to date.")
            return
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN date_of_birth DATE")
    click.echo("Added users.date_of_birth. Existing account data was preserved.")
