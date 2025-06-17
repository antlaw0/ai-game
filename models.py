from extensions import db
from sqlalchemy.dialects.postgresql import JSON

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)  # internal ID
    user_id = db.Column(db.String, unique=True, nullable=False)  # From the JWT token
    email = db.Column(db.String, nullable=True)

    game_state = db.Column(JSON)
    inventory = db.Column(JSON)
    money = db.Column(db.Float, default=0.0)
    day = db.Column(db.Integer, default=1)
    last_meal_completed = db.Column(db.String, default="breakfast", nullable=False)
    chat_history = db.Column(JSON, default=[])
