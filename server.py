from flask import g, Flask, render_template, redirect, url_for, request, make_response, jsonify
import jwt
import tiktoken
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
import json
import re
from flask import jsonify

print("Game server current UTC time:", datetime.datetime.now(datetime.timezone.utc))


SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set in environment variables.")
#print("SECRET_KEY is "+SECRET_KEY)
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('NEON_DB_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 1800  # 30 minutes
}

@app.before_request
def before_request_log():
    safe_log(f"--> Incoming request: {request.method} {request.path}")
    if request.is_json:
        safe_log("Request JSON:", request.get_json())

@app.after_request
def after_request_log(response):
    safe_log(f"<-- Response status: {response.status}")
    return response

db.init_app(app)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama3-70b-8192"
GROQ_SYSTEM_PROMPT = """
You are the AI game master for a restaurant management and cooking simulation game.

Your job is to guide the player through each in-game day by responding to their messages in two parts:
    
1. A vivid and short narration of what happens.
2. A valid JSON object wrapped in <json>...</json> tags.

The JSON must include:
- narration: A 1–2 sentence summary of what the player did and the outcome based on the Game Rules listed later in this system prompt.
- updates: An object with fields like money, inventory, day, last_meal_completed, etc.
Always ensure the <json> block contains a complete and valid JSON object. Do not forget to close all brackets.
Example format (after player submits their meal description and actions such as:  I combine flour and eggs to form the pancake batter. I then cook the pancakes on the griddle until golden brown. I top with blueberry preserves with maple syrup and serve.):

<json>
{
  "narration": "You prepare a delicious stack of pancakes with syrup and berries.
Evaluation:  
Taste:  7/10-  The pancakes are fluffy and cooked to perfection.
Technique:  6/10- Execution was well done but you could have mixed dry and wet ingredients     separately before combining.
Presentation:  8/10-  The pancakes topped with the blueberries look pleasing to the eye and the colors work well together to enhance the culinary experience.
Creativity:  5/10- These are standard blueberry pancakes. You could have applied some unique twist on this classic dish.
Total score:  26/40
Well done. With a score of 26, you earn $520. 

",
  "updates": {
    "money": "+520.0",
    "inventory": {
      "flour": "-1",
      "eggs": "-2"
    },
    "day": 2,
    "last_meal_completed": "breakfast"
  }
}
}
</json>

Do not include any commentary or explanation outside of the narration and JSON. As for the inventory inside the json, the "-+" and "-2" indicate that the inventory item should be reduced or increased by that amount, "+" increase and "-" decrease. If an item quantity reaches 0 or less, remove that item from the inventory list. As for the money, the "+" indicates you add that amount to the player's current money value and a "-" means you decrease the player's money by that amount. Ensure these numbers are a string and not an integer or float in the json.
Use the chat history to maintain continuity. If the last user message is a response to a prior prompt (e.g. "yes", "no", "cancel"), you must interpret it in context of the most recent messages in the chat history.

The chat history is passed to you as a list of previous turns in the conversation. Each entry contains:
- "user": the player’s message
- "ai": your last response (including "narration" and optional "updates")

## Game Rules ##
1. The game starts at day 1 with breakfast.
2. After "breakfast" is completed, the next meal is "lunch", then "dinner".
3. Completing "dinner" advances the day by 1 and resets the meal to "breakfast".
4. Prices and money must be respected. Do not allow purchases the player cannot afford.
5. If the player tries to cheat or say nonsense, respond in-character and guide them back into the game.
6. If the player wants to buy ingredients or cooking supplies, You must give them a list of the item or items they want to purchase along with the quantity and price per quantity and then the total price for the quantity multiplied by the price per quantity. On the final line, give them the grand total of the entire purchase. It should look like this for example:
    --- example ---
      <json>
      {
      "narration":
      "Items in your cart:
        * 1 whole fresh chicken $25 total:  $25
        * 3 watermelons $15 total:  $45
        Grand Total$70
        You have $150. After this purchase you will have $80. Would you like to proceed with this purchase? ",
        "updates": {}
        }
        </json>
        
        
--- end of example ---
If the player does not have enough money for the purchase, do not let them make the purchase and tell them they do not have enough money for that transaction. This format must be followed so the player is informed of what is in their cart along with prices and you must ask them if they would like to proceed with the purchase. If they respond yes, process the purchase and tell them the purchase was successful and list the items added to their inventory and updated amount of money after the purchase.
Here is an example response if the player has enough money and responds yes to proceeding with the transaction:
    ## example response based on transaction ##
    <json>
{
  "narration": "
  You purchased:
  * 1 whole fresh chicken $25 total:  $25
        * 3 watermelons $15 total:  $45
You pay $70 for these items.        
        ",
  "updates": {
    "money": "-70",
    "inventory": {
      "Whole fresh chicken": "+1",
      "Watermelon": "+3"
    }
    }
}
</json>

    ## end of example response ##
7. For each meal, you are to give the player a score in certain categories as you evaluate the description of what and how they cook the meal. The categories are:
    * Taste:  Do the flavors match well together? Did they use proper ingredients and technique to enhance taste?
    * Technique:  Did they demonstrate cooking skill and applied knowledge and experience as they prepare the dish?
    * Presentation:  Did they pay attention to asthetics so the meal presentation is pleasing to the eye? Did they use proper colors and textures?
    * Creativity:  Did they demonstrate creative ways to prepare the meal, creative dish ideas, twists on classic dishes, etc.
    Assign the player a score in each category from 1 to 10 where 1 is the worst and 10 is the best. Add up all the categories and give them a final score. The player receives money based on the score. The total money they receive should be the score multiplied by20. Then advance to the next meal for that day or if at the end of the day, give the player a brief summary of the day, advance the day count by 1 and reset the current meal to 'breakfast'. Make sure to tell the player their score you gave them in each category and why they received that score. If they did poorly for some reason in that category also give them feedback on what could have been better. Finally, tell them their final score and how much money they earned for that meal. Lastly, tell them now its time for the next meal (breakfast, lunch, or dinner).
    8. Do not allow the player to use ingredients they do not have in their inventory. If they try to use an ingredient they do not have, do not proceed with that meal and inform them they do not have that item or ingredient and must purchase it for use. 
    

Be fun, creative, and logical.
"""

