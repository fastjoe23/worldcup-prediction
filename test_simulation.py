import unittest
from simulation import WorldCupSimulation, GROUPS

class TestWorldCupSimulation(unittest.TestCase):

    def setUp(self):
        """Wird vor jedem Test ausgeführt, stellt eine frische Instanz bereit."""
        self.sim = WorldCupSimulation()

    def test_initialization(self):
        """Testet, ob die Basis-Daten korrekt geladen werden."""
        self.assertEqual(len(self.sim.groups), 12, "Es müssen exakt 12 Gruppen sein.")
        self.assertTrue(len(self.sim.ratings) > 0, "Ratings dürfen nicht leer sein.")

    def test_known_results_logic(self):
        """Testet das 'Gedächtnis' für reale Ergebnisse inkl. Seitenwechsel."""
        self.sim.known_results = {("Deutschland", "Curaçao"): (5, 0)}

        self.assertEqual(self.sim.get_known_score("Deutschland", "Curaçao"), (5, 0))
        self.assertEqual(self.sim.get_known_score("Curaçao", "Deutschland"), (0, 5))
        self.assertIsNone(self.sim.get_known_score("Argentinien", "Brasilien"))

    def test_simulate_match_score(self):
        """Testet die Tor-Generierung und K.O.-Bedingungen."""
        score_a, score_b = self.sim.simulate_match_score("Argentinien", "Brasilien", is_knockout=False)
        self.assertIsInstance(score_a, int)
        self.assertIsInstance(score_b, int)

        for _ in range(100):
            s_a, s_b = self.sim.simulate_match_score("Spanien", "Italien", is_knockout=True)
            self.assertNotEqual(s_a, s_b, "K.O.-Spiel darf nicht unentschieden enden!")

    def test_missing_rating_fallback(self):
        """Testet, ob die Simulation abstürzt, wenn ein Team kein Rating hat."""
        score_a, score_b = self.sim.simulate_match_score("Deutschland", "Phantasien")
        self.assertIsInstance(score_a, int)
        self.assertIsInstance(score_b, int)

    def test_third_place_selection(self):
        result = self.sim.run_complete_tournament()
        r32 = result["full_details"]["r32"]

        all_teams = [m["team1"] for m in r32] + [m["team2"] for m in r32]

        self.assertEqual(len(all_teams), 32)
        self.assertEqual(len(set(all_teams)), 32, "Keine doppelten Teams erlaubt!")

    def test_knockout_progression(self):
        result = self.sim.run_complete_tournament()
        details = result["full_details"]

        r32_winners = [m["winner"] for m in details["r32"]]
        r16_teams = [m["team1"] for m in details["r16"]] + [m["team2"] for m in details["r16"]]

        self.assertEqual(set(r32_winners), set(r16_teams))

    def test_group_structure(self):
        for _, teams in GROUPS.items():
            self.assertEqual(len(teams), 4)

    def test_full_tournament_structure(self):
        """Führt ein komplettes Turnier durch und prüft die Struktur des Outputs."""
        result = self.sim.run_complete_tournament()

        # 1. Gruppen-Basisdaten
        self.assertEqual(len(result["group_winners"]), 12)
        self.assertEqual(len(result["group_standings"]), 12)

        # 2. Prüfe die neuen Dashboard-Ticker-Spiele (12 Gruppen * 6 Spiele = 72 Spiele)
        details = result["full_details"]
        self.assertIn("group_matches", details)
        self.assertEqual(len(details["group_matches"]), 72, "Es müssen exakt 72 Gruppenspiele simuliert werden.")
        self.assertIn("score", details["group_matches"][0])

        # 3. K.O. Runden Checks
        self.assertEqual(len(result["qf_pairings"]), 4)
        self.assertEqual(len(result["semi_finalists"]), 4)
        self.assertIsInstance(result["champion"], str)
        self.assertIn(result["champion"], result["semi_finalists"])

        # 4. K.O. Details Checks
        self.assertEqual(len(details["r32"]), 16)
        self.assertEqual(len(details["r16"]), 8)
        self.assertEqual(len(details["qf"]), 4)
        self.assertEqual(len(details["sf"]), 2)
        self.assertEqual(len(details["f"]), 1)

    def test_z_print_tournament_tree(self):
        """Simuliert ein Turnier und gibt den kompletten Baum inkl. Tabellen aus."""
        result = self.sim.run_complete_tournament()
        details = result["full_details"]
        standings = result["group_standings"]

        print("\n" + "="*70)
        print(f"{'🏆 OFFIZIELLER WM 2026 TURNIERBAUM (SIMULATION) 🏆':^70}")
        print("="*70)

        # -- alle Spiele der Gruppenphase ausgeben ---
        print("\n" + "#"*70)
        print(f"{'GRUPPENSPIELE - ERGEBNISSE':^70}")
        print("#"*70)
        for match in details["group_matches"]:
            match_str = f"{match['home']:>20}  {match['score']:^7}  {match['away']:<20}"
            print(f"Gruppe {match['group']}: {match_str}")

        # --- Komplette Gruppentabellen ausgeben ---
        print("\n" + "#"*70)
        print(f"{'GRUPPENPHASE - ABSCHLUSSTABELLEN':^70}")
        print("#"*70)

        for group_id in sorted(standings.keys()):
            print(f"\n--- GRUPPE {group_id} ---")
            print(f"{'Pl.':<4} {'Team':<22} {'Pkt':<4} {'Diff':<5} {'Tore':<4}")
            print("-" * 45)
            for idx, stats in enumerate(standings[group_id]):
                # Ein Pokal für Platz 1 und 2 (direkt qualifiziert)
                icon = "🏆" if idx < 2 else "  "
                print(f"{idx+1:<3}{icon} {stats['team']:<22} {stats['p']:<4} {stats['diff']:>3}    {stats['goals']:<4}")

        print("\n" + "="*70)

        # --- K.O. Phase ausgeben ---
        phases = [
            ("Runde der 32 (Sechzehntelfinale)", details["r32"]),
            ("Achtelfinale", details["r16"]),
            ("Viertelfinale", details["qf"]),
            ("Halbfinale", details["sf"]),
            ("Finale", details["f"])
        ]

        for phase_name, matches in phases:
            print(f"\n--- {phase_name.upper()} ---")
            for m in matches:
                match_str = f"{m['team1']:>20}  {m['score']:^7}  {m['team2']:<20}"
                print(f"{match_str} -> Sieger: {m['winner']}")

        print("\n" + "="*70)
        print(f"🌟 WELTMEISTER 2026: {result['champion'].upper()} 🌟".center(70))
        print("="*70 + "\n")

if __name__ == '__main__':
    unittest.main(verbosity=2)
