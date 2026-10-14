from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app(test_config=None):
    """Build the app. Tests pass test_config to use a separate in-memory database."""
    app = Flask(__name__)
    app.config.from_pyfile("config.py")
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    from app.routes import main
    app.register_blueprint(main)

    with app.app_context():
        db.create_all()

    return app
