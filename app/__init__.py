from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "main.login"
login_manager.login_message_category = "info"


def create_app(test_config=None):
    """Build the app. Tests pass test_config to use a separate in-memory database."""
    app = Flask(__name__)
    app.config.from_pyfile("config.py")
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)

    from app.routes import main
    app.register_blueprint(main)

    from app import models
    from app.seed import seed_skills

    # Register the command that loads the fixed categories and skills.
    # Run with 'flask --app app seed'
    @app.cli.command("seed")
    def seed_command():
        """Load the fixed categories and skills."""
        seed_skills()
        print("Seeded categories and skills.")

    with app.app_context():
        if db.engine.dialect.name == "sqlite":
            # Two seed commands can both start before the categories table exists.
            # Serialize the table check and creation as well as the later upgrade.
            with db.engine.begin() as connection:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                db.metadata.create_all(connection)
        else:
            db.create_all()

    return app
