import os
import json
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Database connection
def get_db():
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    return conn

# Initialize database
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            id SERIAL PRIMARY KEY,
            nickname VARCHAR(50) UNIQUE NOT NULL,
            predictions JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

@app.route('/predict', methods=['POST'])
def submit_prediction():
    data = request.json
    nickname = data.get('nickname')
    predictions = data.get('predictions')
    
    if not nickname or not predictions:
        return jsonify({'error': 'Missing nickname or predictions'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            'INSERT INTO predictions (nickname, predictions) VALUES (%s, %s)',
            (nickname, json.dumps(predictions))
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Prediction saved'}), 201
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({'error': 'Nickname already taken'}), 409
    finally:
        cur.close()
        conn.close()

@app.route('/predictions', methods=['GET'])
def get_predictions():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT nickname, predictions, created_at FROM predictions ORDER BY created_at')
    predictions = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(predictions)

@app.route('/simulate', methods=['POST'])
def simulate_tournament():
    teams = [
        "Argentina", "France", "Brazil", "England", "Spain", "Germany",
        "Netherlands", "Belgium", "Portugal", "Uruguay", "Mexico", "USA",
        "Japan", "South Korea", "Senegal", "Morocco", "Poland", "Australia",
        "Switzerland", "Denmark", "Croatia", "Serbia", "Canada", "Costa Rica",
        "Ghana", "Tunisia", "Cameroon", "Ecuador", "Iran", "Saudi Arabia",
        "Wales", "Qatar"
    ]
    
    winner = random.choice(teams)
    runner_up = random.choice([t for t in teams if t != winner])
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT nickname, predictions FROM predictions')
    all_predictions = cur.fetchall()
    cur.close()
    conn.close()
    
    return jsonify({
        'winner': winner,
        'runner_up': runner_up,
        'predictions': all_predictions
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)