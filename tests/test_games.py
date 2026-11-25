import itertools
import random
import unittest

from caddy import fines as F
from caddy import formats as G
from caddy.models import Course, Player, Round
from caddy.settlement import _greedy, min_transfers, settle, summary_text


def make_round(names_hcps, games=None):
    return Round(Course(), [Player(n, h) for n, h in names_hcps], games=games or {})


def fill(r, name, scores):
    for h, s in enumerate(scores, start=1):
        r.set_score(name, h, s)


PARS = [4, 4, 3, 5, 4, 4, 3, 4, 5, 4, 3, 4, 5, 4, 4, 3, 4, 5]


class StablefordTests(unittest.TestCase):
    def test_points_pot_and_ties(self):
        r = make_round([("A", 0), ("B", 18)], {"stableford": {"stake": 5}})
        fill(r, "A", PARS)  # 36 pts
        fill(r, "B", [p + 1 for p in PARS])  # bogey golf off 18 = 36 pts
        res = G.stableford(r, r.games["stableford"])
        self.assertEqual([row["Points"] for row in res.standings], [36, 36])
        self.assertEqual(res.balances, {"A": 0, "B": 0})
        r.set_score("A", 1, 3)
        res = G.stableford(r, r.games["stableford"])
        self.assertEqual(res.standings[0]["Player"], "A")
        self.assertEqual(res.balances, {"A": 500, "B": -500})


class AmbroseTests(unittest.TestCase):
    def test_team_handicap_formula(self):
        self.assertEqual(G.ambrose_team_handicap([10, 20]), 7.5)  # /4
        self.assertEqual(G.ambrose_team_handicap([8, 12, 16, 24]), 7.5)  # /8
        self.assertEqual(G.ambrose_team_handicap([10, 20], divisor=5), 6.0)

    def test_net_winner_takes_pot(self):
        games = {"ambrose": {"stake": 10, "teams": [{"name": "Hackers", "players": ["A", "B"]}, {"name": "Duffers", "players": ["C", "D"]}]}}
        r = make_round([("A", 30), ("B", 30), ("C", 2), ("D", 2)], games)
        self.assertTrue(r.is_team_scoring)
        for h in range(1, 19):
            r.set_score("Hackers", h, PARS[h - 1], team=True)  # 72 - 15 = 57
            r.set_score("Duffers", h, PARS[h - 1] - (1 if h <= 3 else 0), team=True)  # 69 - 1 = 68
        res = G.ambrose(r, games["ambrose"])
        self.assertEqual(res.standings[0]["Team"], "Hackers")
        self.assertEqual(res.standings[0]["Net"], 57.0)
        self.assertEqual(res.balances, {"A": 1000, "B": 1000, "C": -1000, "D": -1000})
        self.assertTrue(r.is_complete())

    def test_ambrose_cannot_mix_with_individual_games(self):
        self.assertTrue(G.validate_games({"ambrose": {}, "skins": {}}))
        self.assertEqual(G.validate_games({"stableford": {}, "skins": {}}), [])


class SkinsTests(unittest.TestCase):
    def test_carryover_and_zero_sum(self):
        r = make_round([("A", 0), ("B", 0), ("C", 0)], {"skins": {"value": 1, "use_net": False}})
        fill(r, "A", [4, 4, 3])
        fill(r, "B", [4, 4, 4])
        fill(r, "C", [4, 5, 4])
        res = G.skins(r, r.games["skins"])
        a = next(row for row in res.standings if row["Player"] == "A")
        self.assertEqual(a["Skins"], 3)  # holes 1-2 tied (A,B), A wins hole 3 with 2 carried
        self.assertEqual(res.balances, {"A": 600, "B": -300, "C": -300})
        self.assertEqual(sum(res.balances.values()), 0)

    def test_pending_carry_note_and_pickups_never_win(self):
        r = make_round([("A", 0), ("B", 0)], {"skins": {"value": 1, "use_net": False}})
        r.set_score("A", 1, None)
        r.set_score("B", 1, 9)
        r.set_score("A", 2, 4)
        r.set_score("B", 2, 4)
        res = G.skins(r, r.games["skins"])
        self.assertEqual(res.balances, {"A": -100, "B": 100})
        self.assertTrue(any("carrying over" in n for n in res.notes))

    def test_net_skins_use_stroke_index(self):
        r = make_round([("Low", 0), ("High", 18)], {"skins": {"value": 1}})
        r.set_score("Low", 1, 4)
        r.set_score("High", 1, 4)  # High gets a stroke on every hole -> net 3 wins
        res = G.skins(r, r.games["skins"])
        self.assertEqual(res.balances, {"Low": -100, "High": 100})


