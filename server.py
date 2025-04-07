import os
import traceback
import requests
import json
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base

# System prompt to guide the AI
system_info = """
This is a text-based game where the player types how they cook a dish and the AI determines the outcome. 
The player starts out owning a small food cart in a large city. All they have to begin with is a hot plate 
and basic utensils such as a spoon, spatula, forks, knives, etc. For procuring ingredients, the player will 
have to visit a special store where chefs go to purchase ingredients. There is a produce section, butcher, 
cooking equipment, spices—everything the player will need.

The player starts out with a small sum of money. For instructional purposes, let's say $200. 
As far as pricing of ingredients and items go, try to make a reasonable estimate based on whatever data 
and other methods of reasoning you have to assign prices to items. The player can ask if certain items 
are available, and how much it will cost.
"""

# Load Together AI API Key
API_KEY = os.getenv("REMOVED_SECRET")
if not API_KEY:
    raise ValueError("REMOVED_SECRET is not set in environment variables.")

# Together AI API Endpoint
TOGETHER_AI_URL = "https://api.together.ai/v1/chat/completions"

# Flask setup
app = Flask(__name__)
CORS(app)

# Load Supabase/Postgres DB credentials from env
DB_USER = os.getenv("SUPABASE_DB_USER", "postgres")
DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD")
DB_HOST = os.getenv("SUPABASE_DB_URL")  # format like "db.xyz.supabase.co"
DB_PORT = os.getenv("SUPABASE_DB_PORT", "5432")
DB_NAME = os.getenv("SUPABASE_DB_NAME", "postgres")

# Construct Postgres connection string
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# SQLAlchemy setup
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# Define basic game state table
class GameState(Base):
    __tablename__ = "game_state"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    game_data = Column(Text)

# Create tables if not exist
Base.metadata.create_all(bind=engine)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/game")
def game():
    return render_template("game.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_input = data.get("message", "")

        if not user_input:
            return jsonify({"error": "No message provided"}), 400

        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "messages": [
                {"role": "system", "content": system_info},
                {"role": "user", "content": user_input}
            ],
            "temperature": 0.7
        }

        response = requests.post(TOGETHER_AI_URL, headers=headers, json=payload)

        if response.status_code == 200:
            ai_response = response.json()["choices"][0]["message"]["content"]
            return jsonify({"response": ai_response})
        else:
            return jsonify({"error": "Failed to fetch AI response", "details": response.text}), 500

    except Exception as e:
        print("Error processing request:")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# Run the server
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