def count_tokens(text, model="gpt-3.5-turbo"):
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))

def count_message_tokens(messages, model="gpt-3.5-turbo"):
    enc = tiktoken.encoding_for_model(model)
    tokens = 0
    for msg in messages:
        tokens += 4  # Base tokens per message (role, name, etc.)
        for key, value in msg.items():
            tokens += len(enc.encode(value))
    tokens += 2  # Priming
    return tokens


import sys
import traceback

def safe_log(*args, **kwargs):
    try:
        msg = " ".join(str(a) for a in args)
        sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="ignore"))
        sys.stdout.flush()
    except Exception as log_err:
        with open("error_log.txt", "a", encoding="utf-8") as f:
            f.write("Logging failed: " + str(log_err) + "\n")
            f.write(traceback.format_exc() + "\n")





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


def count_tokens(text, model="gpt-3.5-turbo"):
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))


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


def get_user_from_token():
    user_id = g.user['user_id']
    user = db.session.get(User, user_id)
    return user

def build_state_summary(user):
    return (
        f"Current game state:\n"
        f"Money: ${user.money}\n"
        f"Inventory: {json.dumps(user.inventory or {})}\n"
        f"Day: {user.day}\n"
        f"Last meal completed: {user.last_meal_completed or 'breakfast'}\n"
    )

def build_history_summary(chat_history):
    if not chat_history:
        return ""
    return "\n".join([
        f"User: {entry.get('user', '[missing]')}\nAI: {entry.get('ai', '[missing]')}"
        for entry in chat_history[-5:] if isinstance(entry, dict)
    ])

def build_groq_payload(user, user_input, max_chat_history=10):
    messages = []

    # Add system prompt
    messages.append({"role": "system", "content": GROQ_SYSTEM_PROMPT})

    # Add recent chat history
    if user.chat_history:
        for entry in user.chat_history[-max_chat_history:]:
            if "user" in entry:
                messages.append({"role": "user", "content": entry["user"]})
            if "ai" in entry:
                # ai can be dict or string
                if isinstance(entry["ai"], dict):
                    messages.append({"role": "assistant", "content": json.dumps(entry["ai"])})
                else:
                    messages.append({"role": "assistant", "content": str(entry["ai"])})

    # Add the current player message
    messages.append({"role": "user", "content": user_input})

    return {
        "model": GROQ_MODEL,  
        "messages": messages,
        "temperature": 0.7
    }

