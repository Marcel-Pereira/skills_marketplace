import os

# Read from environment variables when deployed, so real secrets never go in git.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev")
SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///skills.db")
