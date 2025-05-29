from server import app, db
from extensions import db
from models import UserGameState

with app.app_context():
    db.create_all()
    print("✅ Tables created successfully.")
