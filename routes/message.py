from flask import Blueprint, request, jsonify

message_bp = Blueprint('message', __name__)

@app.route('/api/message', methods=['POST'])
@token_required
def handle_message():
    user_id = request.user.get('user_id')
    
    message = request.json.get('message', '').strip()
    if not message:
        return jsonify({'error': 'No message provided'}), 400

    user = User.query.get(user_id)
    if not user or not user.game_state:
        return jsonify({'error': 'Game state not found'}), 404

    state = user.game_state
    full_message = (
        f"Day: {state.get('day', 1)}\n"
        f"Money: ${state.get('money', 0.00):.2f}\n"
        f"Inventory: {state.get('inventory', {})}\n"
        f"Last meal completed: {user.last_meal_completed or 'breakfast'}\n"
        f"User action: {message}"
    )

    try:
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

        print("Groq response status code:", response.status_code)
        print("Groq response raw text:", repr(response.text))
        print("Groq response raw content:", response.content)

        if response.status_code != 200:
            return jsonify({'error': f'Groq API request failed with status {response.status_code}'}), 500

        try:
            groq_data = response.json()
            ai_json = groq_data['choices'][0]['message']['content'].strip()
        except Exception as e:
            print("Groq response parsing failed:", str(e))
            print("Groq response raw text again:", repr(response.text))
            return jsonify({'error': f'Failed to parse Groq response: {str(e)}'}), 500

        try:
            parsed = json.loads(ai_json)
        except Exception as e:
            print("Failed to parse AI JSON content:", str(e))
            print("AI JSON content was:", ai_json)
            return jsonify({'error': f'Groq content was not valid JSON: {str(e)}'}), 500

        narration = parsed.get('narration', '')
        should_apply = True

        if 'Would you like to proceed with the purchase?' in narration:
            msg_lower = message.lower()
            if 'yes' not in msg_lower:
                should_apply = False

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
                    change_amount = int(change)
                    inventory[item] = inventory.get(item, 0) + change_amount
                except (ValueError, TypeError):
                    continue
            user.inventory = inventory

        user.game_state = state
        db.session.commit()

        return jsonify({
            'response': narration,
            'earned': earned,
            'new_state': state
        })

    except (requests.RequestException, json.JSONDecodeError) as e:
        return jsonify({'error': f'Request or JSON error: {str(e)}'}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500
