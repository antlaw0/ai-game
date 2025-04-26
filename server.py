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
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from itsdangerous import URLSafeTimedSerializer

# Secure token for password reset
s = URLSafeTimedSerializer(os.getenv("REMOVED_SECRET"))

load_dotenv()

# ---------- SYSTEM PROMPT ----------
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

# ---------- ENVIRONMENT VARIABLES ----------
REMOVED_SECRET = os.getenv("REMOVED_SECRET")
TOGETHERAI_PARSER_MODEL = os.getenv("TOGETHERAI_PARSER_MODEL")
API_KEY = os.getenv("REMOVED_SECRET")
DATABASE_URL = os.getenv("NEON_DB_URL")
REMOVED_SECRET = os.getenv("REMOVED_SECRET")

# ---------- DATABASE SETUP ----------
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

# ---------- FLASK APP ----------
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
        total_cost = sum(int(item['quantity']) * float(item['price']) for item in items)

        if total_cost > state.money:
            return jsonify({"error": "Not enough funds"}), 400

        for item in items:
            name = item['name']
            qty = int(item['quantity'])
            inventory[name] = inventory.get(name, 0) + qty

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

        # Parse data
        parser_payload = {
            "model": TOGETHERAI_PARSER_MODEL,
            "messages": [
                {"role": "system", "content": "Extract JSON data from the AI's message. Output format:\n"
                                              "{\n  \"money\": float,\n  \"day\": int,\n  \"inventory\": {\"item\": quantity, ...}\n}"},
                {"role": "user", "content": ai_response}
            ],
            "temperature": 0.0
        }

        parser_response = requests.post("https://api.together.ai/v1/chat/completions", headers=headers, json=parser_payload)
        parsed_data = parser_response.json()["choices"][0]["message"]["content"]

        try:
            parsed_json = json.loads(parsed_data)
            state.money = float(parsed_json.get("money", state.money))
            state.day = int(parsed_json.get("day", state.day))
            state.inventory = json.dumps(parsed_json.get("inventory", json.loads(state.inventory)))
        except Exception as e:
            print("Parser error:", e)

        # Save log
        new_log = f"Player: {user_input}\nAI: {ai_response}"
        combined_log = (state.log or "") + "\n\n" + new_log
        state.log = combined_log.strip()[-3000:]
        session.commit()

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

@app.route("/request-reset", methods=["POST"])
def request_reset():
    session = SessionLocal()
    try:
        data = request.get_json()
        email = data.get("email")
        user = session.query(User).filter_by(email=email).first()

        if not user:
            return jsonify({"error": "No account found with that email"}), 404

        token = s.dumps(email, salt="password-reset-salt")
        reset_link = f"{request.url_root}reset-password/{token}"

        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = REMOVED_SECRET
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

        email_obj = {
            "sender": {"name": "Cooking Game", "email": os.getenv("SMTP_USERNAME")},
            "to": [{"email": email}],
            "subject": "Reset Your Password",
            "htmlContent": f"<p>Click the link to reset your password:</p><p><a href='{reset_link}'>Reset Password</a></p>"
        }

        api_instance.send_transac_email(email_obj)
        return jsonify({"message": "Password reset email sent!"})
    except ApiException as e:
        print("Brevo error:", e)
        return jsonify({"error": "Failed to send reset email"}), 500
    finally:
        session.close()

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    session = SessionLocal()
    try:
        if request.method == "GET":
            return render_template("reset_form.html", token=token)

        data = request.form
        password = data.get("password")
        confirm = data.get("confirm")

        if password != confirm or len(password) < 8:
            return "Passwords must match and be at least 8 characters."

        email = s.loads(token, salt="password-reset-salt", max_age=3600)
        user = session.query(User).filter_by(email=email).first()

        if user:
            user.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            session.commit()
            return "Password reset successful. You can now log in."

        return "Invalid token or user not found."
    except Exception as e:
        traceback.print_exc()
        return "Something went wrong."
    finally:
        session.close()

# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
