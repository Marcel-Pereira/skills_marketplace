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

    with app.app_context():
        db.create_all()

    return app