def parse_groq_response(response, user):
    parsed = None
    try:
        response_json = response.json()
        raw_text = response_json["choices"][0]["message"]["content"].strip()

        print("Groq raw text response:", raw_text)

        # Extract JSON from <json>...</json> block
        match = re.search(r"<json>\s*(\{.*?\})\s*</json>", raw_text, re.DOTALL)
        if not match:
            print("Error: <json> tags not found or invalid JSON format.")
            return None, {
                "narration": "Sorry, the game master's response was confusing. Try again!",
                "updates": {}
            }

        json_str = match.group(1).strip()

        # Fix unescaped newlines in "narration" value
        json_str = re.sub(r'("narration"\s*:\s*")((?:[^"\\]|\\.)*?)"', 
                          lambda m: f'"narration": "{m.group(2).replace(chr(10), "\\n").replace(chr(13), "")}"',
                          json_str,
                          flags=re.DOTALL)

        print("Extracted and cleaned JSON:", json_str)

        parsed = json.loads(json_str)
        updates = parsed.get("updates", {})

        # --- Money delta ---
        money_delta = updates.get("money")
        if isinstance(money_delta, str):
            try:
                user.money += float(money_delta)
                print(f"Updated money by {money_delta}, new balance: {user.money}")
            except ValueError:
                print(f"Invalid money delta: {money_delta}")
        elif isinstance(money_delta, (int, float)):
            user.money = money_delta
            print(f"Set money to {user.money}")

        # --- Inventory delta ---
        inventory_delta = updates.get("inventory", {})
        if isinstance(inventory_delta, dict):
            if user.inventory is None:
                user.inventory = {}

            for item, change in inventory_delta.items():
                try:
                    change_amount = float(change)
                except ValueError:
                    print(f"Invalid inventory change for {item}: {change}")
                    continue

                current_qty = user.inventory.get(item, 0)
                new_qty = current_qty + change_amount
                if new_qty <= 0:
                    user.inventory.pop(item, None)
                else:
                    user.inventory[item] = new_qty
                print(f"Updated inventory: {item} {current_qty} -> {user.inventory.get(item, 0)}")

        user.day = updates.get("day", user.day)
        user.last_meal_completed = updates.get("last_meal_completed", user.last_meal_completed)

        db.session.commit()

        return raw_text, parsed

    except Exception as e:
        print("Unexpected error in parse_groq_response:", str(e))
        print("Invalid Groq content:", json.dumps(parsed, indent=2) if parsed else "(No parsed content)")
        return None, {
            "narration": "An unexpected error happened while processing the game master's reply. Try again!",
            "updates": {}
        }

def extract_json_tagged_response(text):
    """Extracts and parses JSON from a <json>...</json> section in the AI response."""
    match = re.search(r"<json>(.*?)</json>", text, re.DOTALL)
    if not match:
        raise ValueError("No <json> section found in AI response.")
    json_str = match.group(1).strip()
    return json.loads(json_str)

def safe_print(*args, **kwargs):
    safe_args = [str(arg).encode("ascii", errors="ignore").decode("ascii") for arg in args]
    print(*safe_args, **kwargs)

import traceback

def safe_print(*args, **kwargs):
    safe_args = [str(arg).encode("ascii", errors="ignore").decode("ascii") for arg in args]
    print(*safe_args, **kwargs)

from flask import Response

@app.route("/api/message", methods=["POST"])
@token_required
def message():
    try:
        print("[INFO] /api/message route hit")

        data = request.get_json()
        print("[DEBUG] Incoming data:", data)

        user = get_user_from_token()
        if not user:
            print("[WARN] User not found.")
            return Response(json.dumps({"error": "User not found"}), status=404, mimetype="application/json")

        player_message = data.get("message", "").strip()
        if not player_message:
            print("[WARN] No message provided.")
            return Response(json.dumps({"error": "No message provided"}), status=400, mimetype="application/json")

        # Include chat history in the payload
        payload = build_groq_payload(user, player_message)
        system_token_count = count_tokens(payload["messages"][0]["content"])
        chat_token_count = count_message_tokens(payload["messages"][1:-1])
        user_token_count = count_tokens(payload["messages"][-1]["content"])
        print("[TOKENS] System Prompt:", system_token_count)
        print("[TOKENS] Chat History:", chat_token_count)
        print("[TOKENS] Latest User Message:", user_token_count)
        print("[TOKENS] Total Prompt Tokens:", system_token_count + chat_token_count + user_token_count)
        response = call_groq_api(payload)

        print("[DEBUG] Groq status:", response.status_code)

        if response.status_code != 200:
            print("[ERROR] Groq API failed:", response.text)
            return Response(json.dumps({"error": "Groq API failed", "response_text": response.text}), status=500, mimetype="application/json")

        ai_content, parsed = parse_groq_response(response, user)

        if parsed is None:
            print("[ERROR] Parsed is None.")
            return Response(json.dumps({
                "error": "AI response was invalid",
                "fallback_narration": "Try again later"
            }), status=500, mimetype="application/json")

        # Append to chat history using trimmed format
        user.chat_history.append({
            "user": player_message,
            "ai": {
                "narration": parsed.get("narration", ""),
                "updates": parsed.get("updates", {})
            }
        })

        db.session.commit()

        print("[INFO] Success. Returning parsed.")
        return Response(json.dumps(parsed), mimetype="application/json")

    except Exception as e:
        import traceback
        print("[FATAL] Exception in /api/message")
        print(traceback.format_exc())
        return Response(json.dumps({
            "error": "Unexpected server error",
            "trace": traceback.format_exc()
        }), status=500, mimetype="application/json")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)