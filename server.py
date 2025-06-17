from flask import g, Flask, render_template, redirect, url_for, request, make_response, jsonify
import jwt
import os
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from extensions import db
from models import User
import requests
import datetime
import json
from sqlalchemy.pool import QueuePool
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
print("Game server current UTC time:", datetime.datetime.now(datetime.timezone.utc))


SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set in environment variables.")
print("SECRET_KEY is "+SECRET_KEY)
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('NEON_DB_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 1800  # 30 minutes
}
db.init_app(app)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama3-70b-8192"
GROQ_SYSTEM_PROMPT = (
    "You are a highly skilled cooking simulator AI and act as a game master for a culinary RPG. "
    "The player runs a food stand and must cook four meals per day: breakfast, lunch, dinner, and dessert. "
    "For each meal, the player describes what they made and how they prepared it. "
    "You are a judge in a cooking competition, drawing inspiration from Iron Chef, Gordon Ramsay, and Julia Child. "
    "Base your scoring and feedback on expert-level knowledge of flavor pairing, proper cooking techniques, classical and modern presentation, and originality. "

    "Each completed meal is scored in the following categories (0–10):\n"
    "- Taste: Does the meal sound flavorful, balanced, and well-seasoned?\n"
    "- Technique: Did the player use proper cooking methods and demonstrate skill?\n"
    "- Presentation: Is the meal described in a way that evokes an appealing visual image?\n"
    "- Creativity: Is the dish original, clever, or inspired?\n"

    "Add these scores to make a total score (0–40). "
    "The player earns $20 times their total score, which is added to their total money. "

    "Give helpful, constructive feedback based on professional culinary standards. Avoid overpraise for basic meals and provide meaningful suggestions. "
    "After each meal, update the game state. After dessert, summarize the day and increment the in-game day number. "

    "**Purchasing Rules**:\n"
    "- The player may purchase any realistic food ingredient, cooking tool, or kitchen equipment commonly found in modern times.\n"
    "- Players are not limited to a preset list of items.\n"
    "- Purchases must follow realistic pricing rules and money tracking.\n"
    "- Players may request one or more items in a single message.\n"
    "- Provide a full breakdown of each item’s quantity and cost.\n"
    "- Then show the total cost and their current balance.\n"
    "- Before completing the purchase, ask inside the JSON **narration**: 'Would you like to proceed with the purchase?'\n"
    "- ONLY complete the transaction if the player clearly says yes.\n"
    "- If they do not have enough money, cancel the transaction and explain.\n"
    "- Always maintain consistent pricing throughout the game.\n\n"

    "**Response Format Requirements**:\n"
    "- Your entire response MUST be a single valid JSON object.\n"
    "- DO NOT include any text outside of the JSON object.\n"
    "- DO NOT use markdown formatting (no triple backticks).\n"
    "- DO NOT include explanations, greetings, or commentary before or after the JSON.\n"
    "- All narration, pricing, and player interaction must be inside the JSON object's `narration` field.\n"
    "- Never start lines with dashes (-) unless they are inside a string value in the JSON.\n"

    "**Example of purchasing multiple items**:\n"
    "Player: I want to buy 2 whole fresh chickens, 1 stick of butter, a basic blender, and five pounds of unbleached flour.\n"
    "AI response:\n"
    "{\n"
    "  \"narration\": \"Here's the price breakdown:\\n"
    "  - 2 whole fresh chickens = $30 ($15 each)\\n"
    "  - 1 stick of butter = $1\\n"
    "  - 1 basic blender = $25\\n"
    "  - 5 pounds of unbleached flour = $15 ($3 each)\\n"
    "Total: $71. You currently have $200. After this purchase, you'll have $129. Would you like to proceed with the purchase?\",\n"
    "  \"money_earned\": 0,\n"
    "  \"meal_completed\": \"none\",\n"
    "  \"day_increment\": false,\n"
    "  \"inventory_changes\": {\n"
    "    \"Whole Fresh Chicken\": 2,\n"
    "    \"Butter\": 1,\n"
    "    \"Blender\": 1,\n"
    "    \"Flour (Unbleached)\": 5\n"
    "  }\n"
    "}\n"

    "⚠️ FINAL REMINDER: Only respond with a valid JSON object, wrapped in curly braces `{ ... }`, and nothing else. "
    "Failure to do so will result in your response being ignored by the game system."
)

# Register all blueprints
#for bp in blueprints:
    #app.register_blueprint(bp)





