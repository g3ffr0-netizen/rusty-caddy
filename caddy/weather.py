"""Free weather stack: Open-Meteo storm/heat/UV, BOM warnings RSS, manual lightning timer, Pro Shop alert links.

Not a safety device: the club siren, BOM warnings and your own judgement always come first.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Callable

LIGHTNING_WINDOW_S = 30 * 60
THUNDER_CODES = {95, 96, 99}  # WMO weather codes: thunderstorm (with/without hail)
LEVEL_ORDER = {"danger": 0, "warning": 1, "caution": 2, "info": 3}
USER_AGENT = "Mozilla/5.0 (rusty-caddy; personal non-commercial use)"

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# BOM state warning RSS feeds (free for personal, non-commercial use).
BOM_FEEDS = {
    "nsw": ("IDZ00054", "NSW / ACT"),
    "nt": ("IDZ00055", "NT"),
    "qld": ("IDZ00056", "QLD"),
    "sa": ("IDZ00057", "SA"),
    "tas": ("IDZ00058", "TAS"),
    "vic": ("IDZ00059", "VIC"),
    "wa": ("IDZ00060", "WA"),
}


@dataclass
class Alert:
    level: str  # danger | warning | caution | info
    kind: str  # storm | heat | uv | wind | bom | system
    title: str
    message: str = ""
    link: str = ""


def sort_alerts(alerts: list[Alert]) -> list[Alert]:
    return sorted(alerts, key=lambda a: LEVEL_ORDER.get(a.level, 9))


# ---------------------------------------------------------------- HTTP
def _get(url: str, timeout: float = 10.0, opener: Callable | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with (opener or urllib.request.urlopen)(req, timeout=timeout) as r:
        return r.read()


def fetch_open_meteo(lat: float, lon: float, timeout: float = 10.0, opener: Callable | None = None) -> dict:
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "current": "temperature_2m,apparent_temperature,wind_speed_10m,wind_gusts_10m,wind_direction_10m,uv_index,weather_code",
        "hourly": "temperature_2m,apparent_temperature,uv_index,cape,lightning_potential,precipitation_probability,weather_code,wind_gusts_10m",
        "forecast_hours": "3",
        "timezone": "auto",
    }
    return json.loads(_get(f"{OPEN_METEO_URL}?{urllib.parse.urlencode(params)}", timeout, opener))


def geocode(name: str, timeout: float = 10.0, opener: Callable | None = None) -> list[dict]:
    params = {"name": name, "count": "5", "country_code": "AU", "language": "en"}
    data = json.loads(_get(f"{GEOCODE_URL}?{urllib.parse.urlencode(params)}", timeout, opener))
    return [
        {
            "label": ", ".join(x for x in (r.get("name"), r.get("admin1")) if x),
            "latitude": r["latitude"],
            "longitude": r["longitude"],
        }
        for r in data.get("results", []) or []
    ]


def fetch_bom_xml(state: str, timeout: float = 10.0, opener: Callable | None = None) -> str:
    code, _ = BOM_FEEDS[state.lower()]
    return _get(f"https://www.bom.gov.au/fwo/{code}.warnings_{state.lower()}.xml", timeout, opener).decode("utf-8", "replace")


# ---------------------------------------------------------------- Open-Meteo evaluation
def _vals(series: Any) -> list[float]:
    return [float(v) for v in (series or []) if v is not None]


def evaluate_open_meteo(data: dict) -> list[Alert]:
    cur = data.get("current") or {}
    hr = data.get("hourly") or {}
    alerts: list[Alert] = []

    codes = _vals(hr.get("weather_code")) + _vals([cur.get("weather_code")])
    if any(int(c) in THUNDER_CODES for c in codes):
        alerts.append(Alert("danger", "storm", "⛈️ Thunderstorm forecast in the next few hours",
                            "Plan your shelter now. If you hear thunder, stop play and start the 30-minute timer."))
    lp = _vals(hr.get("lightning_potential"))
    if lp and max(lp) > 0:
        alerts.append(Alert("warning", "storm", "⚡ Lightning potential detected", f"Lightning potential index {max(lp):.0f} J/kg."))
    cape = max(_vals(hr.get("cape")), default=0.0)
    if cape >= 2500:
        alerts.append(Alert("warning", "storm", "🌩️ High storm energy (CAPE)", f"CAPE {cape:.0f} J/kg: storms can build fast."))
    elif cape >= 1000:
        alerts.append(Alert("caution", "storm", "🌥️ Storm potential (CAPE)", f"CAPE {cape:.0f} J/kg: keep an eye on the sky."))

    uv = max(_vals(hr.get("uv_index")) + _vals([cur.get("uv_index")]), default=0.0)
    if uv >= 11:
        alerts.append(Alert("danger", "uv", f"☀️ Extreme UV ({uv:.0f})", "Slip, slop, slap, seek, slide. Reapply sunscreen every 2 hours."))
    elif uv >= 8:
        alerts.append(Alert("warning", "uv", f"☀️ Very high UV ({uv:.0f})", "Hat, sunnies, SPF50+, reapply every 2 hours."))
    elif uv >= 6:
        alerts.append(Alert("caution", "uv", f"🧴 High UV ({uv:.0f})", "Sun protection needed."))
    elif uv >= 3:
        alerts.append(Alert("info", "uv", f"🧢 UV {uv:.0f}: sun protection recommended", "UV 3+ is the SunSmart threshold."))

    feels = max(_vals(hr.get("apparent_temperature")) + _vals([cur.get("apparent_temperature")]), default=None)
    if feels is not None:
        if feels >= 40:
            alerts.append(Alert("danger", "heat", f"🥵 Extreme heat (feels {feels:.0f}°C)", "Consider stopping. Drink every hole, find shade, watch for heat exhaustion."))
        elif feels >= 35:
            alerts.append(Alert("warning", "heat", f"🔥 High heat (feels {feels:.0f}°C)", "Drink water every hole and use the cart shade."))
        elif feels >= 32:
            alerts.append(Alert("caution", "heat", f"💧 Hot (feels {feels:.0f}°C)", "Hydrate on every tee."))

    gust = max(_vals(hr.get("wind_gusts_10m")) + _vals([cur.get("wind_gusts_10m")]), default=0.0)
    if gust >= 60:
        alerts.append(Alert("warning", "wind", f"💨 Damaging gusts ({gust:.0f} km/h)", "Watch for falling branches; club up and keep it low."))
    elif gust >= 40:
        alerts.append(Alert("info", "wind", f"🌬️ Gusty ({gust:.0f} km/h)", "Factor the wind into club selection."))
    return sort_alerts(alerts)


def current_conditions(data: dict) -> dict[str, Any]:
    cur = data.get("current") or {}
    return {
        "temp_c": cur.get("temperature_2m"),
        "feels_c": cur.get("apparent_temperature"),
        "wind_kmh": cur.get("wind_speed_10m"),
        "gust_kmh": cur.get("wind_gusts_10m"),
        "wind_dir_deg": cur.get("wind_direction_10m"),
        "uv": cur.get("uv_index"),
    }


def compass(deg: float | None) -> str:
    if deg is None:
        return "-"
    pts = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return pts[int((float(deg) % 360) / 22.5 + 0.5) % 16]


def extract_wind(conditions: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract live wind speed, gust, and compass direction from Open-Meteo current conditions."""
    if not conditions:
        return None
    speed = conditions.get("wind_kmh")
    direction = conditions.get("wind_dir_deg")
    if speed is None or direction is None:
        return None
    gust = conditions.get("gust_kmh")
    return {
        "wind_kmh": max(0.0, float(speed)),
        "gust_kmh": max(0.0, float(gust)) if gust is not None else None,
        "wind_dir_deg": float(direction) % 360.0,
        "compass": compass(direction),
    }


