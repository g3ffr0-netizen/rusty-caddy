import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from caddy import clubs as C
from caddy import courses as CR
from caddy import fines as F
from caddy import stats as ST
from caddy import weather as W
from caddy.models import (
    DEFAULT_SWING_CUE,
    Course,
    Player,
    Round,
    Settings,
    new_round,
    normalise_swing_cue,
)
from caddy.storage import Store


class SwingCueTests(unittest.TestCase):
    def test_defaults_and_normalisation(self):
        s = Settings()
        self.assertEqual(s.swing_cue, "Hips · Load · Go")
        self.assertEqual(DEFAULT_SWING_CUE, "Hips · Load · Go")
        r = new_round(s)
        self.assertEqual(r.swing_cue, "Hips · Load · Go")
        self.assertEqual(normalise_swing_cue("   "), "Hips · Load · Go")
        self.assertEqual(normalise_swing_cue(None), "Hips · Load · Go")
        self.assertEqual(normalise_swing_cue("  Tempo   Smooth   Finish "), "Tempo Smooth Finish")

    def test_swing_cue_persists_across_restart_and_legacy_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            s = Settings(swing_cue="Breathe · Target · Commit")
            store.save_settings(s)
            r = new_round(s)
            store.save_round(r)

            loaded_s = Store(tmp).load_settings()
            loaded_r = Store(tmp).load_round()
            self.assertEqual(loaded_s.swing_cue, "Breathe · Target · Commit")
            self.assertEqual(loaded_r.swing_cue, "Breathe · Target · Commit")

            # Legacy JSON without swing_cue field falls back cleanly
            raw_s = json.loads(Path(tmp, "settings.json").read_text(encoding="utf-8"))
            raw_s.pop("swing_cue", None)
            Path(tmp, "settings.json").write_text(json.dumps(raw_s), encoding="utf-8")
            self.assertEqual(Store(tmp).load_settings().swing_cue, "Hips · Load · Go")


class RoundStatsTests(unittest.TestCase):
    def setUp(self):
        self.r = Round(Course(), [Player("Rusty", 18.0), Player("Dave", 12.0)])

    def test_hole_stats_and_par3_fairway_exclusion(self):
        # Hole 1 is Par 4, Hole 3 is Par 3, Hole 4 is Par 5
        self.r.set_score("Rusty", 1, 4)
        self.r.toggle_fir("Rusty", 1, True)
        self.r.toggle_gir("Rusty", 1, True)
        self.assertEqual(self.r.adjust_putts("Rusty", 1, +1), 2)
        self.assertEqual(self.r.adjust_penalties("Rusty", 1, +1), 1)
        self.assertEqual(self.r.adjust_penalties("Rusty", 1, -1), 0)

        # Par 3 ignores FIR
        self.r.set_score("Rusty", 3, 4)
        self.r.toggle_fir("Rusty", 3, True)
        self.assertIsNone(self.r.get_hole_stats("Rusty", 3)["fir"])
        self.r.toggle_gir("Rusty", 3, False)
        self.assertEqual(self.r.adjust_putts("Rusty", 3, -1), 1)

        # Par 5 miss fairway, 3-putt, 1 penalty, net double blow-up (8 on par 5 with 1 stroke -> net 7 = par+2)
        self.r.set_score("Rusty", 4, 8)
        self.r.toggle_fir("Rusty", 4, False)
        self.r.toggle_gir("Rusty", 4, False)
        self.r.set_hole_stats("Rusty", 4, putts=3, penalties=1)

        # Add a fine and a shout
        F.add_fine(self.r, "Rusty", F.DEFAULT_FINES[1], hole=4)  # $2.00 obscenity
        F.add_fine(self.r, "Dave", F.DEFAULT_FINES[0], hole=4)  # Shout the round

        summary = ST.round_stats_summary(self.r, "Rusty")
        self.assertEqual(summary.holes_scored, 3)
        self.assertEqual(summary.gross_total, 16)
        self.assertEqual(summary.to_par, 4)  # 16 vs par 12 (4+3+5)
        self.assertEqual(summary.blow_ups, 1)
        self.assertEqual((summary.fir_hit, summary.fir_tracked, summary.fir_pct), (1, 2, 50))
        self.assertEqual((summary.gir_hit, summary.gir_tracked, summary.gir_pct), (1, 3, 33))
        self.assertEqual((summary.total_putts, summary.putts_tracked, summary.three_putts), (6, 3, 1))
        self.assertEqual(summary.putts_per_hole, 2.0)
        self.assertEqual(summary.total_penalties, 1)
        self.assertEqual(summary.fines_count, 2)
        self.assertEqual(summary.fines_total_cents, 200)
        self.assertEqual(summary.shouts_count, 1)
        self.assertEqual(ST.format_ratio(summary.fir_hit, summary.fir_tracked), "1/2 (50%)")
        self.assertEqual(ST.format_to_par(0), "E")
        self.assertEqual(ST.format_to_par(-2), "-2")

        # Toggle again clears FIR
        self.r.toggle_fir("Rusty", 1, True)
        self.assertIsNone(self.r.get_hole_stats("Rusty", 1)["fir"])

    def test_hole_stats_json_round_trip(self):
        self.r.set_hole_stats("Rusty", 2, fir=True, gir=False, putts=2, penalties=1)
        back = Round.from_dict(json.loads(json.dumps(self.r.to_dict())))
        self.assertEqual(back.get_hole_stats("Rusty", 2), {"fir": True, "gir": False, "putts": 2, "penalties": 1})


