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
    "Gruppe L": ["England", "Kroatien", "Ghana", "Panama"]
}

# am Spieltag ggf. nochmal aktualisieren, damit die Simulation bekannte Ergebnisse berücksichtigt
TEAM_RATINGS = {
    "Spanien": 2165, "Argentinien": 2113, "Frankreich": 2082, "England": 2020,
    "Kolumbien": 1975, "Portugal": 1984, "Brasilien": 1984, "Niederlande": 1961,
    "Ecuador": 1933, "Kroatien": 1930, "Deutschland": 1923, "Norwegen": 1912,
    "Türkei": 1902, "Schweiz": 1889, "Belgien": 1866, "Japan": 1904, "Österreich": 1827,
    "Uruguay": 1892, "USA": 1712, "Mexiko": 1858, "Marokko": 1821, "Paraguay": 1833,
    "Schottland": 1767,  "Südkorea": 1752, "Tschechien": 1726, "Australien": 1783,
    "Schweden": 1719, "Algerien": 1743, "Südafrika": 1524, "Kanada": 1784,
    "Ägypten": 1689, "Panama": 1737, "Ghana": 1505, "Katar": 1425, 
    "Irak": 1607, "Saudi-Arabien": 1568, "Jordanien": 1690, "Iran": 1760,
    "Curaçao": 1436, "Haiti": 1532, "Neuseeland": 1585, "DR Kongo": 1655,
    "Bosnien & Herzegowina": 1594, "Kap Verde": 1549, "Usbekistan": 1727, 
    "Senegal": 1879, "Elfenbeinküste": 1676, "Tunesien": 1636
}


KNOWN_RESULTS = {
    #("Mexiko", "Südafrika"): (20, 11)
    }

# ==========================================
# 2. SIMULATIONS-LOGIK
# ==========================================

class WorldCupSimulation:
    def __init__(self):
        self.groups = GROUPS
        self.ratings = TEAM_RATINGS
        self.known_results = KNOWN_RESULTS

    def get_known_score(self, team_a, team_b):
        if (team_a, team_b) in self.known_results:
            return self.known_results[(team_a, team_b)]
        elif (team_b, team_a) in self.known_results:
            score_b, score_a = self.known_results[(team_b, team_a)]
            return score_a, score_b
        return None

    def simulate_match_score(self, team_a, team_b, is_knockout=False):
        rating_a = self.ratings.get(team_a, 1500)
        rating_b = self.ratings.get(team_b, 1500)

        # --- Elo → expected goals (Poisson intensities) ---
        avg_goals = 1.35
        elo_scale = 400

        strength_diff = (rating_a - rating_b) / elo_scale

        lambda_a = avg_goals * math.exp(strength_diff)
        lambda_b = avg_goals * math.exp(-strength_diff)

        # --- Pure Python Poisson sampling (Knuth's Algorithm) ---
        def poisson(lam):
            big_l = math.exp(-lam)
            k = 0
            p = 1.0
            while p > big_l:
                k += 1
                p *= random.random()
            return k - 1

        # 90 Minuten simulieren
        score_a = poisson(lambda_a)
        score_b = poisson(lambda_b)

        # --- small match randomness (injury, red card, luck) ---
        if random.random() < 0.04:
            score_a += 1
        if random.random() < 0.04:
            score_b += 1

        # --- knockout resolution ---
        if is_knockout and score_a == score_b:
            # Verlängerung: 30 Minuten sind 1/3 der Spielzeit
            score_a += poisson(lambda_a / 3)
            score_b += poisson(lambda_b / 3)

            if score_a == score_b:
                # Elfmeterschießen!
                # Leicht Elo-basiert, aber mit SEHR hohem Zufallsfaktor (Nervensache)
                prob_a_wins_penalties = lambda_a / (lambda_a + lambda_b)
                # Wir zwingen ein klares Ergebnis für das Elfmeterschießen
                if random.random() < prob_a_wins_penalties:
                    score_a += 1
                else:
                    score_b += 1

        return score_a, score_b

    def run_complete_tournament(self):
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
                    s1, s2 = self.simulate_match_score(t1, t2)

                # Ergebnisse speichern für API-Ausgabe
                group_matches.append({
                    "group": group_id,
                    "home": t1,
                    "away": t2,
                    "score": f"{s1}:{s2}"
                })

                if s1 > s2:
                    stats[t1]["p"] += 3
                elif s2 > s1:
                    stats[t2]["p"] += 3
                else:
                    stats[t1]["p"] += 1
                    stats[t2]["p"] += 1

                stats[t1]["diff"] += (s1 - s2)
                stats[t2]["diff"] += (s2 - s1)
                stats[t1]["goals"] += s1
                stats[t2]["goals"] += s2

            sorted_group = sorted(
                teams,
                key=lambda t, s=stats: (s[t]["p"], s[t]["diff"], s[t]["goals"]),
                reverse=True
            )


            standings[group_id] = sorted_group
            group_stats[group_id] = stats

            group_winners_for_api[name] = sorted_group[0]

        # --- BESTE DRITTPLATZIERTE ---
        thirds = []
        for g_id, sorted_teams in standings.items():
            thirds.append({
                "team": sorted_teams[2],
                "stats": group_stats[g_id][sorted_teams[2]]  
            })

        sorted_thirds = sorted(
            thirds,
            key=lambda x: (x["stats"]["p"], x["stats"]["diff"], x["stats"]["goals"]),
            reverse=True
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
            (standings["D"][1], standings["G"][1])
        ]

        def play_ko_bracket(matchups):
            winners = []
            details = []
            for t1, t2 in matchups:
                s1, s2 = self.simulate_match_score(t1, t2, is_knockout=True)
                winner = t1 if s1 > s2 else t2
                winners.append(winner)
                details.append({
                    "team1": t1,
                    "team2": t2,
                    "score": f"{s1}:{s2}",
                    "winner": winner
                })
            return winners, details

        round_of_16_teams, r32_results = play_ko_bracket(r32_matchups)

        r16_matchups = [(round_of_16_teams[i], round_of_16_teams[i+1]) for i in range(0, 16, 2)]
        quarter_finalists, r16_results = play_ko_bracket(r16_matchups)

        qf_matchups = [(quarter_finalists[i], quarter_finalists[i+1]) for i in range(0, 8, 2)]
        qf_pairings = [{"team1": t1, "team2": t2} for t1, t2 in qf_matchups]

        semi_finalists, qf_results = play_ko_bracket(qf_matchups)

        sf_matchups = [(semi_finalists[i], semi_finalists[i+1]) for i in range(0, 4, 2)]
        finalists, sf_results = play_ko_bracket(sf_matchups)

        f_matchups = [(finalists[0], finalists[1])]
        champion_list, f_results = play_ko_bracket(f_matchups)

        return {
            "group_winners": group_winners_for_api,
            "qf_pairings": qf_pairings,
            "semi_finalists": semi_finalists,
            "champion": champion_list[0],
            "group_standings": {g_id: [{"team": t, **group_stats[g_id][t]} for t in teams] 
                               for g_id, teams in standings.items()},
            "full_details": {
                "group_matches": group_matches,
                "r32": r32_results,
                "r16": r16_results,
                "qf": qf_results,
                "sf": sf_results,
                "f": f_results
            }
        }
