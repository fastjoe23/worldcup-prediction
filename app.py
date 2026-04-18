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

# --- SESSION CONFIGURATION ---
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

CORS(app, supports_credentials=True)
csrf = CSRFProtect(app)
limiter = Limiter(app=app, key_func=get_remote_address)
Talisman(app,
         force_https=os.getenv('FLASK_ENV') == 'production',
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
PHASES = ["START", "RUNDE_1_NICKNAME", "RUNDE_1_GRUPPEN_TIPP", "RUNDE_1_SIM", "RUNDE_2_TIPP", "FINALE_TIPP", "ENDE"]

TEAM_STRENGTHS = {
    "Argentinien": 92, "Frankreich": 91, "Brasilien": 89, "Deutschland": 85, "Spanien": 87
}

# WM 2026 Gruppen und Teams
GROUPS = {
    "Gruppe A": ["Mexiko", "Südafrika", "Südkorea", "Tschechien"],
    "Gruppe B": ["Kanada", "Bosnien & Herzegowina", "Katar", "Schweiz"],
    "Gruppe C": ["Brasilien", "Marokko", "Haiti", "Schottland"],
    "Gruppe D": ["USA", "Paraguay", "Australien", "Türkei"],
    "Gruppe E": ["Deutschland", "Curaçao", "Elfenbeinküste", "Ecuador"],
    "Gruppe F": ["Niederlande", "Japan", "Schweden", "Tunesien"],
    "Gruppe G": ["Belgien", "Ägypten", "Iran", "Neuseeland"],
    "Gruppe H": ["Spanien", "Kap Verde", "Saudi-Arabien", "Uruguay"],
    "Gruppe I": ["Frankreich", "Senegal", "Irak", "Norwegen"],
    "Gruppe J": ["Argentinien", "Algerien", "Österreich", "Jordanien"],
    "Gruppe K": ["Portugal", "DR Kongo", "Usbekistan", "Kolumbien"],
    "Gruppe L": ["England", "Kroatien", "Ghana", "Panama"]
}

# Statische Test-Ergebnisse für die Simulation (erstes Team jeder Gruppe)
TEST_RESULTS = {
    "Gruppe A": "Mexiko",
    "Gruppe B": "Kanada",
    "Gruppe C": "Brasilien",
    "Gruppe D": "USA",
    "Gruppe E": "Deutschland",
    "Gruppe F": "Niederlande",
    "Gruppe G": "Belgien",
    "Gruppe H": "Spanien",
    "Gruppe I": "Frankreich",
    "Gruppe J": "Argentinien",
    "Gruppe K": "Portugal",
    "Gruppe L": "England"
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
    """Validate selections data for group winners"""
    if not isinstance(selections, dict):
        return False, "Selections müssen ein Objekt sein"
    if json.dumps(selections).__sizeof__() > MAX_SELECTIONS_SIZE:
        return False, "Selections zu groß"
    
    # Check that exactly 12 groups are present
    if len(selections) != 12:
        return False, "Es müssen exakt 12 Gruppen-Tipps eingereicht werden"
    
    # Validate each group selection
    for group_name, selected_team in selections.items():
        # Check if group exists
        if group_name not in GROUPS:
            return False, f"Ungültige Gruppe: {group_name}"
        
        # Check if selected team is in the group
        if selected_team not in GROUPS[group_name]:
            return False, f"Team '{selected_team}' nicht in {group_name}"
    
    return True, None

# Scoring-Logik für verschiedene Phasen
def calculate_score(user_selections, test_results, phase):
    """
    Calculate score for user selections based on test results and phase.
    Can be extended for different scoring rules per phase.
    
    Args:
        user_selections: Dict with group_name -> selected_team
        test_results: Dict with group_name -> correct_team
        phase: Current phase (e.g., "RUNDE_1_GRUPPEN_TIPP")
    
    Returns:
        Integer score (number of correct predictions)
    """
    score = 0
    
    # Standard scoring: 1 point per correct match
    # Can be extended for different phases with different multipliers
    if "GRUPPEN_TIPP" in phase:
        # Group winner predictions: 1 point per correct team
        for group, user_team in user_selections.items():
            if group in test_results and test_results[group] == user_team:
                score += 1
    
    # Add phase-specific scoring rules here as needed
    # Example: elif "FINALE" in phase: score = user_team == test_results ? 10 : 0
    
    return score

# --- DATENBANK ---
def get_db_connection():
    return psycopg.connect(os.getenv('DATABASE_URL'), row_factory=dict_row)

def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Tabelle für Teilnehmer (live Übersicht während Nickname-Phase)
            cur.execute('''CREATE TABLE IF NOT EXISTS participants (
                id SERIAL PRIMARY KEY, nickname VARCHAR(50) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
            # Tabelle für Tipps und Ergebnisse
            cur.execute('''CREATE TABLE IF NOT EXISTS predictions (
                id SERIAL PRIMARY KEY, nickname VARCHAR(50) NOT NULL,
                phase VARCHAR(50) NOT NULL,
                selections JSONB NOT NULL, score INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(nickname, phase))''')
            
            cur.execute('''CREATE TABLE IF NOT EXISTS tournament_results (
                id SERIAL PRIMARY KEY, results JSONB NOT NULL,
                is_final BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            
            # Tabelle für den Event-Status (nur 1 Zeile)
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

# Initialize database on module import (works with Gunicorn and local development)
init_db()

# --- HTML ROUTES (Die Seiten) ---

@app.route('/')
def index():
    access_code = request.args.get('access')
    if access_code != EVENT_ACCESS_CODE:
        return "<h1>Zugriff verweigert</h1><p>Bitte QR-Code scannen.</p>", 403
    # Set session to track authenticated users
    session['authenticated'] = True
    session.permanent = True
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

@app.route('/api/participants', methods=['GET'])
def get_participants():
    """Get list of all participants (nicknames) who have joined"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT nickname, created_at FROM participants ORDER BY created_at ASC')
                participants = cur.fetchall()
        return jsonify({
            'count': len(participants),
            'participants': participants
        })
    except Exception as e:
        return jsonify({'error': 'Fehler beim Abrufen der Teilnehmer'}), 500

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

@app.route('/api/submit-nickname', methods=['POST'])
@limiter.limit("10 per minute")  # Prevent spam
@csrf.exempt  # Exempt CSRF for API but enforce other validations
def submit_nickname():
    data = request.json
    if data.get('email_hp'): return jsonify({'error': 'Bot-Aktivität erkannt!'}), 418
    
    # Check session authentication
    if not session.get('authenticated'):
        if data.get('access_token') != EVENT_ACCESS_CODE:
            return jsonify({'error': 'Nicht autorisiert.'}), 403
    
    # Prüfen, ob wir in der Nickname-Phase sind
    if get_phase() != "RUNDE_1_NICKNAME":
        return jsonify({'error': 'Nickname-Phase ist nicht aktiv!'}), 403

    nickname = data.get('nickname')
    
    # Input validation
    valid, error = validate_nickname(nickname)
    if not valid:
        return jsonify({'error': error}), 400
    
    # Speichere Nickname in der Participants-Tabelle (für Live-Übersicht)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('INSERT INTO participants (nickname) VALUES (%s)', (nickname,))
            conn.commit()
    except psycopg.IntegrityError:
        return jsonify({'error': 'Dieser Nickname ist bereits vergeben! Bitte wähle einen anderen.'}), 409
    except Exception as e:
        print(f"Error saving participant: {e}")
        return jsonify({'error': f'Fehler beim Speichern des Nicknames: {str(e)}'}), 500
    
    return jsonify({'success': True, 'message': 'Nickname gespeichert!'})

@app.route('/api/submit-selections', methods=['POST'])
@limiter.limit("10 per minute")  # Prevent spam
@csrf.exempt  # Exempt CSRF for API but enforce other validations
def submit_selections():
    data = request.json
    if data.get('email_hp'): return jsonify({'error': 'Bot-Aktivität erkannt!'}), 418
    
    # Check session authentication
    if not session.get('authenticated'):
        if data.get('access_token') != EVENT_ACCESS_CODE:
            return jsonify({'error': 'Nicht autorisiert.'}), 403
    
    # Prüfen, ob wir in der Gruppen-Tipp-Phase sind
    if get_phase() != "RUNDE_1_GRUPPEN_TIPP":
        return jsonify({'error': 'Gruppen-Tipps sind aktuell nicht möglich!'}), 403

    # Nickname aus Request-Body auslesen (nicht aus Session)
    nickname = data.get('nickname')
    if not nickname:
        return jsonify({'error': 'Kein Nickname angegeben. Bitte zuerst Nickname wählen!'}), 400
    
    selections = data.get('selections')
    
    # Input validation
    valid, error = validate_selections(selections)
    if not valid:
        return jsonify({'error': error}), 400
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('INSERT INTO predictions (nickname, phase, selections) VALUES (%s, %s, %s)', (nickname, get_phase(), json.dumps(selections)))
            conn.commit()
        return jsonify({'success': True, 'message': 'Tipps gespeichert!'})
    except psycopg.IntegrityError:
        return jsonify({'error': 'Nickname bereits für diese Runde abgegeben!'}), 409
    except Exception as e:
        return jsonify({'error': f'Fehler beim Speichern: {str(e)}'}), 500

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
                cur.execute('DELETE FROM participants')
                cur.execute('DELETE FROM tournament_results')
                # Zurück auf Anfang setzen
                cur.execute('UPDATE system_state SET current_phase = %s WHERE id = 1', (PHASES[0],))
            conn.commit()
        return jsonify({'success': True, 'message': 'Datenbank komplett geleert!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/run-simulation', methods=['POST'])
@csrf.exempt
def run_simulation():
    """Run simulation for RUNDE_1_GRUPPEN_TIPP: save test results, calculate scores, update phase"""
    data = request.json
    if data.get('password') != ADMIN_PASSWORD:
        return jsonify({'error': 'Nicht autorisiert'}), 403
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # FAKE SIMULATION 
                # 1. Speichere TEST_RESULTS in tournament_results
                cur.execute(
                    'INSERT INTO tournament_results (results, is_final) VALUES (%s, %s)',
                    (json.dumps(TEST_RESULTS), True)
                )
                
                # 2. Hole alle predictions für RUNDE_1_GRUPPEN_TIPP
                cur.execute(
                    'SELECT id, nickname, selections FROM predictions WHERE phase = %s',
                    (PHASES[2],)  # RUNDE_1_GRUPPEN_TIPP
                )
                predictions = cur.fetchall()
                
                # 3. Berechne Punkte für jeden User
                for pred in predictions:
                    user_selections = json.loads(pred['selections']) if isinstance(pred['selections'], str) else pred['selections']
                    score = calculate_score(user_selections, TEST_RESULTS, "RUNDE_1_GRUPPEN_TIPP")
                    
                    # 4. Update score in predictions
                    cur.execute(
                        'UPDATE predictions SET score = %s WHERE id = %s',
                        (score, pred['id'])
                    )
                
                # 5. Setze Phase auf RUNDE_1_SIM
                cur.execute(
                    'UPDATE system_state SET current_phase = %s WHERE id = 1',
                    ("RUNDE_1_SIM",)
                )
            
            conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Simulation komplett! {len(predictions)} User bewertet.',
            'details': f'TEST_RESULTS: {TEST_RESULTS}'
        })
    except Exception as e:
        return jsonify({'error': f'Simulationsfehler: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))