class CourseLoaderTests(unittest.TestCase):
    def test_bundled_course_templates_are_valid(self):
        files = CR.list_course_files()
        names = [p.name for p in files]
        self.assertIn("course_template.json", names)
        self.assertIn("coastal_links_sample.json", names)
        for f in files:
            c = CR.load_course_file(f)
            self.assertEqual(c.validate(), [])
            self.assertEqual(len(c.holes), 18)
            self.assertTrue(c.pro_shop_phone)
            self.assertGreater(c.total_distance_m, 4000)
            self.assertIsNotNone(c.latitude)
            self.assertIsNotNone(c.longitude)
            self.assertIn(c.name, CR.course_label(f))

    def test_validation_and_aliases_and_export_round_trip(self):
        with self.assertRaises(ValueError):
            CR.load_course_json("{bad json")
        with self.assertRaises(ValueError):
            CR.load_course_dict({"name": "Short", "holes": [{"number": 1, "par": 4, "stroke_index": 1}]})

        # Flat aliases: metres + pro_shop_phone
        holes = [{"number": i, "par": 4, "stroke_index": i, "metres": 350} for i in range(1, 19)]
        raw = {"name": "Flat Club", "pro_shop_phone": "02 9111 2222", "latitude": -33.9, "longitude": 151.2, "holes": holes}
        c = CR.load_course_dict(raw)
        self.assertEqual(c.pro_shop_phone, "02 9111 2222")
        self.assertEqual(c.hole(1).distance_m, 350)
        self.assertEqual(c.total_distance_m, 18 * 350)

        # Round trip export + save + apply to settings/round
        exported = CR.export_course_json(c)
        reloaded = CR.load_course_json(exported)
        self.assertEqual(reloaded.name, "Flat Club")
        self.assertEqual(reloaded.pro_shop_phone, "02 9111 2222")

        with tempfile.TemporaryDirectory() as tmp:
            saved = CR.save_course_file(reloaded, tmp)
            self.assertTrue(saved.exists())
            self.assertIn(saved, CR.list_course_files([tmp]))

        s = Settings()
        r = new_round(s)
        CR.apply_course_to_settings(s, reloaded, r)
        self.assertEqual(s.course.name, "Flat Club")
        self.assertEqual(r.course.name, "Flat Club")
        self.assertEqual(s.pro_shop_phone, "02 9111 2222")
        self.assertEqual(s.latitude, -33.9)


