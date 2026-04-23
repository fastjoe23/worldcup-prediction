import os
import json
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
import psycopg
from psycopg.rows import dict_row
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from simulation import WorldCupSimulation

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))
app.config["PHASE_CACHE"] = None

# --- SESSION CONFIGURATION ---
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 3600  # 1 hour
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

CORS(app, supports_credentials=True)
csrf = CSRFProtect(app)
limiter = Limiter(app=app, key_func=get_remote_address)
Talisman(
    app,
    force_https=os.getenv("FLASK_ENV") == "production",
    content_security_policy={
        "default-src": "'self'",
        "script-src": ["'self'", "'unsafe-inline'"],  # Erlaubt den <script> Block
        "style-src": ["'self'", "'unsafe-inline'"],  # Erlaubt den <style> Block
    },
)



# --- KONFIGURATION ---
EVENT_ACCESS_CODE = os.getenv("EVENT_ACCESS_CODE", "WM2026")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change_me_in_env")
PHASES = [
    "START",
    "RUNDE_1_NICKNAME",
    "RUNDE_1_GRUPPEN_TIPP",
    "RUNDE_1_SIM",
    "RUNDE_2_TIPP",
    "RUNDE_2_SIM",
    "FINALE_TIPP",
    "FINALE_SIM",
    "ENDE",
]

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
    if not all(c.isalnum() or c in " -_äöüßÄÖÜ" for c in nickname):
        return False, "Ungültige Zeichen im Nickname"
    return True, None


def validate_selections(selections):
    """Validate selections data based on current phase"""
    phase = get_phase()

    # RUNDE_1: 12 groups - expect dict
    if "RUNDE_1" in phase:
        if not isinstance(selections, dict):
            return False, "Selections müssen ein Objekt sein"
        if json.dumps(selections).__sizeof__() > MAX_SELECTIONS_SIZE:
            return False, "Selections zu groß"

        # Check that exactly 12 groups are present
        if len(selections) != 12:
            return False, "Es müssen exakt 12 Gruppen-Tipps eingereicht werden"

    # RUNDE_2: 4 teams from semi-finalists - expect list
    elif "RUNDE_2" in phase:
        if not isinstance(selections, list):
            return False, "Selections müssen ein Array sein"

        if len(selections) != 4:
            return False, "Es müssen exakt 4 Teams ausgewählt werden"

        for team in selections:
            if not isinstance(team, str) or len(team.strip()) == 0:
                return False, "Ungültige Team-Auswahl"

    # FINALE: 1 team - expect string
    elif "FINALE" in phase:
        if not isinstance(selections, str):
            return False, "Selection muss ein Team-Name sein"

        if len(selections.strip()) == 0:
            return False, "Bitte wähle einen Champion aus"

    return True, None


# Scoring-Logik für verschiedene Phasen
def extract_teams(data):
    """Convert any data structure to a unified set of teams"""
    if isinstance(data, dict):
        return set(data.values())
    elif isinstance(data, list):
        return set(data)
    elif isinstance(data, str):
        return {data}
    return set()


def calculate_score(user_selections, actual_winners, phase):
    """
    Calculate score for user selections based on actual results and phase.
    Uses set intersection to handle dict/list/string formats uniformly.

    Args:
        user_selections: Data structure depends on phase (dict/list/string)
        actual_winners: Expected structure depends on phase
        phase: Current phase (e.g., "RUNDE_1_GRUPPEN_TIPP")

    Returns:
        Integer score
    """
    # Convert both inputs to sets
    user_teams = extract_teams(user_selections)
    actual_teams = extract_teams(actual_winners)

    # Find intersection (correct picks)
    correct_picks = len(user_teams & actual_teams)

    # Apply phase-specific point values
    if "GRUPPEN_TIPP" in phase:
        return correct_picks * 1
    elif "RUNDE_2_TIPP" in phase:
        return correct_picks * 3
    elif "FINALE_TIPP" in phase:
        return correct_picks * 12

    return 0