from functools import wraps
from flask import request, jsonify, g
import jwt

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("access_token")  # ✅ From cookie, not header
        print("Received access_token from cookie:", token)  # 👈 Add this
        if not token:
            return jsonify({"error": "Missing authorization token"}), 401
        try:
            decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            #g.user_id = decoded.get("user_id")
            g.user = decoded
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register-page')
def register_page():
    return render_template('register.html')

@app.route('/login-page')
def login_page():
    return render_template('login.html')

@app.route('/dashboard')
@token_required
def dashboard():
    return render_template('dashboard.html', user={'id': g.user.get('user_id')})

@app.route('/logout')
def logout():
    resp = make_response(redirect(url_for('login_page')))
    resp.set_cookie('token', '', expires=0)
    return resp

@app.route('/game')
def game():
    return render_template('game.html')

@app.route("/api/register-user", methods=["POST"])
def register_user():
    token = request.headers.get("Authorization", "").split("Bearer ")[-1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
        user_id = payload.get("user_id")
        email = payload.get("email")
        if not user_id:
            return {"error": "Invalid token: no user_id"}, 400
    except jwt.InvalidTokenError as e:
        return {"error": f"Token decode failed: {str(e)}"}, 401

    existing_user = db.session.get(User, user_id)
    if existing_user:
        return {"message": "User already registered in game DB"}, 200

    new_user = User(id=user_id, user_id=user_id, last_meal_completed="breakfast", money=200.0, inventory={}, day=1, game_state={})
    db.session.add(new_user)
    db.session.commit()
    return {"message": "User registered successfully"}, 201

@app.route('/api/user-data')
@token_required
def get_user_data():
    user_id = g.user['user_id']
    return jsonify({
        'user_id': user_id,
        'favorite_recipes': ['AI Salad Supreme', 'Neural Noodles'],
        'experience_level': 'Sous Chef'
    })

@app.route('/api/state', methods=['POST'])
@token_required
def get_game_state():
    user_id = g.user['user_id']
    email = g.user['email']
    user = db.session.get(User, user_id)

    default_state = {
        'player': f'Chef{user_id}',
        'restaurant': "Neural Noms",
        'day': 1,
        'money': 200.00,
        'inventory': {
            'tomato': 3,
            'cheese': 2,
            'basil': 5
        },
        'last_meal_completed': 'breakfast'
    }

    if not user:
        user = User(id=user_id, user_id=user_id, email=email, game_state=default_state,
                    inventory=default_state['inventory'], money=default_state['money'],
                    day=default_state['day'], last_meal_completed=default_state['last_meal_completed'])
        db.session.add(user)
        db.session.commit()
    elif not user.game_state:
        user.game_state = default_state
        user.inventory = default_state['inventory']
        user.money = default_state['money']
        user.day = default_state['day']
        user.last_meal_completed = default_state['last_meal_completed']
        db.session.commit()

    game_state = {
        'player': f'Chef{user.user_id}',
        'restaurant': "Neural Noms",
        'day': user.day,
        'money': user.money,
        'inventory': {k.lower(): v for k, v in (user.inventory or {}).items()},
        'last_meal_completed': user.last_meal_completed or "breakfast"
    }
    return jsonify(game_state)



@app.route("/api/login", methods=["POST"])
def login_user():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return {"error": "Email and password required"}, 400

    ams_url = os.getenv("ACCOUNT_MGMT_SERVER_URL", "http://localhost:5000")
    try:
        response = requests.post(f"{ams_url}/api/login", json={"email": email, "password": password})
        if response.status_code != 200:
            return {"error": "Invalid credentials or login failed"}, 401

        token = response.json().get("token")
        if not token:
            return {"error": "Login succeeded but no token received"}, 500

        resp = make_response(jsonify({"message": "Login successful"}))
        resp.set_cookie('access_token', token, httponly=True, secure=False)
        return resp
    except requests.RequestException as e:
        return {"error": f"Failed to reach account management server: {str(e)}"}, 500


def build_full_message(state, last_meal, message):
    return (
        f"Day: {state.get('day', 1)}\n"
        f"Money: ${state.get('money', 0.00):.2f}\n"
        f"Inventory: {state.get('inventory', {})}\n"
        f"Last meal completed: {last_meal or 'breakfast'}\n"
        f"User action: {message.strip()}"
    )

def trim_chat_history(history, max_tokens=4096, estimated_per_message=200, buffer=3):
    max_history = max_tokens // estimated_per_message - buffer
    return history[-max_history:], max_history



def call_groq_api(messages):
    response = requests.post(
        GROQ_API_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 512,
            "top_p": 1,
            "stream": False
        }
    )

    print("Groq response status code:", response.status_code)
    print("Groq response raw text:", repr(response.text))
    print("Groq response JSON try:")
    try:
        print(json.dumps(response.json(), indent=2))
    except Exception as e:
        print("Failed to decode Groq response as JSON:", e)
        print("Raw text fallback:", repr(response.text))

    if response.status_code != 200:
        raise ValueError(f"Groq API request failed with status {response.status_code}")

    return response

