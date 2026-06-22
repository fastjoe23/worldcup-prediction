from itertools import combinations
import random
import math

# ==========================================
# 1. TURNIER-KONFIGURATION
# ==========================================

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
    "Gruppe L": ["England", "Kroatien", "Ghana", "Panama"],
}

# am Spieltag ggf. nochmal aktualisieren, damit die Simulation bekannte Ergebnisse berücksichtigt
TEAM_RATINGS = {
    "Spanien": 21345,
    "Argentinien": 2128,
    "Frankreich": 2084,
    "England": 2055,
    "Kolumbien": 1998,
    "Portugal": 1967,
    "Brasilien": 1986,
    "Niederlande": 1972,
    "Ecuador": 1864,
    "Kroatien": 1881,
    "Deutschland": 1954,
    "Norwegen": 1929,
    "Türkei": 1813,
    "Schweiz": 1885,
    "Belgien": 1869,
    "Japan": 1925,
    "Österreich": 1857,
    "Uruguay": 1851,
    "USA": 1820,
    "Mexiko": 1896,
    "Marokko": 1866,
    "Paraguay": 1816,
    "Schottland": 1768,
    "Südkorea": 1771,
    "Tschechien": 1696,
    "Australien": 1799,
    "Schweden": 1727,
    "Algerien": 1743,
    "Südafrika": 1527,
    "Kanada": 1777,
    "Ägypten": 1711,
    "Panama": 1683,
    "Ghana": 1557,
    "Katar": 1437,
    "Irak": 1592,
    "Saudi-Arabien": 1593,
    "Jordanien": 1653,
    "Iran": 1760,
    "Curaçao": 1453,
    "Haiti": 1528,
    "Neuseeland": 1578,
    "DR Kongo": 1674,
    "Bosnien & Herzegowina": 1596,
    "Kap Verde": 1625,
    "Usbekistan": 1698,
    "Senegal": 1839,
    "Elfenbeinküste": 1728,
    "Tunesien": 1570,
}

MARKET_VALUES = {
    "Frankreich": 1600.0,
    "Spanien": 1400.0,
    "England": 1400.0,
    "Deutschland": 1100.0,
    "Portugal": 1000.0,
    "Brasilien": 934.7,
    "Niederlande": 861.4,
    "Argentinien": 747.0,
    "Belgien": 698.3,
    "Norwegen": 618.4,
    "Marokko": 613.2,
    "Türkei": 583.7,
    "Schweden": 571.6,
    "USA": 546.8,
    "Elfenbeinküste": 518.6,
    "Kroatien": 466.2,
    "Senegal": 459.4,
    "Uruguay": 425.4,
    "Schweiz": 417.0,
    "Kolumbien": 363.0,
    "Österreich": 332.8,
    "Tschechien": 324.1,
    "Algerien": 318.1,
    "Ecuador": 304.2,
    "Japan": 258.6,
    "Ghana": 251.6,
    "Kanada": 227.5,
    "DR Kongo": 183.5,
    "Mexiko": 182.1,
    "Schottland": 164.0,
    "Ägypten": 161.1,
    "Bosnien & Herzegowina": 158.5,
    "Südkorea": 154.2,
    "Paraguay": 92.0,
    "Tunesien": 71.3,
    "Australien": 56.5,
    "Kap Verde": 50.7,
    "Haiti": 49.4,
    "Panama": 49.0,
    "Usbekistan": 40.3,
    "Curaçao": 39.9,
    "Neuseeland": 33.5,
    "Irak": 23.5,
    "Iran": 19.0,
    "Saudi-Arabien": 17.0,
    "Südafrika": 11.6,
    "Jordanien": 11.5,
    "Katar": 5.9,
}


