"""Unit tests for GPS rangefinder, Mangrove Mountain course preset, and 3-Club Challenge."""
from __future__ import annotations

import unittest
from pathlib import Path

from caddy import courses as CR
from caddy import rangefinder as RF


class TestRangefinderPhysics(unittest.TestCase):
    def test_haversine_and_bearing_north_111m(self):
        # 0.001 deg latitude ~= 111.19 m due North
        d = RF.haversine_m(-33.2945, 151.2015, -33.2935, 151.2015)
        b = RF.bearing_deg(-33.2945, 151.2015, -33.2935, 151.2015)
        self.assertAlmostEqual(d, 111.2, delta=1.5)
        self.assertAlmostEqual(b, 0.0, delta=0.5)

    def test_gps_smoothing_rejects_noisy_outliers(self):
        fixes = [
            RF.GPSFix(-33.2945, 151.2015, accuracy_m=4.0, elevation_m=300.0),
            RF.GPSFix(-33.2946, 151.2016, accuracy_m=5.0, elevation_m=301.0),
            RF.GPSFix(-33.3500, 151.2500, accuracy_m=45.0, elevation_m=200.0),  # noisy >15m
        ]
        smooth = RF.smooth_gps_fixes(fixes, max_accuracy_m=15.0)
        self.assertIsNotNone(smooth)
        self.assertAlmostEqual(smooth.lat, -33.29455, places=4)
        self.assertAlmostEqual(smooth.accuracy_m, 4.5, places=2)
        self.assertIn("GOOD", RF.accuracy_badge(smooth.accuracy_m))

    def test_front_middle_back_and_uphill_lie_plays_like(self):
        player = RF.GPSFix(-33.2948, 151.2015, accuracy_m=4.0, elevation_m=300.0)
        green = RF.GreenTargets(middle_lat=-33.2935, middle_lon=151.2015, green_elevation_m=306.0)
        reading = RF.compute_rangefinder_reading(
            player,
            green,
            wind_kmh=16.0,
            wind_dir="Headwind",
            lie="Uphill Lie",
        )
        self.assertLess(reading.front_m, reading.middle_m)
        self.assertLess(reading.middle_m, reading.back_m)
        # Headwind + 6m elevation + 8m uphill lie => plays significantly longer than raw middle
        self.assertGreater(reading.plays_like_middle_m, reading.middle_m + 18)
        self.assertEqual(reading.compass, "N")
        self.assertIn("Uphill", reading.lie_tip)

    def test_measure_shot_distance(self):
        tee = RF.GPSFix(-33.2950, 151.2015, accuracy_m=5.0)
        ball = RF.GPSFix(-33.2933, 151.2015, accuracy_m=5.0)
        dist = RF.measure_shot_m(tee, ball)
        self.assertGreater(dist, 180)
        self.assertLess(dist, 200)


class TestThreeClubChallengeAndMangroveCourse(unittest.TestCase):
    def test_three_club_challenge_bands_and_tight_lie(self):
        # 1. Green / Fringe -> 3 Wood Putter
        putt = RF.recommend_three_club_shot(12.0, on_green_or_fringe=True)
        self.assertIn("3 Wood", putt.club)
        self.assertIn("Putter", putt.club)

        # 2. 50m off Tight / Thin Grass -> recommends 7 Iron bump-and-run over 60° wedge
        tight = RF.recommend_three_club_shot(50.0, lie="Tight / Thin Grass")
        self.assertEqual(tight.club, "7 Iron")
        self.assertIn("Bump-and-Run", tight.shot_type)

        # 3. 50m off Flat / Fairway -> 60° Wedge
        flat_w = RF.recommend_three_club_shot(50.0, lie="Flat / Fairway")
        self.assertEqual(flat_w.club, "60° Wedge")

        # 4. 95m gap -> Knockdown 7 Iron
        gap = RF.recommend_three_club_shot(95.0, lie="Flat / Fairway")
        self.assertEqual(gap.club, "7 Iron")
        self.assertIn("Knockdown", gap.shot_type)

        # 5. 185m fairway -> 3 Wood
        go = RF.recommend_three_club_shot(185.0, lie="Flat / Fairway", pressure=4)
        self.assertEqual(go.club, "3 Wood")

    def test_mangrove_mountain_course_json_validates(self):
        path = Path(__file__).resolve().parents[1] / "courses" / "mangrove_mountain.json"
        course = CR.load_course_file(path)
        self.assertEqual(course.par, 70)
        self.assertEqual(len(course.holes), 18)
        self.assertIn("Mangrove Mountain", course.name)


if __name__ == "__main__":
    unittest.main()
