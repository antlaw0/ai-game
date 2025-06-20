from server import app, db
from extensions import db
import models

with app.app_context():
    db.drop_all()
    db.create_all()
    print(" Tables created successfully.")