class BestBallTests(unittest.TestCase):
    def test_stableford_best_ball(self):
        games = {"best_ball": {"stake": 5, "allowance": 1.0, "teams": [{"name": "T1", "players": ["A", "B"]}, {"name": "T2", "players": ["C", "D"]}]}}
        r = make_round([("A", 0), ("B", 0), ("C", 0), ("D", 0)], games)
        for name, s in (("A", [3, 6]), ("B", [6, 4]), ("C", [4, 4]), ("D", [5, 5])):
            fill(r, name, s)
        res = G.best_ball(r, games["best_ball"])
        self.assertEqual(res.standings[0]["Team"], "T1")
        self.assertEqual(res.standings[0]["Score"], 5)  # 3 pts + 2 pts
        self.assertEqual(res.balances, {"A": 500, "B": 500, "C": -500, "D": -500})


class WolfTests(unittest.TestCase):
    def setUp(self):
        self.order = ["W", "X", "Y", "Z"]
        self.r = make_round([(n, 0) for n in self.order], {"wolf": {"order": self.order, "value": 1, "lone_multiplier": 2, "use_net": False}})

    def test_rotation(self):
        self.assertEqual([G.wolf_for_hole(self.order, h) for h in (1, 2, 5)], ["W", "X", "W"])

    def test_partner_win_and_lone_wolf_loss(self):
        r = self.r
        for n, s in zip(self.order, [3, 5, 5, 4]):
            r.set_score(n, 1, s)
        r.wolf_picks[1] = "X"  # W & X (best 3) beat Y & Z (best 4)
        for n, s in zip(self.order, [5, 4, 5, 5]):
            r.set_score(n, 2, s)
        r.wolf_picks[2] = ""  # X lone wolf, 4 vs best 5 -> wins x2
        res = G.wolf(r, r.games["wolf"])
        pts = {row["Player"]: row["Points"] for row in res.standings}
        self.assertEqual(pts, {"W": 1 - 2, "X": 1 + 6, "Y": -1 - 2, "Z": -1 - 2})
        self.assertEqual(sum(res.balances.values()), 0)

    def test_needs_four(self):
        r = make_round([("A", 0), ("B", 0)], {"wolf": {}})
        self.assertTrue(G.compute_all(r)[0].error)


class NassauTests(unittest.TestCase):
    def test_front_back_overall_and_auto_press(self):
        r = make_round([("A", 0), ("B", 0)], {"nassau": {"sides": [["A"], ["B"]], "stake": 5, "use_net": False}})
        # B wins holes 1-2 (A 2 down -> press from 3-9), A wins holes 3-9, halves back nine.
        a = [5, 5] + [3] * 7 + [4] * 9
        b = [4, 4] + [4] * 7 + [4] * 9
        fill(r, "A", a)
        fill(r, "B", b)
        res = G.nassau(r, r.games["nassau"])
        status = {row["Bet"]: row["Status"] for row in res.standings}
        self.assertEqual(status["Front 9"], "A 5 UP")
        self.assertEqual(status["Press (H3-9)"], "A 7 UP")  # A pressed at 2 down after hole 2
        # B then goes 2 down in each new press and auto-presses again: H5-9, H7-9, H9-9.
        self.assertEqual(status["Press (H5-9)"], "A 5 UP")
        self.assertEqual(status["Press (H7-9)"], "A 3 UP")
        self.assertEqual(status["Press (H9-9)"], "A 1 UP")
        self.assertEqual(status["Back 9"], "All square")
        self.assertEqual(status["Overall"], "A 5 UP")
        self.assertEqual(res.balances, {"A": 3000, "B": -3000})  # 6 winning bets x $5

    def test_no_presses_when_disabled(self):
        r = make_round([("A", 0), ("B", 0)], {"nassau": {"sides": [["A"], ["B"]], "stake": 5, "use_net": False, "auto_press": False}})
        fill(r, "A", [5, 5] + [3] * 7 + [4] * 9)
        fill(r, "B", [4] * 18)
        res = G.nassau(r, r.games["nassau"])
        self.assertEqual([row["Bet"] for row in res.standings], ["Front 9", "Back 9", "Overall"])
        self.assertEqual(res.balances, {"A": 1000, "B": -1000})

    def test_rejects_uneven_sides(self):
        r = make_round([("A", 0), ("B", 0), ("C", 0)], {"nassau": {"sides": [["A"], ["B", "C"]]}})
        self.assertIn("equal", G.compute_all(r)[0].error)