# --- DATENBANK ---
def get_db_connection():
    return psycopg.connect(os.getenv("DATABASE_URL"), row_factory=dict_row)


def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Tabelle für Teilnehmer (live Übersicht während Nickname-Phase)
            cur.execute(
                """CREATE TABLE IF NOT EXISTS participants (
                id SERIAL PRIMARY KEY, nickname VARCHAR(50) NOT NULL UNIQUE,
                score INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
            )

            # Tabelle für Tipps und Ergebnisse
            cur.execute(
                """CREATE TABLE IF NOT EXISTS predictions (
                id SERIAL PRIMARY KEY, nickname VARCHAR(50) NOT NULL,
                phase VARCHAR(50) NOT NULL,
                selections JSONB NOT NULL, score INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(nickname, phase))"""
            )

            cur.execute(
                """CREATE TABLE IF NOT EXISTS tournament_results (
                id SERIAL PRIMARY KEY, phase VARCHAR(50) NOT NULL,
                results JSONB NOT NULL,
                is_final BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
            )

            # Tabelle für den Event-Status (nur 1 Zeile)
            cur.execute(
                """CREATE TABLE IF NOT EXISTS system_state (
                id INTEGER PRIMARY KEY, current_phase VARCHAR(50) NOT NULL)"""
            )

            # Startwert setzen, falls leer
            cur.execute(
                "INSERT INTO system_state (id, current_phase) VALUES (1, %s) ON CONFLICT DO NOTHING",
                (PHASES[0],),
            )
        conn.commit()


# Hilfsfunktionen für den Status
def get_phase():
    # Cache verwenden, um DB-Zugriffe zu minimieren (wird bei Phase-Änderung zurückgesetzt)
    if app.config["PHASE_CACHE"] is not None:
        return app.config["PHASE_CACHE"]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_phase FROM system_state WHERE id = 1")
            return cur.fetchone()["current_phase"]


def set_phase(new_phase):

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE system_state SET current_phase = %s WHERE id = 1", (new_phase,)
            )
        conn.commit()

    # Cache nicht vergessen
    app.config["PHASE_CACHE"] = new_phase


# Initialize database on module import (works with Gunicorn and local development)
init_db()

# --- HTML ROUTES (Die Seiten) ---


@app.route("/")
def index():
    access_code = request.args.get("access")
    if access_code != EVENT_ACCESS_CODE:
        return "<h1>Zugriff verweigert</h1><p>Bitte QR-Code scannen.</p>", 403
    # Set session to track authenticated users
    session["authenticated"] = True
    session.permanent = True
    # Flask lädt jetzt automatisch die Datei aus dem /templates Ordner!
    return render_template("index.html")


@app.route("/admin")
def admin_page():
    return render_template("admin.html")


@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")


# --- API ROUTES (Daten & Logik) ---


@app.route("/api/state", methods=["GET"])
def current_state():
    return jsonify({"phase": get_phase()})


