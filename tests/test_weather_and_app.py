import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from caddy import weather as W

BOM_SAMPLE = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0"><channel><title>Weather Warnings for Western Australia</title>
<item><title>25/13:01 WST Marine Wind Warning Summary for Western Australia</title><link>http://reg.bom.gov.au/wa/warnings/marine.shtml</link><pubDate>Wed, 25 Nov 2026 05:01:13 GMT</pubDate></item>
<item><title>25/11:41 WST Heatwave Warning (WA)</title><link>http://reg.bom.gov.au/wa/warnings/heatwave.shtml</link><pubDate>Wed, 25 Nov 2026 03:41:42 GMT</pubDate></item>
<item><title>25/12:47 WST
                Severe Thunderstorm Warning
for
                parts of South Interior district.
            </title><link>http://reg.bom.gov.au/products/IDW21033.shtml</link><pubDate>Wed, 25 Nov 2026 04:47:42 GMT</pubDate></item>
</channel></rss>"""

OPEN_METEO_SAMPLE = {
    "current": {"temperature_2m": 33.0, "apparent_temperature": 36.5, "wind_speed_10m": 17.3, "wind_gusts_10m": 41.0,
                "wind_direction_10m": 93, "uv_index": 9.2, "weather_code": 3},
    "hourly": {"uv_index": [9.0, 8.1, 6.0], "cape": [1500.0, 2700.0, 900.0], "lightning_potential": [None, None, None],
               "apparent_temperature": [36.0, 35.0, 33.0], "weather_code": [3, 95, 3], "wind_gusts_10m": [40.7, 41.0, 41.8]},
}


class OpenMeteoTests(unittest.TestCase):
    def test_storm_heat_uv_alerts(self):
        alerts = W.evaluate_open_meteo(OPEN_METEO_SAMPLE)
        kinds = {(a.kind, a.level) for a in alerts}
        self.assertIn(("storm", "danger"), kinds)  # WMO 95 in the next hours
        self.assertIn(("storm", "warning"), kinds)  # CAPE 2700
        self.assertIn(("uv", "warning"), kinds)  # UV 9.2
        self.assertIn(("heat", "warning"), kinds)  # feels 36.5
        self.assertEqual(alerts[0].level, "danger")  # sorted most severe first
        self.assertFalse(any("Lightning potential" in a.title for a in alerts))  # null in AU -> ignored

    def test_quiet_day_has_no_alerts(self):
        quiet = {"current": {"apparent_temperature": 20, "uv_index": 1, "weather_code": 1, "wind_gusts_10m": 10}, "hourly": {}}
        self.assertEqual(W.evaluate_open_meteo(quiet), [])

    def test_fetch_uses_injected_opener(self):
        seen = {}

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(req, timeout):
            seen["url"] = req.full_url
            return Resp(json.dumps(OPEN_METEO_SAMPLE).encode())

        data = W.fetch_open_meteo(-33.87, 151.21, opener=opener)
        self.assertEqual(data["current"]["uv_index"], 9.2)
        self.assertIn("latitude=-33.8700", seen["url"])
        self.assertEqual(W.current_conditions(data)["wind_kmh"], 17.3)
        self.assertEqual(W.compass(93), "E")


class BomTests(unittest.TestCase):
    def test_parse_and_classify_real_feed_shape(self):
        items = W.parse_bom_rss(BOM_SAMPLE)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[2]["title"], "25/12:47 WST Severe Thunderstorm Warning for parts of South Interior district.")
        alerts = W.classify_bom(items)
        titles = [a.title for a in alerts]
        self.assertFalse(any("Marine" in t for t in titles))  # irrelevant on a golf course
        self.assertTrue(any("Heatwave" in t for t in titles))
        storm = next(a for a in alerts if "Thunderstorm" in a.title)
        self.assertEqual(storm.level, "warning")

    def test_district_keyword_sharpens_relevance(self):
        items = W.parse_bom_rss(BOM_SAMPLE)
        mine = next(a for a in W.classify_bom(items, "South Interior") if "Thunderstorm" in a.title)
        other = next(a for a in W.classify_bom(items, "Perth Metropolitan") if "Thunderstorm" in a.title)
        self.assertEqual(mine.level, "danger")
        self.assertEqual(other.level, "caution")

    def test_feed_table_covers_states(self):
        self.assertEqual(W.BOM_FEEDS["vic"][0], "IDZ00059")
        self.assertEqual(len(W.BOM_FEEDS), 7)


class LightningAndProShopTests(unittest.TestCase):
    def test_30_minute_timer_resets_on_new_strike(self):
        self.assertEqual(W.lightning_status(None, 1000), (False, 0))
        self.assertEqual(W.lightning_status(1000, 1000), (True, 1800))
        self.assertEqual(W.lightning_status(1000, 1000 + 1799), (True, 1))
        self.assertEqual(W.lightning_status(1000, 1000 + 1800), (False, 0))
        self.assertEqual(W.lightning_status(2500, 2800), (True, 1500))  # new tap restarts the clock
        self.assertEqual(W.format_countdown(1500), "25:00")

    def test_pro_shop_links(self):
        self.assertEqual(W.normalise_phone("(02) 9555-1234"), "0295551234")
        self.assertEqual(W.normalise_phone("+61 2 9555 1234"), "+61295551234")
        self.assertEqual(W.tel_link("02 9555 1234"), "tel:0295551234")
        msg = W.pro_shop_message(7, "Rose Bay GC", "14:05")
        self.assertEqual(msg, "Lightning/thunder spotted near Hole 7 — requesting course check (Rose Bay GC) at 14:05.")
        link = W.sms_link("02 9555 1234", msg)
        self.assertTrue(link.startswith("sms:0295551234?&body=Lightning%2Fthunder%20spotted%20near%20Hole%207"))
        self.assertEqual(W.sms_link("", msg), "")


class AppSmokeTests(unittest.TestCase):
    """Drives the real Streamlit script headlessly (no network: no location configured)."""

    def test_tap_persists_across_refresh(self):
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:  # pragma: no cover
            self.skipTest("streamlit not installed")
        app = str(Path(__file__).resolve().parents[1] / "caddy_app.py")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["RUSTY_CADDY_DATA"] = tmp
            try:
                at = AppTest.from_file(app, default_timeout=60).run()
                self.assertFalse(at.exception, [e.value for e in at.exception])
                at.button(key="plus_0").click().run()
                at.button(key="plus_0").click().run()  # bogey
                self.assertFalse(at.exception)
                saved = json.loads(Path(tmp, "current_round.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["scores"]["Rusty"]["1"], 5)
                at.button(key="btn_thunder").click().run()
                self.assertTrue(any("STOP PLAY" in e.value for e in at.error))

                fresh = AppTest.from_file(app, default_timeout=60).run()  # sleeping phone / refresh
                self.assertFalse(fresh.exception)
                self.assertTrue(any("STOP PLAY" in e.value for e in fresh.error))
                for _ in range(17):
                    fresh.button(key="btn_next").click().run()
                self.assertTrue(any("Hole 18" in m.value for m in fresh.markdown))
                self.assertTrue(fresh.button(key="btn_next").disabled)  # can't walk past the 18th
            finally:
                os.environ.pop("RUSTY_CADDY_DATA", None)


if __name__ == "__main__":
    unittest.main()