def extract_ai_json(groq_data):
    try:
        content = groq_data['choices'][0]['message']['content'].strip()
        return content
    except (KeyError, IndexError, TypeError) as e:
        print("Groq response missing expected fields:", e)
        print("Full Groq data:", json.dumps(groq_data, indent=2))
        raise ValueError("Groq response missing expected fields")

def parse_ai_response(ai_json):
    try:
        return json.loads(ai_json)
    except json.JSONDecodeError as e:
        print("JSON parsing failed:", e)
        print("Invalid JSON content was:", repr(ai_json))
        raise ValueError(f"Invalid JSON from AI: {str(e)}")

def apply_game_updates(user, parsed, message):
    state = user.game_state
    narration = parsed.get('narration', '')
    should_apply = 'Would you like to proceed with the purchase?' not in narration or 'yes' in message.lower()

    earned = parsed.get('money_earned', 0)
    state['money'] = state.get('money', 0.0) + earned
    user.money = state['money']

    if parsed.get('meal_completed'):
        user.last_meal_completed = parsed['meal_completed']

    if parsed.get('day_increment', False):
        state['day'] = state.get('day', 1) + 1
        user.last_meal_completed = 'breakfast'

    if should_apply:
        inventory_changes = parsed.get('inventory_changes', {})
        inventory = state.setdefault('inventory', {})
        for item, change in inventory_changes.items():
            try:
                inventory[item] = inventory.get(item, 0) + int(change)
            except (ValueError, TypeError):
                continue
        user.inventory = inventory

    return narration, earned, state


def process_player_message(user, message):
    full_message = build_full_message(user.game_state, user.last_meal_completed, message)
    history = user.chat_history or []
    history.append({"role": "user", "content": full_message})
    trimmed_history, max_history = trim_chat_history(history)

    messages = [{"role": "system", "content": GROQ_SYSTEM_PROMPT}] + trimmed_history
    groq_response = call_groq_api(messages)

    ai_json = extract_ai_json(groq_response.json())
    parsed = parse_ai_response(ai_json)

    narration, earned, new_state = apply_game_updates(user, parsed, message)
    trimmed_history.append({"role": "assistant", "content": narration})
    user.chat_history = trimmed_history[-max_history:]
    user.game_state = new_state

    return narration, earned, new_state


@app.route("/api/message", methods=["POST"])
@token_required
def message():
    data = request.get_json()
    user_id = g.user['user_id']
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    player_message = data.get("message", "").strip()
    if not player_message:
        return jsonify({"error": "No message provided"}), 400

    system_prompt = GROQ_SYSTEM_PROMPT
    state_summary = (
        f"Current game state:\n"
        f"Money: ${user.money}\n"
        f"Inventory: {json.dumps(user.inventory or {})}\n"
        f"Day: {user.day}\n"
        f"Last meal completed: {user.last_meal_completed or 'breakfast'}\n"
    )

    history_summary = "\n".join([
    f"User: {entry.get('user', '[missing]')}\nAI: {entry.get('ai', '[missing]')}"
    for entry in user.chat_history[-5:] if isinstance(entry, dict)
]) if user.chat_history else ""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": state_summary}
    ]

    # Include chat history (past user/AI turns) for memory continuity
    if history_summary:
        messages.append({"role": "system", "content": f"Recent chat history:\n{history_summary}"})

    # Add current user message
    messages.append({"role": "user", "content": player_message})

    payload = {
        "messages": messages,
        "model": "llama3-70b-8192",
        "temperature": 0.2,
        "max_tokens": 1024,
    }

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
    )

    if response.status_code != 200:
        return jsonify({"error": "Groq API failed"}), 500

    try:
        response_json = response.json()
        ai_content = response_json["choices"][0]["message"]["content"].strip()
        print("AI raw content:  ", ai_content)
        parsed = json.loads(ai_content)
        print("AI parsed content:  ", parsed)
    except Exception as e:
        app.logger.error("Groq JSON parsing failed: %s", e)
        app.logger.error("Invalid Groq content: %s", ai_content)
        return jsonify({
            "error": "AI response was invalid JSON.",
            "ai_response": ai_content,
            "fallback_narration": "Oops! The AI got a little scrambled and didn't return a valid response. Try asking again."
        }), 500

    # Save chat history
    user.chat_history.append({"user": player_message, "ai": parsed})
    db.session.commit()

    return jsonify(parsed)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)