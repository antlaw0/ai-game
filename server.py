from flask import Flask, request, jsonify
import psycopg2

app = Flask(__name__)

# PostgreSQL Connection
DB_CONFIG = {
    "dbname": "your_database",
    "user": "your_username",
    "password": "your_password",
    "host": "your_server_ip",
    "port": "5432"  # Default PostgreSQL port
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

@app.route('/get_response', methods=['GET'])
def get_response():
    player_input = request.args.get('input')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT ai_response FROM game_memory WHERE player_input = %s", (player_input,))
    row = cur.fetchone()
    conn.close()

    return jsonify({"response": row[0] if row else None})

@app.route('/save_response', methods=['POST'])
def save_response():
    data = request.json
    player_input = data["input"]
    ai_response = data["response"]

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO game_memory (player_input, ai_response) VALUES (%s, %s) ON CONFLICT (player_input) DO UPDATE SET ai_response = EXCLUDED.ai_response", (player_input, ai_response))
    conn.commit()
    conn.close()

    return jsonify({"message": "Response saved!"})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
