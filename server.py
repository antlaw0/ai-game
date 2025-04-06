import os
import traceback
import requests
import json
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base
port = int(os.environ.get("PORT", 5000))
# Set system prompt to be used every time a message is sent to the AI
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
...
"""

# Load Together AI API Key from environment variable
API_KEY = os.getenv("REMOVED_SECRET")
if not API_KEY:
    raise ValueError("REMOVED_SECRET is not set in environment variables.")

# Together AI API Endpoint
TOGETHER_AI_URL = "https://api.together.ai/v1/chat/completions"

# Flask app setup
app = Flask(__name__)
CORS(app)  # Allow cross-origin requests (for frontend)

# Database setup
DATABASE_URL = "sqlite:///game_data.db"
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# Define a database model (optional, modify as needed)
class GameState(Base):
    __tablename__ = "game_state"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    game_data = Column(Text)

# Create database tables
Base.metadata.create_all(bind=engine)

# Serve the game page
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/game")
def game():
    return render_template("game.html")

# API endpoint for AI responses
@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_input = data.get("message", "")

        if not user_input:
            return jsonify({"error": "No message provided"}), 400

        # Send request to Together AI
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "messages": [
                {"role": "system", "content": system_info},  # Fix: Correct variable name
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
        traceback.print_exc()  # Prints the full error stack traceback
        return jsonify({"error": str(e)}), 500
        return jsonify({"error": str(e)}), 500

# Start the Flask server
#if __name__ == "__main__":
    #app.run(host="0.0.0.0", port=5000, debug=True)

# Start the Flask server (For Render, we do not need to specify host and port)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)