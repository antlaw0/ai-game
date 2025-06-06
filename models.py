from extensions import db
from sqlalchemy.dialects.postgresql import JSON

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.String, primary_key=True)
    game_state = db.Column(JSON)
    inventory = db.Column(JSON)
    money = db.Column(db.Float, default=0.0)
    day = db.Column(db.Integer, default=1)
