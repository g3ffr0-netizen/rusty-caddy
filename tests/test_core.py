import json
import tempfile
import unittest
from pathlib import Path

from caddy.clubs import DEFAULT_CLUBS, get_caddy_advice, pick_club, plays_like
from caddy.handicap import playing_handicap, stableford_points, strokes_on_hole
from caddy.models import Course, Player, Round, Settings, new_round
from caddy.storage import Store


class ClubTests(unittest.TestCase):
    def test_distance_now_changes_the_club(self):
        a = get_caddy_advice(DEFAULT_CLUBS, 4, 120)
        b = get_caddy_advice(DEFAULT_CLUBS, 4, 160)
        self.assertEqual(a.club, "8 Iron")  # shortest club that carries 120 m (9 Iron only carries 115)
        self.assertEqual(b.club, "4 Hybrid")
        self.assertTrue(a.reachable and b.reachable)

    def test_headwind_and_uphill_club_up_tailwind_clubs_down(self):
        self.assertGreater(plays_like(140, 20, "Headwind"), 140)
        self.assertLess(plays_like(140, 20, "Tailwind"), 140)
        self.assertEqual(plays_like(140, 0, "None", 10), 150)
        calm = get_caddy_advice(DEFAULT_CLUBS, 4, 130).club
        into = get_caddy_advice(DEFAULT_CLUBS, 4, 130, wind_kmh=30, wind_dir="Headwind").club
        self.assertEqual(calm, "7 Iron")
        self.assertNotEqual(into, calm)

    def test_unreachable_is_positional_shot_with_layup_plan(self):
        adv = get_caddy_advice(DEFAULT_CLUBS, 5, 480, pressure=3)
        self.assertFalse(adv.reachable)
        self.assertEqual(adv.club, "Driver")
        self.assertIn("leave yourself", adv.next_shot)
        safe = get_caddy_advice(DEFAULT_CLUBS, 4, 380, pressure=9)
        self.assertIn("FAKE FAVOURITE", safe.strategy)
        self.assertNotEqual(safe.club, "Driver")

    def test_high_pressure_clubs_up_and_miss_tip(self):
        normal = get_caddy_advice(DEFAULT_CLUBS, 3, 130, pressure=5)
        tense = get_caddy_advice(DEFAULT_CLUBS, 3, 130, pressure=9, miss="Slice")
        self.assertGreater(tense.carry_m, normal.carry_m)
        self.assertIn("Aim left", tense.aim_tip)

    def test_pick_club_handles_messy_table(self):
        name, carry, ok = pick_club([["", 10], ["Wedge", "95"], ["Bad", "x"], ["Driver", 200]], 90)
        self.assertEqual((name, carry, ok), ("Wedge", 95, True))


class HandicapTests(unittest.TestCase):
    def test_strokes_received_and_plus_handicaps(self):
        self.assertEqual(strokes_on_hole(18, 18), 1)
        self.assertEqual(strokes_on_hole(20, 2), 2)
        self.assertEqual(strokes_on_hole(20, 3), 1)
        self.assertEqual(strokes_on_hole(0, 1), 0)
        self.assertEqual(strokes_on_hole(-2, 18), -1)
        self.assertEqual(strokes_on_hole(-2, 16), 0)
        self.assertEqual(sum(strokes_on_hole(27, si) for si in range(1, 19)), 27)

    def test_stableford_points(self):
        self.assertEqual(stableford_points(5, 4, 1), 2)  # net par
        self.assertEqual(stableford_points(3, 4, 0), 3)  # birdie
        self.assertEqual(stableford_points(8, 4, 0), 0)  # quad
        self.assertEqual(stableford_points(None, 4, 1), 0)  # pick-up

    def test_allowance_rounds_half_up(self):
        self.assertEqual(playing_handicap(15, 0.9), 14)  # 13.5 -> 14
        self.assertEqual(playing_handicap(10.4), 10)


class RoundModelTests(unittest.TestCase):
    def setUp(self):
        self.r = Round(Course(), [Player("A", 10), Player("B", 20)])

    def test_bogey_and_any_score_can_be_logged(self):
        self.r.adjust_score("A", 1, +1)  # first tap = par
        self.assertEqual(self.r.gross("A", 1), 4)
        self.r.adjust_score("A", 1, +1)  # bogey (used to be impossible)
        self.assertEqual(self.r.gross("A", 1), 5)
        self.r.adjust_score("B", 1, -1)  # first minus = birdie
        self.assertEqual(self.r.gross("B", 1), 3)
        self.r.set_score("B", 2, None)
        self.assertIsNone(self.r.gross("B", 2))
        self.assertTrue(self.r.has_score("B", 2))

    def test_round_stops_at_18(self):
        self.assertEqual(self.r.go_to_hole(25), 18)
        self.assertEqual(self.r.go_to_hole(0), 1)
        with self.assertRaises(ValueError):
            self.r.set_score("A", 19, 4)
        for h in range(1, 19):
            for p in ("A", "B"):
                self.r.set_score(p, h, 4)
        self.assertTrue(self.r.is_complete())

    def test_course_validation(self):
        c = Course()
        self.assertEqual(c.validate(), [])
        self.assertEqual(c.par, 72)
        c.holes[0].stroke_index = 2
        self.assertTrue(c.validate())

    def test_round_json_round_trip(self):
        self.r.set_score("A", 3, 6)
        self.r.set_score("B", 3, None)
        self.r.wolf_picks[3] = ""
        back = Round.from_dict(json.loads(json.dumps(self.r.to_dict())))
        self.assertEqual(back.gross("A", 3), 6)
        self.assertIsNone(back.gross("B", 3))
        self.assertEqual(back.wolf_picks, {3: ""})
        self.assertEqual(back.round_id, self.r.round_id)


class StorageTests(unittest.TestCase):
    def test_every_save_survives_restart_and_corruption_falls_back_to_bak(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            r = new_round(Settings())
            r.set_score("Rusty", 1, 5)
            store.save_round(r)
            r.set_score("Rusty", 2, 4)
            store.save_round(r)
            loaded = Store(tmp).load_round()  # simulates a phone refresh / server restart
            self.assertEqual(loaded.gross("Rusty", 2), 4)
            Path(tmp, "current_round.json").write_text("{corrupt", encoding="utf-8")
            recovered = Store(tmp).load_round()
            self.assertEqual(recovered.gross("Rusty", 1), 5)  # .bak has the previous tap

    def test_archive_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            s = Settings(pro_shop_phone="02 9555 1234", latitude=-33.8)
            store.save_settings(s)
            self.assertEqual(store.load_settings().pro_shop_phone, "02 9555 1234")
            r = new_round(s)
            store.save_round(r)
            dest = store.archive_round(r)
            self.assertTrue(dest.exists())
            self.assertIsNone(store.load_round())
            self.assertEqual(len(store.list_archived()), 1)


if __name__ == "__main__":
    unittest.main()