KNOWN_RESULTS = {
    # --- 1. Spieltag ---
    ("Mexiko", "Südafrika"): (2, 0),
    ("Südkorea", "Tschechien"): (2, 1),
    ("Kanada", "Bosnien & Herzegowina"): (1, 1),
    ("USA", "Paraguay"): (4, 1),
    ("Katar", "Schweiz"): (1, 1),
    ("Schottland", "Haiti"): (1, 0),
    ("Brasilien", "Marokko"): (1, 1),
    ("Australien", "Türkei"): (2, 0),
    ("Deutschland", "Curaçao"): (7, 1),
    ("Elfenbeinküste", "Ecuador"): (1, 0),
    ("Schweden", "Tunesien"): (5, 1),
    ("Niederlande", "Japan"): (2, 2),
    ("Belgien", "Ägypten"): (1, 1),
    ("Iran", "Neuseeland"): (2, 2),
    ("Uruguay", "Saudi-Arabien"): (1, 1),
    ("Spanien", "Kap Verde"): (0, 0),
    ("Frankreich", "Senegal"): (3, 1),
    ("Irak", "Norwegen"): (1, 4),
    ("Argentinien", "Algerien"): (3, 0),
    ("Österreich", "Jordanien"): (3, 1),
    ("Portugal", "DR Kongo"): (1, 1),
    ("Usbekistan", "Kolumbien"): (1, 3),
    ("England", "Kroatien"): (4, 2),
    ("Ghana", "Panama"): (1, 0),
    

    # --- 2. Spieltag ---
    ("Schottland", "Marokko"): (0, 1),
    ("Brasilien", "Haiti"): (3, 0),
    ("Türkei", "Paraguay"): (0, 1),
    ("Niederlande", "Schweden"): (5, 1),
    ("Deutschland", "Elfenbeinküste"): (2, 1),
    ("Ecuador", "Curaçao"): (0, 0),
    ("Tunesien", "Japan"): (0, 4),
    ("Spanien", "Saudi-Arabien"): (4, 0),
    ("Belgien", "Iran"): (0, 0),
    ("Uruguay", "Kap Verde"): (2, 2),
    ("Neuseeland", "Ägypten"): (1, 3),
    ("Schweiz", "Bosnien & Herzegowina"): (4, 1),
    ("Tschechien", "Südafrika"): (1, 1),
    ("Mexiko", "Südkorea"): (1, 0),
    ("Kanada", "Katar"): (6, 0),
    ("USA", "Australien"): (2, 0),
}

# ==========================================
# 2. SIMULATIONS-LOGIK
# ==========================================


