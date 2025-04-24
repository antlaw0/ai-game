from dotenv import load_dotenv
import os
import json
import traceback
import requests
import bcrypt
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

load_dotenv()

# System prompt for the main AI model
system_info = """
You are running a text-based cooking game. The player starts with $200 and a small food cart.
They can buy ingredients and cooking equipment from a store at the start of each day.
Each day has four cooking sessions: breakfast, lunch, dinner, and dessert.
The player types what and how they cook, and you respond with detailed feedback and
award money based on how well they cooked.

You must consider:
- Their available money
- Ingredients and quantities
- The day number
- Previous actions (last 3)
Respond like a game master. Stay immersive and do not break character.
"""

# Environment variables
REMOVED_SECRET = os.getenv("REMOVED_SECRET")
TOGETHERAI_PARSER_MODEL = os.getenv("TOGETHERAI_PARSER_MODEL")
API_KEY = os.getenv("REMOVED_SECRET")
DATABASE_URL = os.getenv("NEON_DB_URL")

# Database setup
engine = create_engine(DATABASE_URL, echo=True, pool_pre_ping=True, poolclass=NullPool)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String)
    restaurant = Column(String)

class GameState(Base):
    __tablename__ = "game_state"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    day = Column(Integer, default=1)
    money = Column(Float, default=200.0)
    inventory = Column(Text, default='{}')
    log = Column(Text, default="")

Base.metadata.create_all(bind=engine)

# Flask app
app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login-page")
def login_page():
    return render_template("index.html")

@app.route("/register-page")
def register_page():
    return render_template("register.html")

@app.route("/game")
def game():
    return render_template("game.html")

@app.route("/register", methods=["POST"])
def register():
    session = SessionLocal()
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")

        print("Attempting registration:", email)
        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400

        existing = session.query(User).filter_by(email=email).first()
        if existing:
            return jsonify({"error": "Email already registered"}), 409

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = User(email=email, password_hash=password_hash)
        session.add(user)
        session.commit()

        return jsonify({"message": "User registered", "user_id": user.id})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

@app.route("/login", methods=["POST"])
def login():
    session = SessionLocal()
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")

        user = session.query(User).filter_by(email=email).first()
        if not user:
            return jsonify({"error": "No such account"}), 404
        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return jsonify({"error": "Invalid credentials"}), 401

        return jsonify({
            "message": "Login successful",
            "user_id": user.id,
            "name": user.name,
            "restaurant": user.restaurant
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

@app.route("/api/buy", methods=["POST"])
def buy():
    session = SessionLocal()
    try:
        data = request.json
        user_id = data.get("user_id")
        items = data.get("items")

        state = session.query(GameState).filter_by(user_id=user_id).first()
        if not state:
            return jsonify({"error": "Game state not found"}), 404

        inventory = json.loads(state.inventory or '{}')
        total_cost = 0.0

        for item in items:
            name = item['name']
            qty = int(item['quantity'])
            price = float(item['price'])
            total_cost += qty * price
            inventory[name] = inventory.get(name, 0) + qty

        if total_cost > state.money:
            return jsonify({"error": "Not enough funds"}), 400

        state.money -= total_cost
        state.inventory = json.dumps(inventory)
        session.commit()

        return jsonify({
            "message": "Items purchased",
            "money": state.money,
            "inventory": inventory
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

# 🧠 PARSER FUNCTION
def parse_game_state(ai_response):
    prompt = f"""
You are a parser. Extract the following game state from this response and output JSON:
- day: current day number
- money: numeric value
- inventory: object with ingredient names and quantities

AI response:
\"\"\"
{ai_response}
\"\"\"

Respond in JSON:
{{"day": 2, "money": 155.5, "inventory": {{"eggs": 3, "bacon": 1}}}}
"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": TOGETHERAI_PARSER_MODEL,
        "messages": [
            {"role": "system", "content": "You are a JSON data extractor."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }

    try:
        response = requests.post("https://api.together.ai/v1/chat/completions", headers=headers, json=payload)
        parsed = response.json()["choices"][0]["message"]["content"]
        return json.loads(parsed)
    except Exception as e:
        print("Parsing failed:", e)
        return None

@app.route("/api/chat", methods=["POST"])
def chat():
    session = SessionLocal()
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        user_input = data.get("message")

        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        state = session.query(GameState).filter_by(user_id=user_id).first()
        if not state:
            state = GameState(user_id=user_id)
            session.add(state)
            session.commit()

        history = (state.log or "").strip().split("\n\n")[-3:]
        inventory_dict = json.loads(state.inventory or '{}')
        inventory_str = "\n".join(f"- {k}: {v}" for k, v in inventory_dict.items())

        context = f"""
Day: {state.day}
Money: ${state.money:.2f}
Inventory:
{inventory_str}

Last actions:
{chr(10).join(history)}
"""

        # Step 1: Main AI response
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": REMOVED_SECRET,
            "messages": [
                {"role": "system", "content": system_info},
                {"role": "user", "content": context + "\n\nPlayer says: " + user_input}
            ],
            "temperature": 0.7
        }

        response = requests.post("https://api.together.ai/v1/chat/completions", headers=headers, json=payload)
        if response.status_code != 200:
            return jsonify({"error": "AI request failed", "details": response.text}), 500

        ai_response = response.json()["choices"][0]["message"]["content"]

        # Step 2: Use parser model to extract updated data
        parser_payload = {
            "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
            "messages": [
                {"role": "system", "content": "Extract JSON data from the AI's message. Output format:\n"
                                              "{\n  \"money\": float,\n  \"day\": int,\n  \"inventory\": {\"item\": quantity, ...}\n}"},
                {"role": "user", "content": ai_response}
            ],
            "temperature": 0.0
        }

        parser_response = requests.post("https://api.together.ai/v1/chat/completions", headers=headers, json=parser_payload)
        parsed_data = parser_response.json()["choices"][0]["message"]["content"]

        # Step 3: Try parsing and updating the DB
        try:
            parsed_json = json.loads(parsed_data)
            if "money" in parsed_json:
                state.money = float(parsed_json["money"])
            if "day" in parsed_json:
                state.day = int(parsed_json["day"])
            if "inventory" in parsed_json:
                state.inventory = json.dumps(parsed_json["inventory"])
        except Exception as parse_error:
            print("Parser AI returned invalid JSON:", parsed_data)
            print("Parse error:", parse_error)

        # Step 4: Save updated log
        new_log = f"Player: {user_input}\nAI: {ai_response}"
        combined_log = (state.log or "") + "\n\n" + new_log
        state.log = combined_log.strip()[-3000:]
        session.commit()

        # Step 5: Send response back to frontend
        return jsonify({
            "response": ai_response,
            "player": user.name,
            "restaurant": user.restaurant,
            "day": state.day,
            "money": state.money,
            "inventory": json.loads(state.inventory or '{}')
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    finally:
        session.close()

# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
