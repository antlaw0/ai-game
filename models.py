# models.py
from extensions import db

class UserGameState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    game_state = db.Column(db.Text)  # or JSON depending on usage
