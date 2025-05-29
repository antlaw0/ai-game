from flask import Flask, render_template, redirect, url_for, request, make_response, jsonify
import jwt
import os
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSON
from extensions import db
from models import UserGameState

SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('NEON_DB_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)





# ✅ Token verification decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Try to get token from cookie or Authorization header
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
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            request.user = payload  # Attach decoded payload to request
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        return f(*args, **kwargs)
    return decorated

# ✅ In-memory game state (for dev/testing)
user_states = {}

# ✅ Routes

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
    user_email = request.user.get('email')
    return render_template('dashboard.html', user={'email': user_email})

@app.route('/logout')
def logout():
    response = make_response(redirect(url_for('login_page')))
    response.set_cookie('token', '', expires=0)
    return response

@app.route('/game')
@token_required
def game():
    return render_template('game.html')

# ✅ Simple user data
@app.route('/api/user-data')
@token_required
def get_user_data():
    email = request.user.get('email')
    data = {
        'email': email,
        'favorite_recipes': ['AI Salad Supreme', 'Neural Noodles'],
        'experience_level': 'Sous Chef'
    }
    return jsonify(data)

# ✅ Get game state
@app.route('/api/state', methods=['POST'])
@token_required
def get_game_state():
    user_id = request.user.get('id')
    game_state = UserGameState.query.filter_by(user_id=user_id).first()

    if not game_state:
        default_state = {
            'player': request.user.get('email').split('@')[0].capitalize(),
            'restaurant': "Neural Noms",
            'day': 1,
            'money': 200.00,
            'inventory': {
                'Tomato': 3,
                'Cheese': 2,
                'Basil': 5
            }
        }
        game_state = UserGameState(user_id=user_id, state=default_state)
        db.session.add(game_state)
        db.session.commit()

    return jsonify(game_state.state)
# ✅ Handle gameplay message
@app.route('/api/message', methods=['POST'])
@token_required
def handle_message():
    user_id = request.user.get('id')
    message = request.json.get('message', '').strip()

    if not message:
        return jsonify({'error': 'No message provided'}), 400

    game_state = UserGameState.query.filter_by(user_id=user_id).first()

    if not game_state:
        return jsonify({'error': 'Game state not found'}), 404

    state = game_state.state

    # Basic mock AI response
    ai_response = f"You said: '{message}'. The chef nods thoughtfully."

    # Example: change state if keyword detected
    if "cook" in message.lower():
        state['money'] += 5.00
        ai_response += " You cooked a dish and earned $5!"

    if "next day" in message.lower():
        state['day'] += 1
        ai_response += f" It is now day {state['day']}."

    game_state.state = state
    db.session.commit()

    return jsonify({
        'response': ai_response,
        'new_state': state
    })
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
