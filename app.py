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
EVENT_ACCESS_CODE = "WM2026" # Der Parameter, der in der URL stehen muss

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
    # 1. URL-Parameter prüfen, bevor die Seite überhaupt geladen wird
    access_code = request.args.get('access')
    if access_code != EVENT_ACCESS_CODE:
        return "<h1>Zugriff verweigert</h1><p>Bitte scanne den offiziellen QR-Code vor Ort.</p>", 403

    # Einfaches HTML-Template direkt in Python
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
            input[type="text"], select { width: 100%; padding: 10px; margin: 10px 0; border-radius: 4px; border: 1px solid #ddd; box-sizing: border-box; }
            button { width: 100%; padding: 10px; margin: 10px 0; background: #007bff; color: white; border: none; cursor: pointer; font-weight: bold; border-radius: 4px; }
            h1 { color: #333; }
            .hp-field { display: none; } /* Versteckt den Honeypot */
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🏆 WM Tippspiel</h1>
            <p>Gib deinen Nicknamen ein und wähle deinen Weltmeister für die Simulation!</p>
            
            <div class="hp-field" aria-hidden="true">
                <input type="text" id="bot_email" name="email_hp" tabindex="-1" autocomplete="off" placeholder="Leave empty">
            </div>

            <input type="text" id="nickname" placeholder="Dein Nickname">
            <select id="winner">
                <option value="Argentinien">Argentinien</option>
                <option value="Frankreich">Frankreich</option>
                <option value="Deutschland">Deutschland</option>
                <option value="Brasilien">Brasilien</option>
                <option value="Spanien">Spanien</option>
            </select>
            <button onclick="submitTip()">Tipp abgeben</button>
            <div id="msg" style="margin-top: 10px; font-weight: bold;"></div>
        </div>

        <script>
            async function submitTip() {
                const nick = document.getElementById('nickname').value;
                const win = document.getElementById('winner').value;
                const honeypot = document.getElementById('bot_email').value; // Wert des versteckten Feldes
                
                // Access-Code aus der URL auslesen
                const urlParams = new URLSearchParams(window.location.search);
                const accessCode = urlParams.get('access');

                if(!nick) return alert("Nickname fehlt!");

                const res = await fetch('/predict', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        nickname: nick, 
                        selections: {winner: win},
                        access_token: accessCode, // Code mitschicken
                        email_hp: honeypot        // Honeypot mitschicken
                    })
                });
                const data = await res.json();
                
                const msgDiv = document.getElementById('msg');
                msgDiv.innerText = data.message || data.error;
                msgDiv.style.color = data.success ? 'green' : 'red';
            }
        </script>
    </body>
    </html>
    ''')

@app.route('/predict', methods=['POST'])
def submit_prediction():
    data = request.json
    
    # 2. Honeypot prüfen: Ist das Feld ausgefüllt? -> Bot!
    if data.get('email_hp'):
        return jsonify({'error': 'Bot-Aktivität erkannt!'}), 418

    # 3. Access-Code prüfen: Darf dieser Request speichern?
    if data.get('access_token') != EVENT_ACCESS_CODE:
        return jsonify({'error': 'Nicht autorisiert. Falscher Event-Code.'}), 403

    nickname = data.get('nickname')
    selections = data.get('selections')
    
    # Kleine Validierung des Nicknamens
    if not nickname or len(nickname.strip()) < 2:
        return jsonify({'error': 'Bitte einen gültigen Nicknamen eingeben.'}), 400
    if not selections:
        return jsonify({'error': 'Daten unvollständig'}), 400
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO predictions (nickname, selections) VALUES (%s, %s)',
                    (nickname.strip(), json.dumps(selections))
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
    # Port 8080 oder den von Railway zugewiesenen Port nutzen
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))