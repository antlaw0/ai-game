from flask import Flask, render_template, redirect, url_for, request, make_response, jsonify
import jwt
import os
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from extensions import db
from models import User
import requests

SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('NEON_DB_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama3-70b-8192"
REMOVED_SECRET = os.getenv('REMOVED_SECRET')  # You can hardcode for dev, but env var is safer
GROQ_SYSTEM_PROMPT = (
    "You are a helpful cooking simulator AI chef assistant. "
    "Keep responses concise and game-like. Your job is to act like a game master in a table-top role-playing game where the player tells you what actions they want to take or asks questions where you respond similar to a game master would. There is a Cooking Emporium store where the player can buy all the ingrediants and cooking supplies they need to cook meals with. The player starts out owning a small, one-person food stand on a busy city street. All they start out with is a hot plate and $200 to spend. They must make 4 meals a day, breakfast, lunch, dinner, and dessert. Your main job is to evaluate the way and what they cook as if you are a judge in a cooking competition such as Iron Chef. You give them a score out of 10 for taste, technique, presentation, and creativity. Add these scores up to give them their overall score for the meal. They receive $20 multiplied by their score for the meal which is added to their total amount of money. Then the game progresses to the next meal, and so on until the end of the day where you recap their day, progress they made and then facilitate moving to the next day where they do this all again trying to get a high score and earn as much money as possible."
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
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
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

@app.route('/api/user-data')
@token_required
def get_user_data():
    user_id = request.user.get('user_id')
    data = {
        'user_id': user_id,
        'favorite_recipes': ['AI Salad Supreme', 'Neural Noodles'],
        'experience_level': 'Sous Chef'
    }
    return jsonify(data)

@app.route('/api/state', methods=['POST'])
@token_required
def get_game_state():
    user_id = request.user.get('user_id')
    user = User.query.get(user_id)

    if not user:
        user = User(id=user_id, game_state=None, inventory={}, money=0.0, day=1)
        db.session.add(user)
        db.session.commit()

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
            }
        }
        user.game_state = default_state
        user.inventory = default_state['inventory']
        user.money = default_state['money']
        user.day = default_state['day']
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

    # 🧠 Call Groq API
    try:
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {REMOVED_SECRET}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": GROQ_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": message
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 256,
                "top_p": 1,
                "stream": False
            }
        )

        # ✅ Handle non-200 responses from Groq
        if response.status_code != 200:
            try:
                error_detail = response.json()
            except ValueError:
                error_detail = {"message": "Invalid JSON returned from Groq."}

            print("Groq API Error:", error_detail)
            return jsonify({
                'error': 'Groq API request failed',
                'status_code': response.status_code,
                'detail': error_detail
            }), 500

        ai_content = response.json()['choices'][0]['message']['content']

    except requests.exceptions.RequestException as e:
        print("RequestException:", str(e))
        return jsonify({'error': f'Network or request error: {str(e)}'}), 500

    except Exception as e:
        print("Unhandled Exception:", str(e))
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

    # 🔄 Update game state based on user message
    if "cook" in message.lower():
        state['money'] += 5.00
    if "next day" in message.lower():
        state['day'] += 1

    user.game_state = state
    db.session.commit()

    return jsonify({
        'response': ai_content,
        'new_state': state
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
