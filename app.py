import os
import json
import random
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import psycopg
from psycopg.rows import dict_row
from datetime import datetime

app = Flask(__name__)
CORS(app)

# --- KONFIGURATION & TEAM-STÄRKEN ---
# Power-Levels (0-100) beeinflussen die Simulation
TEAM_STRENGTHS = {
    "Argentinien": 92, "Frankreich": 91, "Brasilien": 89, "England": 88,
    "Spanien": 87, "Deutschland": 85, "Niederlande": 84, "Portugal": 86,
    "Kroatien": 82, "Marokko": 80, "Schweiz": 78, "USA": 75, "Japan": 77
}

# Standardwert für Teams, die nicht in der Liste stehen
DEFAULT_STRENGTH = 70

# --- DATENBANK FUNKTIONEN ---
def get_db_connection():
    # Railway stellt DATABASE_URL automatisch bereit
    return psycopg.connect(os.getenv('DATABASE_URL'), row_factory=dict_row)

def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Tabelle für Vorhersagen
            cur.execute('''
                CREATE TABLE IF NOT EXISTS predictions (
                    id SERIAL PRIMARY KEY,
                    nickname VARCHAR(50) UNIQUE NOT NULL,
                    selections JSONB NOT NULL,
                    score INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Tabelle für die simulierten "echten" Ergebnisse
            cur.execute('''
                CREATE TABLE IF NOT EXISTS tournament_results (
                    id SERIAL PRIMARY KEY,
                    results JSONB NOT NULL,
                    is_final BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        conn.commit()

# --- ROUTES ---

@app.route('/')
def index():
    # Einfaches HTML-Template direkt in Python, damit das Frontend sofort läuft
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="de">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>WM Tippspiel Simulation</title>
        <style>
            body { font-family: sans-serif; max-width: 600px; margin: 20px auto; padding: 0 10px; background: #f4f4f9; }
            .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
            input, button { width: 100%; padding: 10px; margin: 10px 0; border-radius: 4px; border: 1px solid #ddd; box-sizing: border-box; }
            button { background: #007bff; color: white; border: none; cursor: pointer; font-weight: bold; }
            h1 { color: #333; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🏆 WM Tippspiel</h1>
            <p>Gib deinen Nicknamen ein und wähle deinen Weltmeister für die Simulation!</p>
            <input type="text" id="nickname" placeholder="Dein Nickname">
            <select id="winner" style="width:100%; padding:10px;">
                <option value="Argentinien">Argentinien</option>
                <option value="Frankreich">Frankreich</option>
                <option value="Deutschland">Deutschland</option>
                <option value="Brasilien">Brasilien</option>
                <option value="Spanien">Spanien</option>
            </select>
            <button onclick="submitTip()">Tipp abgeben</button>
            <div id="msg"></div>
        </div>

        <script>
            async function submitTip() {
                const nick = document.getElementById('nickname').value;
                const win = document.getElementById('winner').value;
                if(!nick) return alert("Nickname fehlt!");

                const res = await fetch('/predict', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({nickname: nick, selections: {winner: win}})
                });
                const data = await res.json();
                document.getElementById('msg').innerText = data.message || data.error;
            }
        </script>
    </body>
    </html>
    ''')

@app.route('/predict', methods=['POST'])
def submit_prediction():
    data = request.json
    nickname = data.get('nickname')
    selections = data.get('selections')
    
    if not nickname or not selections:
        return jsonify({'error': 'Daten unvollständig'}), 400
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO predictions (nickname, selections) VALUES (%s, %s)',
                    (nickname, json.dumps(selections))
                )
            conn.commit()
        return jsonify({'success': True, 'message': 'Tipp erfolgreich gespeichert!'}), 201
    except psycopg.IntegrityError:
        return jsonify({'error': 'Dieser Nickname ist schon vergeben!'}), 409

@app.route('/simulate', methods=['POST'])
def simulate_tournament():
    # Simulation basierend auf Power-Levels
    teams = list(TEAM_STRENGTHS.keys())
    
    # Gewichtete Auswahl: Teams mit höherem Power-Level erscheinen öfter in der Lostrommel
    weighted_pool = []
    for team, strength in TEAM_STRENGTHS.items():
        weighted_pool.extend([team] * strength)
    
    winner = random.choice(weighted_pool)
    
    # Speichere das Simulationsergebnis
    results = {"winner": winner, "simulated_at": datetime.now().isoformat()}
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO tournament_results (results) VALUES (%s)', [json.dumps(results)])
            # Hier könnte man jetzt die Punkte aller User berechnen
        conn.commit()
    
    return jsonify({
        'status': 'Simulation abgeschlossen',
        'winner': winner
    })

@app.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT nickname, score FROM predictions ORDER BY score DESC LIMIT 10')
            scores = cur.fetchall()
    return jsonify(scores)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'database': 'connected'})

if __name__ == '__main__':
    # Initialisiere DB beim Start
    init_db()
    # Port 5000 ist Standard für viele Cloud-Hoster
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))