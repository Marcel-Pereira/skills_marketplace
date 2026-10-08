from werkzeug.security import check_password_hash, generate_password_hash

from app import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        # salted hash, so two users with the same password get different hashes
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Skill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    owner = db.relationship("User", backref="skills")
