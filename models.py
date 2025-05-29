from server import db

class UserGameState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String, unique=True, nullable=False)
    state = db.Column(db.JSON, nullable=False)