class OpenMeteoWindPlaysLikeTests(unittest.TestCase):
    def test_extract_wind_from_open_meteo_conditions(self):
        sample = {
            "current": {
                "temperature_2m": 26.0,
                "apparent_temperature": 27.0,
                "wind_speed_10m": 22.0,
                "wind_gusts_10m": 38.0,
                "wind_direction_10m": 90,
                "uv_index": 5.0,
            }
        }
        cond = W.current_conditions(sample)
        w = W.extract_wind(cond)
        self.assertIsNotNone(w)
        self.assertEqual(w["wind_kmh"], 22.0)
        self.assertEqual(w["gust_kmh"], 38.0)
        self.assertEqual(w["wind_dir_deg"], 90.0)
        self.assertEqual(w["compass"], "E")
        self.assertIsNone(W.extract_wind(None))
        self.assertIsNone(W.extract_wind({"wind_kmh": 10.0}))

    def test_wind_vector_decomposition_and_exact_parity(self):
        # Wind from East (90), hitting East (90) => pure headwind
        h, c = C.decompose_wind(20, 90, 90)
        self.assertAlmostEqual(h, 20.0, places=5)
        self.assertAlmostEqual(c, 0.0, places=5)
        wa_head = C.wind_plays_like(150, 20, 90, 90, elevation_m=5, gust_kmh=35)
        self.assertAlmostEqual(wa_head.plays_like_m, C.plays_like(150, 20, "Headwind", 5), places=5)
        self.assertEqual(wa_head.relative_label, "Headwind")
        self.assertIsNotNone(wa_head.gust_plays_like_m)
        self.assertGreater(wa_head.gust_plays_like_m, wa_head.plays_like_m)

        # Wind from West (270), hitting East (90) => pure tailwind
        wa_tail = C.wind_plays_like(150, 20, 270, 90)
        self.assertAlmostEqual(wa_tail.plays_like_m, C.plays_like(150, 20, "Tailwind"), places=5)
        self.assertLess(wa_tail.wind_effect_m, 0)
        self.assertEqual(wa_tail.relative_label, "Tailwind")

        # Wind from North (0), hitting East (90) => pure crosswind from left
        h_c, c_c = C.decompose_wind(20, 0, 90)
        self.assertAlmostEqual(h_c, 0.0, places=5)
        self.assertAlmostEqual(c_c, -20.0, places=5)
        wa_cross = C.wind_plays_like(150, 20, 0, 90)
        self.assertAlmostEqual(wa_cross.plays_like_m, C.plays_like(150, 20, "Cross"), places=5)
        self.assertIn("from left", wa_cross.relative_label)
        self.assertIn("drifts right", wa_cross.aim_drift_tip)

        # Wind from South (180), hitting East (90) => pure crosswind from right
        wa_right = C.wind_plays_like(150, 20, 180, 90)
        self.assertIn("from right", wa_right.relative_label)
        self.assertIn("drifts left", wa_right.aim_drift_tip)

    def test_get_caddy_advice_integrates_open_meteo_wind(self):
        into = C.get_caddy_advice(
            C.DEFAULT_CLUBS, par=3, distance_m=135, wind_kmh=28, wind_dir_deg=90, shot_bearing_deg=90, gust_kmh=42
        )
        down = C.get_caddy_advice(
            C.DEFAULT_CLUBS, par=3, distance_m=135, wind_kmh=28, wind_dir_deg=270, shot_bearing_deg=90, gust_kmh=42
        )
        self.assertIsNotNone(into.wind_adjustment)
        self.assertGreater(into.plays_like_m, 135)
        self.assertLess(down.plays_like_m, 135)
        self.assertGreater(into.carry_m, down.carry_m)


class EnginePurityTests(unittest.TestCase):
    def test_caddy_engine_has_no_streamlit_imports(self):
        caddy_dir = Path(__file__).resolve().parents[1] / "caddy"
        for py_file in caddy_dir.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(alias.name.startswith("streamlit"), f"{py_file} imports streamlit")
                elif isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith("streamlit"), f"{py_file} imports streamlit")


