from flask import Flask, render_template, redirect, url_for, request, make_response, jsonify
import jwt
import os
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from extensions import db
from models import User
import requests
import datetime
print("Game server current UTC time:", datetime.datetime.utcnow())

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set in environment variables.")
print("SECRET_KEY is "+SECRET_KEY)
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('NEON_DB_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)


#Init Groq stuff
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama3-70b-8192"
GROQ_SYSTEM_PROMPT = (
    "You are a helpful cooking simulator AI chef assistant. "
    "Act as a game master for a cooking RPG where the player owns a food stand and cooks 4 meals per day: breakfast, lunch, dinner, and dessert. "
    "Evaluate their meals and provide feedback as a judge from a cooking competition. Give a score out of 10 for taste, technique, presentation, and creativity. "
    "Add those to make a total score (0–40). The player earns $20 x their total score, added to their total money. "
    "After each meal, update the meal state. After dessert, summarize the day and increment the day number. "
    "Always return your reply as a JSON object with these fields:\n\n"
    "```json\n"
    "{\n"
    "  \"narration\": \"Narrative response to the player\",\n"
    "  \"money_earned\": 0,\n"
    "  \"meal_completed\": \"breakfast\", // or lunch, dinner, dessert\n"
    "  \"day_increment\": false, // set to true only after dessert\n"
    "  \"inventory_changes\": {\"Tomato\": -1, \"Cheese\": -1} // optional\n"
    "}\n"
    "```\n\n"
    "Only include the JSON object. Do not add explanations or extra commentary."
)


# ✅ Token verification decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            parts = auth_header.split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        elif 'token' in request.cookies:
            token = request.cookies.get('token')

        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'], options={"verify_exp": False})
            print("Decoded token payload:", payload)
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
    user_id = request.user.get('user_id')
    return render_template('dashboard.html', user={'id': user_id})

@app.route('/logout')
def logout():
    response = make_response(redirect(url_for('login_page')))
    response.set_cookie('token', '', expires=0)
    return response

@app.route('/game')
@token_required
def game():
    return render_template('game.html')

@app.route("/api/register-user", methods=["POST"])
def register_user():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return {"error": "Authorization header missing or invalid"}, 401

    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
        user_id = payload.get("user_id")
        email = payload.get("email")
        if not user_id:
            return {"error": "Invalid token: no user_id"}, 400
    except jwt.InvalidTokenError as e:
        return {"error": f"Token decode failed: {str(e)}"}, 401

    # Check if user exists
    existing_user = User.query.get(user_id)
    if existing_user:
        return {"message": "User already registered in game DB"}, 200

    new_user = User(
        id=user_id,
        user_id=user_id,
        last_meal_completed="breakfast",
        money=200.0,
        inventory={},
        day=1,
        game_state={}
    )
    db.session.add(new_user)
    db.session.commit()

    return {"message": "User registered successfully"}, 201

@app.route('/api/user-data')
@token_required
def get_user_data():
    user_id = request.user['user_id']
    data = {
        'user_id': user_id,
        'favorite_recipes': ['AI Salad Supreme', 'Neural Noodles'],
        'experience_level': 'Sous Chef'
    }
    return jsonify(data)


@app.route('/api/state', methods=['POST'])
@token_required
def get_game_state():
    user_id = request.user['user_id']
    email = request.user['email']

    user = User.query.get(user_id)

    if not user:
        default_state = {
            'player': f'Chef{user_id}',
            'restaurant': "Neural Noms",
            'day': 1,
            'money': 200.00,
            'inventory': {
                'Tomato': 3,
                'Cheese': 2,
                'Basil': 5
            },
            'last_meal_completed': 'breakfast'
        }
        user = User(
            id=user_id,
            user_id=user_id,
            email=email,
            game_state=default_state,
            inventory=default_state['inventory'],
            money=default_state['money'],
            day=default_state['day'],
            last_meal_completed=default_state['last_meal_completed']
        )
        db.session.add(user)
        db.session.commit()

    # Fill missing game state (if DB entry exists but was missing game_state)
    if not user.game_state:
        default_state = {
            'player': f'Chef{user_id}',
            'restaurant': "Neural Noms",
            'day': 1,
            'money': 200.00,
            'inventory': {
                'Tomato': 3,
                'Cheese': 2,
                'Basil': 5
            },
            'last_meal_completed': 'breakfast'
        }
        user.game_state = default_state
        user.inventory = default_state['inventory']
        user.money = default_state['money']
        user.day = default_state['day']
        user.last_meal_completed = default_state['last_meal_completed']
        db.session.commit()

    return jsonify(user.game_state)


@app.route('/api/message', methods=['POST'])
@token_required
def handle_message():
    user_id = request.user.get('user_id')
    message = request.json.get('message', '').strip()
    print("Sending to Groq:", message)

    if not message:
        return jsonify({'error': 'No message provided'}), 400

    user = User.query.get(user_id)
    if not user or not user.game_state:
        return jsonify({'error': 'Game state not found'}), 404

    state = user.game_state

    # 🧠 Build state context string
    state_info = (
        f"Day: {state.get('day', 1)}\n"
        f"Money: ${state.get('money', 0.00):.2f}\n"
        f"Inventory: {state.get('inventory', {})}\n"
        f"Last meal completed: {getattr(user, 'last_meal_completed', 'breakfast')}\n"
    )
    full_message = f"{state_info}\nUser action: {message}"

    try:
        # 🧠 Call Groq API
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": GROQ_SYSTEM_PROMPT},
                    {"role": "user", "content": full_message}
                ],
                "temperature": 0.7,
                "max_tokens": 512,
                "top_p": 1,
                "stream": False
            }
        )

        if response.status_code != 200:
            print("Groq API Error:", response.json())
            return jsonify({'error': 'Groq API request failed'}), 500

        ai_json = response.json()['choices'][0]['message']['content'].strip()
        print("AI raw JSON:", ai_json)

        try:
            import json
            parsed = json.loads(ai_json)
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid JSON returned from Groq', 'raw': ai_json}), 500

        # ✅ Apply changes to game state
        earned = parsed.get('money_earned', 0)
        state['money'] = state.get('money', 0.0) + earned
        user.money = state['money']  # Also update user.money explicitly

        meal = parsed.get('meal_completed')
        if meal:
            user.last_meal_completed = meal

        if parsed.get('day_increment', False):
            state['day'] = state.get('day', 1) + 1
            user.last_meal_completed = 'breakfast'

        inventory_changes = parsed.get('inventory_changes', {})
        inventory = state.setdefault('inventory', {})

        for item, change in inventory_changes.items():
            inventory[item] = inventory.get(item, 0) + change

        # ✅ Save inventory separately to user.inventory if it's stored there
        user.inventory = inventory

        # ✅ Save full state back to DB
        user.game_state = state
        db.session.commit()

        return jsonify({
            'response': parsed.get('narration', 'No response'),
            'earned': earned,
            'new_state': state
        })

    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Network or request error: {str(e)}'}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


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
            return {"error": "Invalid credentials or login failed", "status": response.status_code}, 401

        token = response.json().get("token")
        if not token:
            return {"error": "Login succeeded but no token received"}, 500

        # ✅ SET COOKIE HERE
        resp = make_response(jsonify({"message": "Login successful"}))
        resp.set_cookie('token', token, httponly=True, secure=False)  # Set secure=True in production
        return resp

    except requests.RequestException as e:
        return {"error": f"Failed to reach account management server: {str(e)}"}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
