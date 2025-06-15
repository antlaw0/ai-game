from flask import Flask, render_template, redirect, url_for, request, make_response, jsonify
from routes import blueprints
import jwt
import os
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from extensions import db
from models import User
import requests
import datetime
import json
print("Game server current UTC time:", datetime.datetime.utcnow())

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set in environment variables.")
print("SECRET_KEY is "+SECRET_KEY)
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('NEON_DB_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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

    "**Important**: Your **entire response must be a single valid JSON object**, with no text outside it.\n\n"

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

    "You must return your entire response as a valid JSON object, and nothing else. "
    "Do not use markdown syntax (like ```json). "
    "Do not include explanation or messages outside the JSON. "
    "Do not start lines with dashes (-) unless inside a JSON string. "
    "Wrap the entire response in curly braces { ... }."
)

# Register all blueprints
for bp in blueprints:
    app.register_blueprint(bp)


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').split("Bearer ")[-1] \
            if 'Authorization' in request.headers else request.cookies.get('token')
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'], options={"verify_exp": False})
            request.user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
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
    return render_template('dashboard.html', user={'id': request.user.get('user_id')})

@app.route('/logout')
def logout():
    resp = make_response(redirect(url_for('login_page')))
    resp.set_cookie('token', '', expires=0)
    return resp

@app.route('/game')
@token_required
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

    existing_user = User.query.get(user_id)
    if existing_user:
        return {"message": "User already registered in game DB"}, 200

    new_user = User(id=user_id, user_id=user_id, last_meal_completed="breakfast", money=200.0, inventory={}, day=1, game_state={})
    db.session.add(new_user)
    db.session.commit()
    return {"message": "User registered successfully"}, 201

@app.route('/api/user-data')
@token_required
def get_user_data():
    user_id = request.user['user_id']
    return jsonify({
        'user_id': user_id,
        'favorite_recipes': ['AI Salad Supreme', 'Neural Noodles'],
        'experience_level': 'Sous Chef'
    })

@app.route('/api/state', methods=['POST'])
@token_required
def get_game_state():
    user_id = request.user['user_id']
    email = request.user['email']
    user = User.query.get(user_id)

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
        resp.set_cookie('token', token, httponly=True, secure=False)
        return resp
    except requests.RequestException as e:
        return {"error": f"Failed to reach account management server: {str(e)}"}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
