"""Upgrade the original SQLite skills table while keeping its listing references."""

from collections import defaultdict
from contextlib import contextmanager

from sqlalchemy import inspect

from app.models import Category, HISTORICAL_CATEGORY


# Labels used in the original skill picker.
RENAMED_SKILLS = {
    "Design": "Graphic Design",
    "Mandarin": "Mandarin Chinese",
    "Writing": "Creative Writing",
}


@contextmanager
def catalog_transaction(engine):
    """Lock before inspecting the schema and commit the upgrade and seed together."""
    with engine.connect() as connection:
        if engine.dialect.name != "sqlite":
            with connection.begin():
                if "category_id" not in {c["name"] for c in inspect(connection).get_columns("skills")}:
                    raise RuntimeError("The automatic upgrade from the original schema supports SQLite.")
                yield connection, False
            return

        sql = connection.exec_driver_sql
        foreign_keys = sql("PRAGMA foreign_keys").scalar_one()
        # SQLite requires this setting outside the transaction to rebuild a
        # referenced parent table. Validate all references before committing.
        try:
            if foreign_keys:
                sql("PRAGMA foreign_keys = OFF")
            sql("BEGIN IMMEDIATE")
            columns = {c["name"] for c in inspect(connection).get_columns("skills")}
            needs_upgrade = "category_id" not in columns
            if needs_upgrade and columns != {"id", "name"}:
                raise RuntimeError("Unrecognized skills schema. Cannot automatically upgrade it.")
            yield connection, needs_upgrade
            if sql("PRAGMA foreign_key_check").first() is not None:
                raise RuntimeError("Catalog update rolled back because a database reference is invalid.")
            connection.commit()
        finally:
            connection.rollback()
            if foreign_keys:
                sql("PRAGMA foreign_keys = ON")


def upgrade_legacy_skills(connection, catalog, category_ids):
    """Replace the old global name constraint, retaining every original skill ID."""
    sql = connection.exec_driver_sql
    # Refuse to discard extra indexes or triggers added outside the main schema.
    if sql("""SELECT 1 FROM sqlite_schema WHERE tbl_name = 'skills'
              AND type IN ('index', 'trigger') AND sql IS NOT NULL""").first():
        raise RuntimeError("The old skills table has custom indexes or triggers and needs a manual upgrade.")

    old_skills = sql("SELECT id, name FROM skills ORDER BY id").all()
    original_names = {name for _, name in old_skills}
    categories_for_skill = defaultdict(list)
    for category, names in catalog.items():
        for name in names:
            categories_for_skill[name].append(category_ids[category])

    sql("""CREATE TABLE skills_catalog_upgrade (
        id INTEGER NOT NULL PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        category_id INTEGER NOT NULL REFERENCES categories(id),
        CONSTRAINT uq_skill_category_name UNIQUE (category_id, name)
    )""")
    migrated = []
    for skill_id, original_name in old_skills:
        name = RENAMED_SKILLS.get(original_name, original_name)
        candidates = categories_for_skill[name]
        # An exact catalog name keeps its ID if both an alias and its target
        # already exist. Keep the alias row and its listings as account history.
        if len(candidates) == 1 and (name == original_name or name not in original_names):
            migrated.append((skill_id, name, candidates[0]))
        else:
            if HISTORICAL_CATEGORY not in category_ids:
                result = connection.execute(Category.__table__.insert().values(name=HISTORICAL_CATEGORY))
                category_ids[HISTORICAL_CATEGORY] = result.inserted_primary_key[0]
            migrated.append((skill_id, original_name, category_ids[HISTORICAL_CATEGORY]))

    if migrated:
        sql("INSERT INTO skills_catalog_upgrade (id, name, category_id) VALUES (?, ?, ?)", migrated)
    sql("DROP TABLE skills")
    sql("ALTER TABLE skills_catalog_upgrade RENAME TO skills")
    sql("CREATE INDEX ix_skills_category_id ON skills (category_id)")