@app.route("/api/participants", methods=["GET"])
def get_participants():
    """Get list of all participants (nicknames) who have joined"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nickname, created_at FROM participants ORDER BY created_at ASC"
                )
                participants = cur.fetchall()
        return jsonify({"count": len(participants), "participants": participants})
    except Exception as e:
        return jsonify({"error": f"Fehler beim Abrufen der Teilnehmer: {str(e)}"}), 500


@app.route("/api/latest-results", methods=["GET"])
def latest_results():
    """Holt die Turnier-Daten aus dem Master-Drehbuch für die Tipp-Runden"""
    try:
        current_phase = get_phase()

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT results FROM tournament_results WHERE phase = %s",
                    ("MASTER_SIMULATION",),
                )
                master_row = cur.fetchone()

        if not master_row:
            return jsonify({"error": "Keine Simulation in der Datenbank gefunden"}), 404

        master_data = master_row["results"]

        if current_phase == "RUNDE_2_TIPP":
            # Wir liefern die Paarungen für das Viertelfinale ans Handy!
            return jsonify({"pairings": master_data.get("qf_pairings", [])})
        elif current_phase == "FINALE_TIPP":
            # Wir liefern die 4 Halbfinalisten für den Weltmeister-Tipp
            return jsonify({"teams": master_data.get("semi_finalists", [])})
        else:
            return jsonify({"error": "Falsche Phase für diese Abfrage"}), 400

    except Exception as e:
        return jsonify({"error": f"Fehler: {str(e)}"}), 500


@app.route("/api/user-summary", methods=["GET"])
def user_summary():
    """Get user's final summary with total score and round-by-round results"""
    nickname = request.args.get("nickname")

    if not nickname:
        return jsonify({"error": "Nickname erforderlich"}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get total score from participants
                cur.execute(
                    "SELECT score FROM participants WHERE nickname = %s", (nickname,)
                )
                participant = cur.fetchone()

                if not participant:
                    return jsonify({"error": "Benutzer nicht gefunden"}), 404

                total_score = participant["score"] or 0

                # Get all predictions for this user
                cur.execute(
                    "SELECT phase, selections, score FROM predictions WHERE nickname = %s ORDER BY phase",
                    (nickname,),
                )
                predictions = cur.fetchall()

                # Get all tournament results
                cur.execute(
                    "SELECT phase, results FROM tournament_results ORDER BY phase"
                )
                results = cur.fetchall()
                # Extract winners from standardized structure: {"winners": data}
                results_by_phase = {
                    r["phase"]: r["results"].get("winners") for r in results
                }

                # Build round-by-round comparisons
                rounds = []

                for pred in predictions:
                    phase = pred["phase"]
                    # JSONB columns are already parsed by psycopg - no json.loads needed
                    user_selections = pred["selections"]
                    user_score = pred["score"] or 0
                    actual_results = results_by_phase.get(phase)

                    round_data = {
                        "phase": phase,
                        "user_score": user_score,
                        "comparisons": [],
                    }

                    # Round 1: Compare dict of group picks
                    if phase == "RUNDE_1_GRUPPEN_TIPP":
                        if isinstance(actual_results, dict) and isinstance(
                            user_selections, dict
                        ):
                            for group, user_team in user_selections.items():
                                actual_team = actual_results.get(group, "N/A")
                                round_data["comparisons"].append(
                                    {
                                        "category": group,
                                        "user_pick": user_team,
                                        "actual": actual_team,
                                        "correct": user_team == actual_team,
                                    }
                                )

                    # Round 2: Compare list of semi-finalist picks
                    elif phase == "RUNDE_2_TIPP":
                        if isinstance(actual_results, list) and isinstance(
                            user_selections, list
                        ):
                            round_data["comparisons"] = {
                                "user_picks": user_selections,
                                "actual_semis": actual_results,
                                "correct_count": sum(
                                    1 for t in user_selections if t in actual_results
                                ),
                            }

                    # Finals: Compare champion pick
                    elif phase == "FINALE_TIPP":
                        # In Runde 3 ist user_selections nur ein String (z.B. "Deutschland")
                        round_data["comparisons"] = {
                            "user_pick": user_selections,
                            "actual_champion": actual_results,
                            "correct": user_selections == actual_results,
                        }

                    rounds.append(round_data)

                return jsonify(
                    {"nickname": nickname, "total_score": total_score, "rounds": rounds}
                )

    except Exception as e:
        return jsonify({"error": f"Fehler: {str(e)}"}), 500


@app.route("/api/admin/set-phase", methods=["POST"])
@limiter.limit("5 per minute")  # Prevent brute force attempts
@csrf.exempt  # Exempt CSRF for API but enforce other validations
def update_state():
    data = request.json
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "Falsches Passwort"}), 403

    new_phase = data.get("phase")
    if new_phase in PHASES:
        set_phase(new_phase)
        return jsonify({"success": True, "phase": new_phase})
    return jsonify({"error": "Ungültige Phase"}), 400