# ---------------------------------------------------------------- BOM warnings
def parse_bom_rss(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    items = []
    for item in root.iter("item"):
        title = " ".join((item.findtext("title") or "").split())
        items.append({"title": title, "link": (item.findtext("link") or "").strip(), "pub_date": (item.findtext("pubDate") or "").strip()})
    return items


_SKIP = re.compile(r"marine|coastal waters|surf|sheep graziers|tsunami|hazardous surf|abnormally high tides|road weather|bushwalk", re.I)


def classify_bom(items: list[dict[str, str]], district: str = "") -> list[Alert]:
    """Map BOM warnings to golf-relevant alerts; district (e.g. 'Sydney Metropolitan') sharpens relevance."""
    district = district.strip().lower()
    out: list[Alert] = []
    for it in items:
        title = it["title"]
        low = title.lower()
        if _SKIP.search(low):
            continue
        if "cancellation" in low or "cancelled" in low:
            out.append(Alert("info", "bom", f"BOM: {title}", link=it.get("link", "")))
            continue
        if "thunderstorm" in low:
            if not district:
                level, note = "warning", "Check whether it covers your course."
            elif district in low:
                level, note = "danger", "Your district is named. Be ready to stop play."
            else:
                level, note = "caution", "Elsewhere in the state."
            out.append(Alert(level, "bom", f"BOM: {title}", note, it.get("link", "")))
        elif "severe weather" in low or "heatwave" in low or "fire weather" in low:
            level = "warning" if (not district or district in low or "heatwave" in low) else "caution"
            out.append(Alert(level, "bom", f"BOM: {title}", link=it.get("link", "")))
        elif "flood" in low or "wind" in low or "frost" in low:
            out.append(Alert("info", "bom", f"BOM: {title}", link=it.get("link", "")))
    return sort_alerts(out)


# ---------------------------------------------------------------- Lightning timer
def lightning_status(last_ts: float | None, now: float, window_s: int = LIGHTNING_WINDOW_S) -> tuple[bool, int]:
    """(stop_play, seconds_remaining). Every new thunder/lightning tap restarts the 30-minute clock."""
    if last_ts is None:
        return False, 0
    remaining = int(round(float(last_ts) + window_s - float(now)))
    return (remaining > 0, max(0, remaining))


def format_countdown(seconds: int) -> str:
    m, s = divmod(max(0, int(seconds)), 60)
    return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------- Pro Shop alert
def normalise_phone(raw: str) -> str:
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    return ("+" + digits) if raw.startswith("+") else digits


def pro_shop_message(hole: int | None, course_name: str = "", when: str = "") -> str:
    where = f"Hole {hole}" if hole else "the course"
    msg = f"Lightning/thunder spotted near {where} — requesting course check"
    if course_name:
        msg += f" ({course_name})"
    if when:
        msg += f" at {when}"
    return msg + "."


def tel_link(phone: str) -> str:
    p = normalise_phone(phone)
    return f"tel:{p}" if p else ""


def sms_link(phone: str, body: str) -> str:
    """`sms:NUMBER?&body=` is the form that opens pre-filled on both iOS and Android."""
    p = normalise_phone(phone)
    return f"sms:{p}?&body={urllib.parse.quote(body, safe='')}" if p else ""