class WorldCupSimulation:
    def __init__(self):
        self.groups = GROUPS
        self.ratings = TEAM_RATINGS
        self.market_values = MARKET_VALUES
        self.known_results = KNOWN_RESULTS

    def get_known_score(self, team_a, team_b):
        if (team_a, team_b) in self.known_results:
            return self.known_results[(team_a, team_b)]
        elif (team_b, team_a) in self.known_results:
            score_b, score_a = self.known_results[(team_b, team_a)]
            return score_a, score_b
        return None

    def simulate_match_score(self, team_a, team_b, is_knockout=False, mode="combined"):
        rating_a = self.ratings.get(team_a, 1500)
        rating_b = self.ratings.get(team_b, 1500)

        mv_a = self.market_values.get(team_a, 50)
        mv_b = self.market_values.get(team_b, 50)

        # --- 1. Modus-Schalter (Gewichtung festlegen) ---
        if mode == "elo":
            weight_elo = 1.0
        elif mode == "mv":
            weight_elo = 0.0
        else:  # mode == 'combined'
            # 50/50 in der K.O.-Phase, 70/30 in der Gruppenphase
            weight_elo = 0.5 if is_knockout else 0.7

        weight_mv = 1.0 - weight_elo

        # --- 2. Wahrscheinlichkeiten berechnen ---
        prob_elo_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

        total_mv = mv_a + mv_b
        prob_mv_a = mv_a / total_mv if total_mv > 0 else 0.5

        p_comb_a = (prob_elo_a * weight_elo) + (prob_mv_a * weight_mv)

        # Extreme abfangen für den Logarithmus
        p_comb_a = max(0.01, min(0.99, p_comb_a))

        # --- 3. Rückrechnung in "effektive" Stärkedifferenz ---
        effective_strength_diff = math.log10(p_comb_a / (1 - p_comb_a))

        # --- 4. Expected Goals (Poisson Intensitäten) ---
        avg_goals = 1.35
        lambda_a = avg_goals * math.exp(effective_strength_diff)
        lambda_b = avg_goals * math.exp(-effective_strength_diff)

        # --- Pure Python Poisson sampling (Knuth's Algorithm) ---
        def poisson(lam):
            big_l = math.exp(-lam)
            k = 0
            p = 1.0
            while p > big_l:
                k += 1
                p *= random.random()
            return k - 1

        score_a = poisson(lambda_a)
        score_b = poisson(lambda_b)

        # --- small match randomness (injury, red card, luck) ---
        if random.random() < 0.04:
            score_a += 1
        if random.random() < 0.04:
            score_b += 1

        # --- knockout resolution ---
        if is_knockout and score_a == score_b:
            score_a += poisson(lambda_a / 3)
            score_b += poisson(lambda_b / 3)

            if score_a == score_b:
                prob_a_wins_penalties = lambda_a / (lambda_a + lambda_b)
                if random.random() < prob_a_wins_penalties:
                    score_a += 1
                else:
                    score_b += 1

        return score_a, score_b

    def run_complete_tournament(self, mode="combined"):
        group_winners_for_api = {}
        standings = {}
        group_stats = {}
        group_matches = []

        # --- GRUPPENPHASE ---
        for name, teams in self.groups.items():
            stats = {t: {"p": 0, "diff": 0, "goals": 0} for t in teams}
            group_id = name.split(" ")[1]

            for t1, t2 in combinations(teams, 2):
                known = self.get_known_score(t1, t2)
                if known:
                    s1, s2 = known
                else:
                    s1, s2 = self.simulate_match_score(
                        t1, t2, is_knockout=False, mode=mode
                    )

                # Ergebnisse speichern für API-Ausgabe
                group_matches.append(
                    {"group": group_id, "home": t1, "away": t2, "score": f"{s1}:{s2}"}
                )

                if s1 > s2:
                    stats[t1]["p"] += 3
                elif s2 > s1:
                    stats[t2]["p"] += 3
                else:
                    stats[t1]["p"] += 1
                    stats[t2]["p"] += 1

                stats[t1]["diff"] += s1 - s2
                stats[t2]["diff"] += s2 - s1
                stats[t1]["goals"] += s1
                stats[t2]["goals"] += s2

            sorted_group = sorted(
                teams,
                key=lambda t, s=stats: (s[t]["p"], s[t]["diff"], s[t]["goals"]),
                reverse=True,
            )

            standings[group_id] = sorted_group
            group_stats[group_id] = stats

            group_winners_for_api[name] = sorted_group[0]

        # --- BESTE DRITTPLATZIERTE ---
        thirds = []
        for g_id, sorted_teams in standings.items():
            thirds.append(
                {"team": sorted_teams[2], "stats": group_stats[g_id][sorted_teams[2]]}
            )

        sorted_thirds = sorted(
            thirds,
            key=lambda x: (x["stats"]["p"], x["stats"]["diff"], x["stats"]["goals"]),
            reverse=True,
        )

        # beste 8 Drittplatzierten qualifizieren sich für die K.O.-Phase
        best_8_thirds = [x["team"] for x in sorted_thirds[:8]]

        t = best_8_thirds

        r32_matchups = [
            (standings["A"][1], standings["B"][1]),
            (standings["E"][0], t[0]),
            (standings["F"][0], standings["C"][1]),
            (standings["C"][0], standings["F"][1]),
            (standings["I"][0], t[1]),
            (standings["E"][1], standings["I"][1]),
            (standings["A"][0], t[2]),
            (standings["L"][0], t[3]),
            (standings["D"][0], t[4]),
            (standings["G"][0], t[5]),
            (standings["K"][1], standings["L"][1]),
            (standings["H"][0], standings["J"][1]),
            (standings["B"][0], t[6]),
            (standings["J"][0], standings["H"][1]),
            (standings["K"][0], t[7]),
            (standings["D"][1], standings["G"][1]),
        ]

        def play_ko_bracket(matchups):
            winners = []
            details = []
            for t1, t2 in matchups:
                s1, s2 = self.simulate_match_score(t1, t2, is_knockout=True, mode=mode)
                winner = t1 if s1 > s2 else t2
                winners.append(winner)
                details.append(
                    {"team1": t1, "team2": t2, "score": f"{s1}:{s2}", "winner": winner}
                )
            return winners, details

        round_of_16_teams, r32_results = play_ko_bracket(r32_matchups)

        r16_matchups = [
            (round_of_16_teams[i], round_of_16_teams[i + 1]) for i in range(0, 16, 2)
        ]
        quarter_finalists, r16_results = play_ko_bracket(r16_matchups)

        qf_matchups = [
            (quarter_finalists[i], quarter_finalists[i + 1]) for i in range(0, 8, 2)
        ]
        qf_pairings = [{"team1": t1, "team2": t2} for t1, t2 in qf_matchups]

        semi_finalists, qf_results = play_ko_bracket(qf_matchups)

        sf_matchups = [
            (semi_finalists[i], semi_finalists[i + 1]) for i in range(0, 4, 2)
        ]
        finalists, sf_results = play_ko_bracket(sf_matchups)

        f_matchups = [(finalists[0], finalists[1])]
        champion_list, f_results = play_ko_bracket(f_matchups)

        return {
            "group_winners": group_winners_for_api,
            "qf_pairings": qf_pairings,
            "semi_finalists": semi_finalists,
            "champion": champion_list[0],
            "group_standings": {
                g_id: [{"team": t, **group_stats[g_id][t]} for t in teams]
                for g_id, teams in standings.items()
            },
            "full_details": {
                "group_matches": group_matches,
                "r32": r32_results,
                "r16": r16_results,
                "qf": qf_results,
                "sf": sf_results,
                "f": f_results,
            },
        }