@app.route("/api/submit-nickname", methods=["POST"])
@limiter.limit("10 per minute")  # Prevent spam
@csrf.exempt  # Exempt CSRF for API but enforce other validations
def submit_nickname():
    data = request.json
    if data.get("email_hp"):
        return jsonify({"error": "Bot-Aktivität erkannt!"}), 418

    # Check session authentication
    if not session.get("authenticated"):
        if data.get("access_token") != EVENT_ACCESS_CODE:
            return jsonify({"error": "Nicht autorisiert."}), 403

    # aktuelle Phase prüfen
    current_phase = get_phase()

    # Prüfen, ob wir in der Nickname-Phase sind
    if current_phase != "RUNDE_1_NICKNAME":
        return jsonify({"error": "Nickname-Phase ist nicht aktiv!"}), 403

    nickname = data.get("nickname")

    # Input validation
    valid, error = validate_nickname(nickname)
    if not valid:
        return jsonify({"error": error}), 400

    # Speichere Nickname in der Participants-Tabelle (für Live-Übersicht)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO participants (nickname) VALUES (%s)", (nickname,)
                )
            conn.commit()
    except psycopg.IntegrityError:
        return (
            jsonify(
                {
                    "error": "Dieser Nickname ist bereits vergeben! Bitte wähle einen anderen."
                }
            ),
            409,
        )
    except Exception as e:
        print(f"Error saving participant: {e}")
        return jsonify({"error": f"Fehler beim Speichern des Nicknames: {str(e)}"}), 500

    return jsonify({"success": True, "message": "Nickname gespeichert!"})


