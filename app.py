import os
import json
import random
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
import psycopg
from psycopg.rows import dict_row
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))
CORS(app, supports_credentials=True)
csrf = CSRFProtect(app)
limiter = Limiter(app=app, key_func=get_remote_address)
Talisman(app,
         force_https=True,
         content_security_policy={
        'default-src': "'self'",
        'script-src': [
            "'self'",
            "'unsafe-inline'"  # Erlaubt den <script> Block
        ],
        'style-src': [
            "'self'",
            "'unsafe-inline'"  # Erlaubt den <style> Block
        ]
    })

# --- KONFIGURATION ---
EVENT_ACCESS_CODE = os.getenv('EVENT_ACCESS_CODE', 'WM2026')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'change_me_in_env')
PHASES = ["START", "RUNDE_1_TIPP", "RUNDE_1_SIM", "RUNDE_2_TIPP", "FINALE_TIPP", "ENDE"]

TEAM_STRENGTHS = {
    "Argentinien": 92, "Frankreich": 91, "Brasilien": 89, "Deutschland": 85, "Spanien": 87
}

# Input validation constraints
MAX_NICKNAME_LENGTH = 50
MAX_SELECTIONS_SIZE = 5000  # Max JSON size in bytes

# --- INPUT VALIDATION ---
def validate_nickname(nickname):
    """Validate nickname input"""
    if not nickname or not isinstance(nickname, str):
        return False, "Nickname erforderlich"
    if len(nickname) > MAX_NICKNAME_LENGTH:
        return False, f"Nickname zu lang (max {MAX_NICKNAME_LENGTH})"
    if len(nickname) < 2:
        return False, "Nickname zu kurz (min 2)"
    # Allow only alphanumeric, spaces, and basic punctuation
    if not all(c.isalnum() or c in ' -_äöüßÄÖÜ' for c in nickname):
        return False, "Ungültige Zeichen im Nickname"
    return True, None

def validate_selections(selections):
    """Validate selections data"""
    if not isinstance(selections, dict):
        return False, "Selections müssen ein Objekt sein"
    if json.dumps(selections).__sizeof__() > MAX_SELECTIONS_SIZE:
        return False, "Selections zu groß"
    # Ensure selections has required fields
    if 'winner' not in selections:
        return False, "Winner erforderlich in Selections"
    if selections['winner'] not in TEAM_STRENGTHS.keys():
        return False, "Ungültiger Team-Auswahl"
    return True, None

# --- DATENBANK ---
def get_db_connection():
    return psycopg.connect(os.getenv('DATABASE_URL'), row_factory=dict_row)

def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Deine alten Tabellen
            cur.execute('''CREATE TABLE IF NOT EXISTS predictions (
                id SERIAL PRIMARY KEY, nickname VARCHAR(50) UNIQUE NOT NULL,
                selections JSONB NOT NULL, score INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
            cur.execute('''CREATE TABLE IF NOT EXISTS tournament_results (
                id SERIAL PRIMARY KEY, results JSONB NOT NULL,
                is_final BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
            # NEU: Tabelle für den Event-Status (nur 1 Zeile)
            cur.execute('''CREATE TABLE IF NOT EXISTS system_state (
                id INTEGER PRIMARY KEY, current_phase VARCHAR(50) NOT NULL)''')
            
            # Startwert setzen, falls leer
            cur.execute('INSERT INTO system_state (id, current_phase) VALUES (1, %s) ON CONFLICT DO NOTHING', (PHASES[0],))
        conn.commit()

# Hilfsfunktionen für den Status
def get_phase():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT current_phase FROM system_state WHERE id = 1')
            return cur.fetchone()['current_phase']

def set_phase(new_phase):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('UPDATE system_state SET current_phase = %s WHERE id = 1', (new_phase,))
        conn.commit()


# --- HTML ROUTES (Die Seiten) ---

@app.route('/')
def index():
    access_code = request.args.get('access')
    if access_code != EVENT_ACCESS_CODE:
        return "<h1>Zugriff verweigert</h1><p>Bitte QR-Code scannen.</p>", 403
    # Set session to track authenticated users
    session['authenticated'] = True
    session.permanent = True
    app.permanent_session_lifetime = 3600  # 1 hour
    # Flask lädt jetzt automatisch die Datei aus dem /templates Ordner!
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/dashboard')
def dashboard_page():
    return render_template('dashboard.html')


# --- API ROUTES (Daten & Logik) ---

@app.route('/api/state', methods=['GET'])
def current_state():
    return jsonify({'phase': get_phase()})

@app.route('/api/admin/set-phase', methods=['POST'])
@limiter.limit("5 per minute")  # Prevent brute force attempts
@csrf.exempt # Exempt CSRF for API but enforce other validations
def update_state():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Falsches Passwort'}), 403
    
    new_phase = data.get('phase')
    if new_phase in PHASES:
        set_phase(new_phase)
        return jsonify({'success': True, 'phase': new_phase})
    return jsonify({'error': 'Ungültige Phase'}), 400

@app.route('/predict', methods=['POST'])
@limiter.limit("10 per minute")  # Prevent spam
@csrf.exempt  # Exempt CSRF for API but enforce other validations
def submit_prediction():
    data = request.json
    if data.get('email_hp'): return jsonify({'error': 'Bot-Aktivität erkannt!'}), 418
    
    # Check session authentication
    if not session.get('authenticated'):
        # Fallback to access token validation for backward compatibility
        if data.get('access_token') != EVENT_ACCESS_CODE:
            return jsonify({'error': 'Nicht autorisiert.'}), 403
    
    # Prüfen, ob wir überhaupt in einer Tipp-Phase sind!
    if "TIPP" not in get_phase():
        return jsonify({'error': 'Die Tipprunde ist aktuell geschlossen!'}), 403

    nickname = data.get('nickname')
    selections = data.get('selections')
    
    # Input validation
    valid, error = validate_nickname(nickname)
    if not valid:
        return jsonify({'error': error}), 400
    
    valid, error = validate_selections(selections)
    if not valid:
        return jsonify({'error': error}), 400
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('INSERT INTO predictions (nickname, selections) VALUES (%s, %s)', (nickname, json.dumps(selections)))
            conn.commit()
        return jsonify({'success': True, 'message': 'Gespeichert!'})
    except psycopg.IntegrityError:
        return jsonify({'error': 'Nickname vergeben!'}), 409
    except Exception as e:
        return jsonify({'error': 'Fehler beim Speichern'}), 500

@app.route('/api/admin/reset-db', methods=['POST'])
@csrf.exempt # WICHTIG wegen deiner Security-Einstellungen
def reset_db():
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Nicht autorisiert'}), 403
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM predictions')
                cur.execute('DELETE FROM tournament_results')
                # Zurück auf Anfang setzen
                cur.execute('UPDATE system_state SET current_phase = %s WHERE id = 1', (PHASES[0],))
            conn.commit()
        return jsonify({'success': True, 'message': 'Datenbank komplett geleert!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))