class Task003bAppTests(unittest.TestCase):
    """End-to-end headless Streamlit UI checks for TASK-003b features."""

    def test_swing_cue_course_loader_stats_and_open_meteo_wind_ui(self):
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:  # pragma: no cover
            self.skipTest("streamlit not installed")

        app = str(Path(__file__).resolve().parents[1] / "caddy_app.py")
        fake_meteo = {
            "current": {
                "temperature_2m": 24.0,
                "apparent_temperature": 25.0,
                "wind_speed_10m": 25.0,
                "wind_gusts_10m": 38.0,
                "wind_direction_10m": 90,
                "uv_index": 4.0,
                "weather_code": 1,
            },
            "hourly": {
                "uv_index": [4.0],
                "cape": [100.0],
                "lightning_potential": [None],
                "apparent_temperature": [25.0],
                "weather_code": [1],
                "wind_gusts_10m": [38.0],
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["RUSTY_CADDY_DATA"] = tmp
            try:
                with mock.patch("caddy.weather.fetch_open_meteo", return_value=fake_meteo), mock.patch(
                    "caddy.weather.fetch_bom_xml", return_value="<rss><channel></channel></rss>"
                ):
                    at = AppTest.from_file(app, default_timeout=60).run()
                    self.assertFalse(at.exception, [e.value for e in at.exception])

                    # 1. Default Pre-Shot Routine / Swing Cue rendered at top of Caddy tab
                    self.assertTrue(any("Hips · Load · Go" in m.value for m in at.markdown))

                    # Edit swing cue in Setup and confirm persistence
                    at.text_input(key="setup_swing_cue").set_value("Smooth · Balanced · Hold")
                    at.button(key="FormSubmitter:setup_form-💾 Save setup").click().run()
                    self.assertFalse(at.exception, [e.value for e in at.exception])
                    self.assertTrue(any("Smooth · Balanced · Hold" in m.value for m in at.markdown))

                    # Also edit swing cue inline on Caddy tab and confirm persistence
                    at.text_input(key="caddy_swing_cue_input").set_value("Breath · Tempo · Target").run()
                    at.button(key="btn_save_cue_inline").click().run()
                    self.assertFalse(at.exception, [e.value for e in at.exception])
                    self.assertTrue(any("Breath · Tempo · Target" in m.value for m in at.markdown))

                    # 2. Log score + one-tap hole stats (FIR, GIR, putts, penalties)
                    at.button(key="plus_0").click().run()
                    at.button(key="btn_fir_hit").click().run()
                    at.button(key="btn_gir_hit").click().run()
                    at.button(key="btn_putts_plus").click().run()
                    at.button(key="btn_pen_plus").click().run()
                    self.assertFalse(at.exception, [e.value for e in at.exception])
                    # Summary shows 1/1 (100%) for GIR & FIR
                    self.assertTrue(any("1/1 (100%)" in m.value for m in at.markdown))

                    # 3. Load a local JSON course template in Setup (also populates coords -> live Open-Meteo wind!)
                    at.button(key="btn_load_course").click().run()
                    self.assertFalse(at.exception, [e.value for e in at.exception])

                    # Reload fresh session: swing cue, hole stats, loaded course & live Open-Meteo wind all persist
                    fresh = AppTest.from_file(app, default_timeout=60).run()
                    self.assertFalse(fresh.exception, [e.value for e in fresh.exception])
                    self.assertTrue(any("Breath · Tempo · Target" in m.value for m in fresh.markdown))
                    self.assertTrue(any("Live Open-Meteo Wind" in m.value for m in fresh.markdown))
                    self.assertTrue(any("1/1 (100%)" in m.value for m in fresh.markdown))

                    saved_settings = json.loads(Path(tmp, "settings.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved_settings["swing_cue"], "Breath · Tempo · Target")
                    self.assertTrue(saved_settings["pro_shop_phone"])
                    saved_round = json.loads(Path(tmp, "current_round.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved_round["hole_stats"]["Rusty"]["1"]["fir"], True)
                    self.assertEqual(saved_round["hole_stats"]["Rusty"]["1"]["gir"], True)
                    self.assertEqual(saved_round["hole_stats"]["Rusty"]["1"]["putts"], 2)
                    self.assertEqual(saved_round["hole_stats"]["Rusty"]["1"]["penalties"], 1)
            finally:
                os.environ.pop("RUSTY_CADDY_DATA", None)


if __name__ == "__main__":
    unittest.main()