@app.route("/api/submit-selections", methods=["POST"])
@limiter.limit("10 per minute")  # Prevent spam
@csrf.exempt  # Exempt CSRF for API but enforce other validations
def submit_selections():
    data = request.json
    if data.get("email_hp"):
        return jsonify({"error": "Bot-Aktivität erkannt!"}), 418

    # Check session authentication
    if not session.get("authenticated"):
        if data.get("access_token") != EVENT_ACCESS_CODE:
            return jsonify({"error": "Nicht autorisiert."}), 403

    current_phase = get_phase()

    # Prüfen, ob wir in einer Tipp-Phase sind (RUNDE_1_GRUPPEN_TIPP, RUNDE_2_TIPP, FINALE_TIPP)
    if not current_phase.endswith("_TIPP"):
        return jsonify({"error": "Tipps sind aktuell nicht möglich!"}), 403

    # Nickname aus Request-Body auslesen (nicht aus Session)
    nickname = data.get("nickname")
    if not nickname:
        return (
            jsonify(
                {"error": "Kein Nickname angegeben. Bitte zuerst Nickname wählen!"}
            ),
            400,
        )

    selections = data.get("selections")

    # Input validation
    valid, error = validate_selections(selections)
    if not valid:
        return jsonify({"error": error}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Ensure late joiners are registered in participants table
                cur.execute(
                    "INSERT INTO participants (nickname) VALUES (%s) ON CONFLICT DO NOTHING",
                    (nickname,),
                )
                cur.execute(
                    "INSERT INTO predictions (nickname, phase, selections) VALUES (%s, %s, %s)",
                    (nickname, current_phase, json.dumps(selections)),
                )
            conn.commit()
        return jsonify({"success": True, "message": "Tipps gespeichert!"})
    except psycopg.IntegrityError:
        return jsonify({"error": "Nickname bereits für diese Runde abgegeben!"}), 409
    except Exception as e:
        return jsonify({"error": f"Fehler beim Speichern: {str(e)}"}), 500


@app.route("/api/admin/reset-db", methods=["POST"])
@csrf.exempt  # WICHTIG wegen deiner Security-Einstellungen
def reset_db():
    data = request.json
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "Nicht autorisiert"}), 403

    # Neue Simulation ausführen
    sim = WorldCupSimulation()
    simulation_results = sim.run_complete_tournament()

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM predictions")
                cur.execute("DELETE FROM participants")
                cur.execute("DELETE FROM tournament_results")
                # Zurück auf Anfang setzen
                cur.execute(
                    "UPDATE system_state SET current_phase = %s WHERE id = 1",
                    (PHASES[0],),
                )
                # Simulationsergebnisse speichern
                cur.execute(
                    "INSERT INTO tournament_results (phase, results, is_final) VALUES (%s, %s, %s)",
                    ("MASTER_SIMULATION", json.dumps(simulation_results), True),
                )
            conn.commit()

        return jsonify({"success": True, "message": "Datenbank komplett geleert!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/run-simulation", methods=["POST"])
@csrf.exempt
def run_simulation():
    """Run phase-specific simulation: get pre-calculated results, calculate scores, update phase"""
    data = request.json
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "Nicht autorisiert"}), 403

    phase = get_phase()

    # Konfiguration: Wie verhalten sich die einzelnen Phasen?
    # Format: { "aktuelle_phase": ("key_in_master_sim", "nächste_phase", "Lokalisiertes Wording") }
    phase_config: dict[str, tuple[str, str, str]] = {
        "RUNDE_1_GRUPPEN_TIPP": ("group_winners", "RUNDE_1_SIM", "Runde 1"),
        "RUNDE_2_TIPP": ("semi_finalists", "RUNDE_2_SIM", "Runde 2"),
        "FINALE_TIPP": ("champion", "FINALE_SIM", "Finale"),
    }

    if phase not in phase_config:
        return (
            jsonify({"error": f"Simulation für Phase '{phase}' nicht verfügbar"}),
            400,
        )

    master_key, next_phase, round_name = phase_config[phase]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. Geheimes Drehbuch (Master Simulation) laden
                cur.execute(
                    "SELECT results FROM tournament_results WHERE phase = %s",
                    ("MASTER_SIMULATION",),
                )
                master_row = cur.fetchone()

                if not master_row:
                    return (
                        jsonify(
                            {
                                "error": "Fehler: Keine MASTER_SIMULATION in der Datenbank gefunden! Bitte Turnier resetten."
                            }
                        ),
                        500,
                    )

                master_data = master_row["results"]

                # 2. Die relevanten Ergebnisse für DIESE Runde extrahieren
                round_winners = master_data.get(master_key)

                if not round_winners:
                    return (
                        jsonify(
                            {
                                "error": f"Fehler: '{master_key}' fehlt in der Master Simulation!"
                            }
                        ),
                        500,
                    )

                # 3. Das Ergebnis "offiziell" für das Frontend/Dashboard abspeichern
                cur.execute(
                    "INSERT INTO tournament_results (phase, results, is_final) VALUES (%s, %s, %s)",
                    (phase, json.dumps({"winners": round_winners}), True),
                )

                # 4. Alle Tipps für diese Runde holen
                cur.execute(
                    "SELECT id, nickname, selections FROM predictions WHERE phase = %s",
                    (phase,),
                )
                predictions = cur.fetchall()

                # 5. Universelle Scoring-Schleife (für alle Phasen gleich!)
                for pred in predictions:
                    user_selections = pred["selections"]
                    score = calculate_score(user_selections, round_winners, phase)

                    # Punkte in die Tipps-Tabelle und ins Leaderboard schreiben
                    cur.execute(
                        "UPDATE predictions SET score = %s WHERE id = %s",
                        (score, pred["id"]),
                    )
                    cur.execute(
                        "UPDATE participants SET score = COALESCE(score, 0) + %s WHERE nickname = %s",
                        (score, pred["nickname"]),
                    )

                # 6. Event in die nächste Phase (Simulations-Ansicht) schalten
                cur.execute(
                    "UPDATE system_state SET current_phase = %s WHERE id = 1",
                    (next_phase,),
                )
                conn.commit()

                return jsonify(
                    {
                        "success": True,
                        "message": f"{round_name} Simulation komplett! {len(predictions)} User bewertet.",
                    }
                )

    except Exception as e:
        return jsonify({"error": f"Simulationsfehler: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