class FinesAndSettlementTests(unittest.TestCase):
    def test_default_catalog_matches_club_rules(self):
        by_key = {f["key"]: f for f in F.DEFAULT_FINES}
        self.assertTrue(by_key["tantrum"]["shout"])
        self.assertEqual(by_key["obscenity"]["amount"], 2.0)
        self.assertEqual(by_key["air_swing"]["amount"], 2.0)
        self.assertEqual(by_key["front_tees"]["amount"], 2.0)
        self.assertEqual(by_key["three_putt"]["amount"], 1.0)
        self.assertIn("Shout the round", F.describe(by_key["tantrum"]))

    def test_ledger_kitty_split_and_undo(self):
        r = make_round([("A", 0), ("B", 0), ("C", 0)])
        cat = {f["key"]: f for f in F.DEFAULT_FINES}
        F.add_fine(r, "A", cat["obscenity"], 3)
        F.add_fine(r, "A", cat["tantrum"], 4)
        e = F.add_fine(r, "B", cat["three_putt"], 5)
        self.assertEqual(F.fine_balances(r), {"A": -200, "B": -100, "C": 0, F.KITTY: 300})
        self.assertEqual(F.fine_balances(r, "split"), {"A": -150, "B": 0, "C": 150})
        self.assertEqual([s["player"] for s in F.shouts(r)], ["A"])
        self.assertTrue(F.undo_fine(r, e["id"]))
        self.assertEqual(F.fines_by_player(r)["B"]["count"], 0)
        with self.assertRaises(ValueError):
            F.add_fine(r, "Nobody", cat["obscenity"])

    def test_catalog_normalisation(self):
        cat = F.normalise_catalog([{"label": "Shank", "amount": "3"}, {"label": ""}, {"label": "Shank", "amount": -1}])
        self.assertEqual([c["key"] for c in cat], ["shank", "shank_2"])
        self.assertEqual(cat[1]["amount"], 0.0)
        self.assertEqual(len(F.normalise_catalog([])), len(F.DEFAULT_FINES))

    def test_min_transfers_beats_greedy(self):
        bal = {"A": 600, "B": 400, "C": -400, "D": -300, "E": -300}
        self.assertEqual(len(_greedy(list(bal.items()))), 4)
        tx = min_transfers(bal)
        self.assertEqual(len(tx), 3)
        self._assert_settles(bal, tx)

    def test_min_transfers_is_optimal_on_random_cases(self):
        rng = random.Random(7)
        for _ in range(60):
            n = rng.randint(2, 7)
            vals = [rng.choice([-3, -2, -1, 1, 2, 3]) * 100 for _ in range(n - 1)]
            vals.append(-sum(vals))
            bal = {f"P{i}": v for i, v in enumerate(vals)}
            tx = min_transfers(bal)
            self._assert_settles(bal, tx)
            self.assertEqual(len(tx), self._brute_min(vals))

    def test_rejects_non_zero_sum(self):
        with self.assertRaises(ValueError):
            min_transfers({"A": 100, "B": -50})

    def test_full_19th_hole_summary(self):
        r = make_round([("Rusty", 18), ("Dave", 18), ("Mick", 18)], {"stableford": {"stake": 5}, "skins": {"value": 1, "use_net": False}})
        fill(r, "Rusty", PARS)
        fill(r, "Dave", [p + 1 for p in PARS])
        fill(r, "Mick", [p + 2 for p in PARS])
        F.add_fine(r, "Mick", F.DEFAULT_FINES[0], 7)
        F.add_fine(r, "Dave", F.DEFAULT_FINES[1], 9)
        s = settle(r)
        self.assertEqual(sum(s.net.values()), 0)
        self.assertEqual(s.net["Rusty"], 1000 + 3600)  # stableford pot + 18 skins x $1 x 2 opponents
        self._assert_settles(s.net, s.transfers)
        text = summary_text(r, s)
        self.assertIn("Mick shouts the round", text)
        self.assertIn("Settle up", text)

    # helpers
    def _assert_settles(self, bal, tx):
        left = dict(bal)
        for t in tx:
            self.assertGreater(t.cents, 0)
            left[t.payer] += t.cents
            left[t.payee] -= t.cents
        self.assertTrue(all(v == 0 for v in left.values()), left)

    @staticmethod
    def _brute_min(vals):
        nz = [v for v in vals if v]
        best = 0
        # max number of disjoint zero-sum groups via brute force on partitions
        def rec(rem):
            if not rem:
                return 0
            first, rest = rem[0], rem[1:]
            out = 0
            for k in range(len(rest) + 1):
                for combo in itertools.combinations(range(len(rest)), k):
                    if first + sum(rest[i] for i in combo) == 0:
                        left = [rest[i] for i in range(len(rest)) if i not in combo]
                        out = max(out, 1 + rec(left))
            return out
        best = rec(nz)
        return len(nz) - best


if __name__ == "__main__":
    unittest.main()
