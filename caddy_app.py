"""Rusty's Caddy: Streamlit UI. All logic lives in the tested `caddy` engine package."""
from __future__ import annotations

import copy
import html
import os
import time
from pathlib import Path

import streamlit as st

from caddy import clubs as C
from caddy import courses as CR
from caddy import fines as F
from caddy import formats as G
from caddy import rangefinder as RF
from caddy import settlement as S
from caddy import stats as ST
from caddy import weather as W
from caddy.models import (
    DEFAULT_SWING_CUE,
    N_HOLES,
    Course,
    Hole,
    Player,
    new_round,
    normalise_swing_cue,
)
from caddy.storage import Store

DATA_DIR = Path(os.environ.get("RUSTY_CADDY_DATA") or Path(__file__).with_name("data"))
USER_COURSES_DIR = DATA_DIR / "courses"

st.set_page_config(page_title="Rusty's Caddy", page_icon="⛳", layout="wide")

# High-contrast, sunlight-readable, thumb-friendly CSS for on-course one-handed use.
SUNLIGHT_CSS = """
<style>
  html, body, [data-testid="stAppViewContainer"] {
    background-color: #FFFFFF;
    color: #0B1410;
  }
  .block-container {
    padding-top: 1rem;
    padding-bottom: 3rem;
    max-width: 960px;
  }
  /* Bigger, high-contrast tap targets for thumb use in sunlight */
  .stButton > button,
  .stLinkButton > a,
  .stDownloadButton > button {
    min-height: 3.35rem;
    font-size: 1.08rem;
    font-weight: 700;
    border-radius: 12px;
    border: 2px solid #0B1410;
    touch-action: manipulation;
    letter-spacing: 0.01em;
  }
  .stButton > button[kind="primary"] {
    background-color: #0B6636;
    border-color: #063D20;
    color: #FFFFFF;
  }
  .stButton > button[kind="primary"]:hover {
    background-color: #084E29;
  }
  .stButton > button[kind="secondary"] {
    background-color: #F4F7F4;
    color: #0B1410;
    border-color: #1F2937;
  }
  .stButton > button[kind="secondary"]:hover {
    background-color: #E2ECE4;
  }
  .stButton > button:disabled {
    opacity: 0.45;
  }
  /* High-contrast tabs with larger tap height */
  .stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    border-bottom: 2px solid #1F2937;
  }
  .stTabs [data-baseweb="tab"] {
    min-height: 3.1rem;
    padding: 0.55rem 0.9rem;
    font-weight: 800;
    font-size: 1.02rem;
    color: #0B1410;
    background-color: #EDF3EE;
    border-radius: 10px 10px 0 0;
    border: 2px solid transparent;
  }
  .stTabs [aria-selected="true"] {
    background-color: #0B6636 !important;
    color: #FFFFFF !important;
    border-color: #063D20 !important;
  }
  /* Swing Cue hero card (sunlight high-contrast dark green + pure white + gold accent) */
  .swing-cue-card {
    background: #083D22;
    color: #FFFFFF;
    border: 3px solid #042213;
    border-radius: 16px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.14);
  }
  .swing-cue-label {
    font-size: 0.82rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #FDE047;
    margin-bottom: 0.25rem;
  }
  .swing-cue-text {
    font-size: 1.85rem;
    font-weight: 900;
    line-height: 1.2;
    color: #FFFFFF;
    letter-spacing: 0.02em;
  }
  /* Score readout & Hole header banner */
  .hole-banner {
    background: #0B1410;
    color: #FFFFFF;
    border-radius: 12px;
    padding: 0.55rem 0.75rem;
    text-align: center;
    font-weight: 800;
  }
  .hole-banner-title {
    font-size: 1.35rem;
    line-height: 1.15;
  }
  .hole-banner-sub {
    font-size: 0.92rem;
    color: #FDE047;
    font-weight: 700;
  }
  .score-box {
    background: #FFFFFF;
    border: 2px solid #0B1410;
    border-radius: 12px;
    padding: 0.25rem 0.4rem;
    text-align: center;
    min-height: 3.35rem;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  .score-num {
    font-size: 1.75rem;
    font-weight: 900;
    line-height: 1.05;
    color: #0B1410;
  }
  .score-sub {
    font-size: 0.78rem;
    font-weight: 700;
    color: #1F2937;
    text-transform: uppercase;
  }
  /* Round stats & Fines tally cards */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 8px;
    margin: 0.4rem 0 0.6rem 0;
  }
  .stat-tile {
    background: #F4F7F4;
    border: 2px solid #0B1410;
    border-radius: 12px;
    padding: 0.55rem 0.65rem;
    text-align: center;
  }
  .stat-tile.fines-tile {
    background: #FEF3C7;
    border-color: #92400E;
  }
  .stat-label {
    font-size: 0.76rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #1F2937;
  }
  .stat-val {
    font-size: 1.25rem;
    font-weight: 900;
    color: #0B1410;
    line-height: 1.2;
  }
  .stat-sub {
    font-size: 0.78rem;
    font-weight: 700;
    color: #374151;
  }
  /* Wind plays-like callout */
  .wind-pill {
    background: #E0F2FE;
    border: 2px solid #0369A1;
    border-radius: 12px;
    padding: 0.6rem 0.85rem;
    color: #0C4A6E;
    font-weight: 700;
    margin-bottom: 0.6rem;
  }
  /* Metric cards readability */
  [data-testid="stMetric"] {
    background: #F4F7F4;
    border: 2px solid #0B1410;
    border-radius: 12px;
    padding: 0.65rem 0.85rem;
  }
  [data-testid="stMetricLabel"] {
    color: #1F2937 !important;
    font-weight: 800 !important;
  }
  [data-testid="stMetricValue"] {
    color: #0B1410 !important;
    font-weight: 900 !important;
  }
</style>
"""
st.markdown(SUNLIGHT_CSS, unsafe_allow_html=True)

store = Store(DATA_DIR)
ss = st.session_state
if "settings" not in ss:
    ss.settings = store.load_settings()
if "round" not in ss:
    ss.round = store.load_round() or new_round(ss.settings)
    store.save_round(ss.round)


def save_round() -> None:
    store.save_round(ss.round)


def save_settings() -> None:
    store.save_settings(ss.settings)


rnd = ss.round
cfg = ss.settings


# ------------------------------------------------------------------ callbacks
def cb_adjust(name: str, delta: int, team: bool) -> None:
    ss.round.adjust_score(name, ss.round.current_hole, delta, team)
    save_round()


def cb_pickup(name: str, team: bool) -> None:
    ss.round.set_score(name, ss.round.current_hole, None, team)
    save_round()


def cb_clear(name: str, team: bool) -> None:
    ss.round.clear_score(name, ss.round.current_hole, team)
    save_round()


def cb_hole(delta: int) -> None:
    ss.round.go_to_hole(ss.round.current_hole + delta)
    save_round()


def cb_toggle_fir(name: str, value: bool) -> None:
    ss.round.toggle_fir(name, ss.round.current_hole, value)
    save_round()


def cb_toggle_gir(name: str, value: bool) -> None:
    ss.round.toggle_gir(name, ss.round.current_hole, value)
    save_round()


def cb_adjust_putts(name: str, delta: int) -> None:
    ss.round.adjust_putts(name, ss.round.current_hole, delta)
    save_round()


def cb_adjust_penalties(name: str, delta: int) -> None:
    ss.round.adjust_penalties(name, ss.round.current_hole, delta)
    save_round()


def cb_save_cue_inline(input_key: str) -> None:
    cue = normalise_swing_cue(ss.get(input_key))
    ss.settings.swing_cue = cue
    ss.round.swing_cue = cue
    save_settings()
    save_round()


def cb_wolf_pick(hole: int, key: str) -> None:
    val = ss[key]
    ss.round.wolf_picks[hole] = "" if val == "🐺 Lone Wolf" else val
    save_round()


def cb_finish() -> None:
    ss.round.finished_at = time.time()
    save_round()


def cb_new_round() -> None:
    old = ss.round
    if old.scores or old.team_scores or old.fines or old.hole_stats:
        store.archive_round(old)
    ss.round = new_round(ss.settings, games=old.games)
    save_round()


def cb_thunder() -> None:
    ss.round.lightning_last = time.time()
    save_round()


def cb_clear_lightning() -> None:
    ss.round.lightning_last = None
    save_round()


def cb_fine(player: str, fine_type: dict) -> None:
    F.add_fine(ss.round, player, fine_type, ss.round.current_hole)
    save_round()


def cb_undo_fine() -> None:
    F.undo_last(ss.round)
    save_round()


# ------------------------------------------------------------------ weather (cached, fail-soft)
@st.cache_data(ttl=600, show_spinner=False)
def cached_open_meteo(lat: float, lon: float) -> dict | None:
    try:
        return W.fetch_open_meteo(lat, lon, timeout=8)
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def cached_bom(state: str) -> str | None:
    try:
        return W.fetch_bom_xml(state, timeout=8)
    except Exception:
        return None


def gather_weather() -> tuple[list[W.Alert], dict | None]:
    alerts: list[W.Alert] = []
    conditions = None
    if cfg.latitude is not None and cfg.longitude is not None:
        data = cached_open_meteo(round(cfg.latitude, 3), round(cfg.longitude, 3))
        if data:
            alerts += W.evaluate_open_meteo(data)
            conditions = W.current_conditions(data)
        else:
            alerts.append(W.Alert("info", "system", "Open-Meteo forecast unavailable (offline?)"))
    xml = cached_bom(cfg.bom_state) if cfg.bom_state in W.BOM_FEEDS else None
    if xml:
        try:
            alerts += W.classify_bom(W.parse_bom_rss(xml), cfg.bom_district)
        except Exception:
            alerts.append(W.Alert("info", "system", "Couldn't read the BOM warnings feed."))
    elif cfg.bom_state in W.BOM_FEEDS:
        alerts.append(W.Alert("info", "system", "BOM warnings unavailable (offline?)"))
    return W.sort_alerts(alerts), conditions


ALERT_FN = {"danger": st.error, "warning": st.warning, "caution": st.warning, "info": st.info}


@st.fragment(run_every="15s")
def lightning_panel() -> None:
    r = ss.round
    stop, remaining = W.lightning_status(r.lightning_last, time.time())
    c1, c2, c3 = st.columns([2, 1.3, 1.1])
    with c1:
        if stop:
            st.error(f"⚡ **STOP PLAY: SEEK SHELTER.** All clear in **{W.format_countdown(remaining)}** (resets on every new strike/thunder).")
        elif r.lightning_last:
            st.success("✅ 30 minutes since the last thunder/lightning. All clear (check the sky and club siren).")
        else:
            st.caption("If you hear thunder, you're within striking distance. Tap to start the 30-minute timer.")
    with c2:
        st.button("⚡ Heard Thunder", on_click=cb_thunder, type="primary", key="btn_thunder", width="stretch")
    with c3:
        phone = W.normalise_phone(cfg.pro_shop_phone or r.course.pro_shop_phone)
        if phone:
            msg = W.pro_shop_message(r.current_hole, r.course.name, time.strftime("%H:%M"))
            st.link_button("📞 Call Pro Shop", W.tel_link(phone), width="stretch")
            st.link_button("💬 SMS Pro Shop", W.sms_link(phone, msg), width="stretch")
        else:
            st.caption("📞 Add Pro Shop in ⚙️ Setup or load a course JSON.")
    if stop:
        with st.expander("False alarm?"):
            if st.checkbox("I'm sure it was a false alarm", key="chk_false_alarm"):
                st.button("Clear lightning timer", on_click=cb_clear_lightning, key="btn_clear_lightning")


def weather_banner() -> dict | None:
    alerts, conditions = gather_weather()
    with st.container(border=True):
        if conditions:
            st.markdown(
                f"**🌡️ {conditions['temp_c']}°C** (feels {conditions['feels_c']}°C) · "
                f"**💨 {conditions['wind_kmh']} km/h {W.compass(conditions['wind_dir_deg'])}** "
                f"(gusts {conditions['gust_kmh']}) · **☀️ UV {conditions['uv']}**"
                + (f" · {cfg.location_name}" if cfg.location_name else "")
            )
        elif cfg.latitude is None:
            st.caption("📍 Set your course location or load a course JSON in ⚙️ Setup for live Open-Meteo wind, storm, heat and UV.")
        top = [a for a in alerts if a.level != "info"][:3]
        for a in top:
            ALERT_FN[a.level](f"**{a.title}**" + (f": {a.message}" if a.message else "") + (f" [details]({a.link})" if a.link else ""))
        rest = [a for a in alerts if a not in top]
        if rest:
            with st.expander(f"{len(rest)} more weather notice(s)"):
                for a in rest:
                    st.write(f"- {a.title}" + (f": {a.message}" if a.message else ""))
        lightning_panel()
        st.caption("Not a safety device. The club siren, BOM warnings and your own judgement come first.")
    return conditions


def render_round_stats_card(r, player_name: str | None = None) -> None:
    """Render the sunlight-readable Round Stats summary (GIR/FIR/putts/penalties + Fines & Shouts)."""
    s = ST.round_stats_summary(r, player_name)
    score_val = f"{s.gross_total} ({ST.format_to_par(s.to_par)})" if s.par_played else "—"
    score_sub = f"thru {s.holes_scored} · {s.blow_ups} blow-up{'s' if s.blow_ups != 1 else ''}"
    fir_val = ST.format_ratio(s.fir_hit, s.fir_tracked)
    gir_val = ST.format_ratio(s.gir_hit, s.gir_tracked)
    putts_val = str(s.total_putts) if s.putts_tracked else "—"
    putts_sub = f"{s.putts_per_hole:.2f}/hole · {s.three_putts}x 3-putt" if s.putts_tracked else "tap below to log"
    pen_val = str(s.total_penalties)
    fines_val = S.money(s.fines_total_cents)
    shouts_txt = f"{s.shouts_count} shout{'s' if s.shouts_count != 1 else ''}"
    fines_sub = f"{s.fines_count} fine{'s' if s.fines_count != 1 else ''} · {shouts_txt}"

    header = f"📊 Round Stats — {html.escape(s.player)}" if s.player else "📊 Round Stats"
    st.markdown(f"**{header}**")
    st.markdown(
        f"""
        <div class="stats-grid">
          <div class="stat-tile">
            <div class="stat-label">Score</div>
            <div class="stat-val">{html.escape(score_val)}</div>
            <div class="stat-sub">{html.escape(score_sub)}</div>
          </div>
          <div class="stat-tile">
            <div class="stat-label">GIR</div>
            <div class="stat-val">{html.escape(gir_val)}</div>
            <div class="stat-sub">Greens in reg</div>
          </div>
          <div class="stat-tile">
            <div class="stat-label">Fairways</div>
            <div class="stat-val">{html.escape(fir_val)}</div>
            <div class="stat-sub">Par 4/5 only</div>
          </div>
          <div class="stat-tile">
            <div class="stat-label">Putts</div>
            <div class="stat-val">{html.escape(putts_val)}</div>
            <div class="stat-sub">{html.escape(putts_sub)}</div>
          </div>
          <div class="stat-tile">
            <div class="stat-label">Penalties</div>
            <div class="stat-val">{html.escape(pen_val)}</div>
            <div class="stat-sub">Penalty strokes</div>
          </div>
          <div class="stat-tile fines-tile">
            <div class="stat-label">Fines &amp; Shouts</div>
            <div class="stat-val">{html.escape(fines_val)}</div>
            <div class="stat-sub">{html.escape(fines_sub)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if s.shouts:
        shout_names = ", ".join(f"{sh['player']} (H{sh['hole']})" if sh.get("hole") else sh["player"] for sh in s.shouts)
        st.info(f"🍻 **Shouts on the board:** {shout_names}")


# ------------------------------------------------------------------ header
st.title("⛳ Rusty's Mental Caddy")
course_meta = f"{rnd.course.name} · Par {rnd.course.par} · {rnd.course.total_distance_m} m"
if rnd.course.tee:
    course_meta += f" ({rnd.course.tee})"
st.markdown(f"**{course_meta}** — Clear the head. Play the percentages.")
conditions = weather_banner()
live_wind = W.extract_wind(conditions)

tab_card, tab_caddy, tab_games, tab_fines, tab_setup = st.tabs(
    ["📝 Scorecard", "🧠 Caddy", "🏆 Games", "💸 Fines & 19th", "⚙️ Setup"]
)

# ------------------------------------------------------------------ scorecard
with tab_card:
    h = rnd.current_hole
    hole = rnd.course.hole(h)
    team = rnd.is_team_scoring

    n1, n2, n3 = st.columns([1.1, 2.2, 1.1])
    n1.button("◀ Prev", on_click=cb_hole, args=(-1,), disabled=h <= 1, key="btn_prev", width="stretch")
    bearing_txt = f" · {C.nearest_compass_point(hole.bearing_deg)}" if hole.bearing_deg is not None else ""
    n2.markdown(
        f"<div class='hole-banner'>"
        f"<div class='hole-banner-title'>Hole {h} · Par {hole.par}</div>"
        f"<div class='hole-banner-sub'>{hole.effective_distance_m} m · SI {hole.stroke_index}{bearing_txt}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    n3.button("Next ▶", on_click=cb_hole, args=(1,), disabled=h >= N_HOLES, key="btn_next", width="stretch")

    if "wolf" in rnd.games:
        order = list(rnd.games["wolf"].get("order") or rnd.player_names)
        if len(order) == 4:
            wolf_name = G.wolf_for_hole(order, h)
            opts = ["🐺 Lone Wolf"] + [p for p in order if p != wolf_name]
            cur = rnd.wolf_picks.get(h)
            idx = 0 if cur in (None, "") else (opts.index(cur) if cur in opts else 0)
            key = f"wolf_{rnd.round_id}_{h}"
            st.radio(
                f"🐺 {wolf_name} is the Wolf. Partner:",
                opts,
                index=idx if h in rnd.wolf_picks else None,
                key=key,
                horizontal=True,
                on_change=cb_wolf_pick,
                args=(h, key),
            )

    entities = rnd.scoring_entities()
    if not entities:
        st.warning("Set up Ambrose teams in 🏆 Games first." if team else "Add players in ⚙️ Setup.")
    for i, name in enumerate(entities):
        c = st.columns([2.2, 1.2, 1.3, 1.2, 1.0, 0.9])
        has = rnd.has_score(name, h, team)
        val = rnd.gross(name, h, team) if has else None
        strokes_txt = "—" if not has else ("P/U" if val is None else str(val))
        sub = ""
        if has and val is not None:
            diff = val - hole.par
            sub = {-3: "albatross", -2: "eagle", -1: "birdie", 0: "par", 1: "bogey", 2: "double"}.get(
                diff, f"+{diff}" if diff > 0 else str(diff)
            )
        tot, played, _ = rnd.total_gross(name, team)
        c[0].markdown(f"**{name}**  \n{tot} thru {played}")
        c[1].button("−", key=f"minus_{i}", on_click=cb_adjust, args=(name, -1, team), width="stretch")
        c[2].markdown(
            f"<div class='score-box'><div class='score-num'>{strokes_txt}</div>"
            f"<div class='score-sub'>{sub or '&nbsp;'}</div></div>",
            unsafe_allow_html=True,
        )
        c[3].button("+", key=f"plus_{i}", on_click=cb_adjust, args=(name, 1, team), type="primary", width="stretch")
        c[4].button("P/U", key=f"pu_{i}", on_click=cb_pickup, args=(name, team), help="Pick up / no return", width="stretch")
        c[5].button("✖", key=f"clr_{i}", on_click=cb_clear, args=(name, team), help="Clear this hole", width="stretch")

    # One-tap Hole Stats (FIR / GIR / Putts / Penalties)
    stats_player: str | None = None
    if not team and rnd.players:
        if len(rnd.players) == 1:
            stats_player = rnd.players[0].name
        else:
            stats_player = st.selectbox("Track hole stats for", rnd.player_names, key="stats_player_sel")
        hst = rnd.get_hole_stats(stats_player, h)
        with st.container(border=True):
            st.markdown(f"**🎯 Hole {h} Stats — {stats_player}**")
            st1, st2 = st.columns(2)
            with st1:
                if hole.par >= 4:
                    f1, f2 = st.columns(2)
                    f1.button(
                        "✅ FW Hit" if hst["fir"] is True else "FW Hit",
                        key="btn_fir_hit",
                        type="primary" if hst["fir"] is True else "secondary",
                        on_click=cb_toggle_fir,
                        args=(stats_player, True),
                        width="stretch",
                    )
                    f2.button(
                        "❌ FW Miss" if hst["fir"] is False else "FW Miss",
                        key="btn_fir_miss",
                        type="primary" if hst["fir"] is False else "secondary",
                        on_click=cb_toggle_fir,
                        args=(stats_player, False),
                        width="stretch",
                    )
                else:
                    st.info("Par 3 — Fairway N/A")
            with st2:
                g1, g2 = st.columns(2)
                g1.button(
                    "✅ GIR" if hst["gir"] is True else "GIR",
                    key="btn_gir_hit",
                    type="primary" if hst["gir"] is True else "secondary",
                    on_click=cb_toggle_gir,
                    args=(stats_player, True),
                    width="stretch",
                )
                g2.button(
                    "❌ GIR Miss" if hst["gir"] is False else "GIR Miss",
                    key="btn_gir_miss",
                    type="primary" if hst["gir"] is False else "secondary",
                    on_click=cb_toggle_gir,
                    args=(stats_player, False),
                    width="stretch",
                )

            p1, p2 = st.columns(2)
            with p1:
                pm, pv, pp = st.columns([1, 1.2, 1])
                pm.button("−", key="btn_putts_minus", on_click=cb_adjust_putts, args=(stats_player, -1), width="stretch")
                putts_disp = "—" if hst["putts"] is None else str(hst["putts"])
                pv.markdown(
                    f"<div class='score-box'><div class='score-num'>{putts_disp}</div>"
                    f"<div class='score-sub'>PUTTS</div></div>",
                    unsafe_allow_html=True,
                )
                pp.button("+", key="btn_putts_plus", on_click=cb_adjust_putts, args=(stats_player, 1), width="stretch")
            with p2:
                xm, xv, xp = st.columns([1, 1.2, 1])
                xm.button("−", key="btn_pen_minus", on_click=cb_adjust_penalties, args=(stats_player, -1), width="stretch")
                xv.markdown(
                    f"<div class='score-box'><div class='score-num'>{hst['penalties']}</div>"
                    f"<div class='score-sub'>PENALTIES</div></div>",
                    unsafe_allow_html=True,
                )
                xp.button("+", key="btn_pen_plus", on_click=cb_adjust_penalties, args=(stats_player, 1), width="stretch")

    done = len(rnd.holes_complete(team=team))
    st.progress(done / N_HOLES, text=f"{done}/{N_HOLES} holes complete")
    if rnd.is_complete():
        if rnd.finished_at:
            st.success("🏁 Round finished. Head to 💸 Fines & 19th to settle up.")
        else:
            st.button("🏁 Finish round", on_click=cb_finish, type="primary", key="btn_finish", width="stretch")

    # Round Stats Summary (GIR / Fairways / Putts / Penalties + Running Fines & Shouts)
    render_round_stats_card(rnd, stats_player)

    st.button("🔄 Start new round (archives this one)", on_click=cb_new_round, key="btn_new_round", width="stretch")

# ------------------------------------------------------------------ caddy
with tab_caddy:
    # 1. Editable Pre-Shot Routine / Swing Cue card right at the top of the Caddy tab
    active_cue = normalise_swing_cue(rnd.swing_cue or cfg.swing_cue)
    st.markdown(
        f"""
        <div class="swing-cue-card">
          <div class="swing-cue-label">🎯 Pre-Shot Routine · Swing Cue</div>
          <div class="swing-cue-text">{html.escape(active_cue)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("✏️ Edit swing cue"):
        ec1, ec2 = st.columns([3, 1.2])
        ec1.text_input(
            "Pre-Shot Routine / Swing Cue",
            value=active_cue,
            key="caddy_swing_cue_input",
            label_visibility="collapsed",
            placeholder=DEFAULT_SWING_CUE,
        )
        ec2.button(
            "💾 Save cue",
            key="btn_save_cue_inline",
            type="primary",
            on_click=cb_save_cue_inline,
            args=("caddy_swing_cue_input",),
            width="stretch",
        )

    hole = rnd.course.hole(rnd.current_hole)
    default_dist = hole.effective_distance_m
    default_compass = C.nearest_compass_point(hole.bearing_deg)
    hole_sig = (rnd.round_id, rnd.course.name, rnd.current_hole, default_dist, hole.bearing_deg)
    if ss.get("_cad_hole_sig") != hole_sig:
        ss._cad_hole_sig = hole_sig
        ss.cad_dist = default_dist
        ss.cad_shot_bearing = default_compass
    elif "cad_dist" not in ss:
        ss.cad_dist = default_dist
    if "cad_shot_bearing" not in ss:
        ss.cad_shot_bearing = default_compass

    bearing_badge = f" · Bearing {default_compass}" if hole.bearing_deg is not None else ""
    st.subheader(f"Hole {rnd.current_hole} · Par {hole.par} · {default_dist} m · SI {hole.stroke_index}{bearing_badge}")

    # Open-Meteo Wind Plays-Like adjuster
    use_live_wind = False
    shot_bearing_deg: float | None = None
    wind_dir_deg: float | None = None
    gust_kmh: float | None = None
    wind_dir_manual = "None"

    if live_wind:
        gust_txt = f" · Gusts {live_wind['gust_kmh']:.0f} km/h" if live_wind["gust_kmh"] is not None else ""
        st.markdown(
            f"<div class='wind-pill'>💨 Live Open-Meteo Wind: "
            f"{live_wind['wind_kmh']:.0f} km/h from {live_wind['compass']} ({live_wind['wind_dir_deg']:.0f}°)"
            f"{gust_txt}</div>",
            unsafe_allow_html=True,
        )
        wind_mode = st.radio(
            "Wind plays-like source",
            ["Live Open-Meteo wind", "Manual wind"],
            horizontal=True,
            key="cad_wind_mode",
        )
        use_live_wind = wind_mode == "Live Open-Meteo wind"
    else:
        st.caption("💨 Set a location or load a local course JSON in ⚙️ Setup to auto-adjust plays-like distance from live Open-Meteo wind.")

    a1, a2, a3 = st.columns(3)
    distance = a1.number_input("Distance to pin (m)", min_value=10, max_value=650, step=5, key="cad_dist")

    if use_live_wind and live_wind:
        compass_opts = list(C.COMPASS_BEARINGS)
        shot_dir_label = a2.selectbox(
            "Shot direction (towards pin)",
            compass_opts,
            key="cad_shot_bearing",
            help="Auto-filled from course hole bearing when available.",
        )
        shot_bearing_deg = C.COMPASS_BEARINGS[shot_dir_label]
        wind_kmh = live_wind["wind_kmh"]
        wind_dir_deg = live_wind["wind_dir_deg"]
        gust_kmh = live_wind["gust_kmh"]
        a3.metric("Live wind", f"{wind_kmh:.0f} km/h", f"from {live_wind['compass']}", delta_color="off")
    else:
        default_wind = int(round(live_wind["wind_kmh"])) if live_wind else 10
        wind_kmh = float(a2.slider("Wind (km/h)", 0, 60, min(60, default_wind), key="cad_wind"))
        wind_dir_manual = a3.selectbox("Wind relative to shot", C.WIND_DIRECTIONS, key="cad_wdir")

    b1, b2, b3 = st.columns(3)
    elevation = b1.number_input("Elevation change (m, uphill +)", -40, 40, 0, key="cad_elev")
    pressure = b2.slider("Mental pressure (1-10)", 1, 10, 5, key="cad_press")
    miss_idx = C.MISSES.index(cfg.typical_miss) if cfg.typical_miss in C.MISSES else 0
    miss = b3.selectbox("Typical miss", C.MISSES, index=miss_idx, key="cad_miss")

    # Lie / Turf & Bag Mode (Full Bag vs 3-Club Challenge)
    c1, c2 = st.columns([1.2, 1.8])
    lie = c1.selectbox("Lie / Turf (Mangrove slopes & tight grass)", list(RF.LIE_CONDITIONS), key="cad_lie")
    bag_mode = c2.radio(
        "Bag mode",
        ["Full Bag", "🏆 3-Club Challenge (3W / 7I / 60°)"],
        horizontal=True,
        key="cad_bag_mode",
    )

    lie_delta_m, lie_tip = RF.LIE_CONDITIONS.get(lie, (0.0, ""))

    # Optional GPS Rangefinder (Front / Middle / Back + Shot Distance Tracker)
    with st.expander("📍 GPS Rangefinder (Front / Middle / Back & Shot Tracker)", expanded=False):
        st.caption(
            "Enter your current GPS & green-center pin (or paste from Google Maps / phone GPS) for Front / Middle / Back "
            "yardages, compass bearing, and Mark-Ball shot measurement."
        )
        base_lat = float(cfg.latitude) if cfg.latitude is not None else -33.2935
        base_lon = float(cfg.longitude) if cfg.longitude is not None else 151.2015
        g1, g2, g3, g4 = st.columns(4)
        p_lat = g1.number_input("Player Lat", value=base_lat - 0.0012, format="%.6f", step=0.0001, key="rf_plat")
        p_lon = g2.number_input("Player Lon", value=base_lon, format="%.6f", step=0.0001, key="rf_plon")
        g_lat = g3.number_input("Green Mid Lat", value=base_lat, format="%.6f", step=0.0001, key="rf_glat")
        g_lon = g4.number_input("Green Mid Lon", value=base_lon, format="%.6f", step=0.0001, key="rf_glon")

        rf_reading = RF.compute_rangefinder_reading(
            RF.GPSFix(lat=p_lat, lon=p_lon, accuracy_m=5.0),
            RF.GreenTargets(middle_lat=g_lat, middle_lon=g_lon),
            wind_kmh=wind_kmh,
            wind_dir=wind_dir_manual,
            wind_dir_deg=wind_dir_deg if use_live_wind else None,
            elevation_override_m=float(elevation),
            lie=lie,
        )
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Front", f"{rf_reading.front_m} m", f"plays {rf_reading.plays_like_front_m} m", delta_color="off")
        r2.metric("Middle", f"{rf_reading.middle_m} m", f"plays {rf_reading.plays_like_middle_m} m", delta_color="off")
        r3.metric("Back", f"{rf_reading.back_m} m", f"plays {rf_reading.plays_like_back_m} m", delta_color="off")
        r4.metric("Bearing", f"{rf_reading.compass} ({rf_reading.bearing_deg:.0f}°)", rf_reading.accuracy_badge, delta_color="off")

        sb1, sb2, sb3 = st.columns(3)
        if sb1.button("📌 Use GPS Middle Distance", key="rf_use_mid"):
            ss.cad_dist = max(10, min(650, rf_reading.middle_m))
            ss.cad_shot_bearing = rf_reading.compass
            st.rerun()
        if sb2.button("⛳ Mark Ball (Start Shot)", key="rf_mark_start"):
            ss.rf_shot_start = RF.GPSFix(lat=p_lat, lon=p_lon, accuracy_m=5.0)
        if sb3.button("📏 Measure Shot", key="rf_measure_shot") and ss.get("rf_shot_start"):
            shot_m = RF.measure_shot_m(ss.rf_shot_start, RF.GPSFix(lat=p_lat, lon=p_lon, accuracy_m=5.0))
            st.success(f"Measured shot distance: **{shot_m} m**")

    if bag_mode.startswith("🏆"):
        tc1, tc2, tc3 = st.columns(3)
        w3_c = tc1.number_input("3 Wood carry (m)", 120, 260, 190, 5, key="tc_3w")
        i7_c = tc2.number_input("7 Iron carry (m)", 80, 190, 135, 5, key="tc_7i")
        w60_c = tc3.number_input("60° Wedge carry (m)", 30, 110, 65, 5, key="tc_60")
        three_bag = [["3 Wood", int(w3_c)], ["7 Iron", int(i7_c)], ["60° Wedge", int(w60_c)]]
        if use_live_wind and live_wind and wind_dir_deg is not None and shot_bearing_deg is not None:
            pl_total = C.wind_plays_like(distance, wind_kmh, wind_dir_deg, shot_bearing_deg, elevation, gust_kmh).plays_like_m + lie_delta_m
        else:
            pl_total = C.plays_like(distance, wind_kmh, wind_dir_manual, elevation) + lie_delta_m
        tc_shot = RF.recommend_three_club_shot(
            pl_total,
            three_clubs=three_bag,
            lie=lie,
            wind_kmh=wind_kmh,
            pressure=pressure,
        )
        m1, m2 = st.columns(2)
        with m1:
            st.metric("3-Club Play", tc_shot.club, f"{tc_shot.shot_type} · plays like {tc_shot.plays_like_m} m", delta_color="off")
            st.info(f"**Feel:** {tc_shot.swing_feel}  \n{tc_shot.strategy}" + (f"  \n🧭 {tc_shot.lie_tip}" if tc_shot.lie_tip else ""))
            st.caption(tc_shot.next_shot)
        with m2:
            st.warning(C.mental_state(pressure))
    else:
        adv = C.get_caddy_advice(
            cfg.clubs,
            hole.par,
            distance,
            wind_kmh=wind_kmh,
            wind_dir=wind_dir_manual,
            pressure=pressure,
            miss=miss,
            elevation_m=elevation + lie_delta_m,
            wind_dir_deg=wind_dir_deg,
            shot_bearing_deg=shot_bearing_deg,
            gust_kmh=gust_kmh,
        )

        m1, m2 = st.columns(2)
        with m1:
            delta_label = f"plays like {adv.plays_like_m} m (carry {adv.carry_m} m)"
            st.metric("Recommended club", adv.club, delta_label, delta_color="off")
            if adv.wind_adjustment:
                wa = adv.wind_adjustment
                sign = "+" if wa.wind_effect_m >= 0 else ""
                gust_part = f" · in gusts: **{round(wa.gust_plays_like_m)} m**" if wa.gust_plays_like_m is not None else ""
                st.markdown(
                    f"💨 **{wa.relative_label}** ({sign}{round(wa.wind_effect_m)} m wind effect{gust_part})"
                )
            st.info(adv.strategy + (f"  \n{adv.aim_tip}" if adv.aim_tip else "") + (f"  \n🧭 {lie_tip}" if lie_tip else ""))
            st.caption(adv.next_shot)
        with m2:
            st.warning(C.mental_state(pressure))

# ------------------------------------------------------------------ games
with tab_games:
    st.subheader("Games for this round")
    names = rnd.player_names
    enabled = st.multiselect(
        "Formats", list(G.GAME_TITLES), default=list(rnd.games), format_func=lambda k: G.GAME_TITLES[k], key="games_enabled"
    )
    new_games: dict[str, dict] = {}
    for key in enabled:
        old = copy.deepcopy(rnd.games.get(key, {}))
        with st.expander(G.GAME_TITLES[key], expanded=key not in rnd.games):
            if key == "stableford":
                old["stake"] = st.number_input("Stake per player ($)", 0.0, 500.0, float(old.get("stake", 5.0)), 1.0, key="g_sf_stake")
                old["allowance"] = st.number_input("Handicap allowance", 0.5, 1.0, float(old.get("allowance", 1.0)), 0.05, key="g_sf_allow")
            elif key == "skins":
                old["value"] = st.number_input("Value per skin, per opponent ($)", 0.0, 100.0, float(old.get("value", 1.0)), 0.5, key="g_sk_val")
                old["use_net"] = st.checkbox("Net skins (handicap strokes)", bool(old.get("use_net", True)), key="g_sk_net")
                old["carryover"] = st.checkbox("Carry over ties", bool(old.get("carryover", True)), key="g_sk_carry")
            elif key in ("ambrose", "best_ball"):
                teams = old.get("teams") or []
                n_teams = st.number_input("Number of teams", 1 if key == "ambrose" else 2, 8, max(len(teams), 2), key=f"g_{key}_n")
                new_teams = []
                for t in range(int(n_teams)):
                    prev = teams[t] if t < len(teams) else {"name": f"Team {t + 1}", "players": []}
                    tc1, tc2 = st.columns([1, 3])
                    tname = tc1.text_input("Name", prev["name"], key=f"g_{key}_tn{t}")
                    tplayers = tc2.multiselect(
                        "Players",
                        names,
                        [p for p in prev["players"] if p in names],
                        max_selections=None if key == "ambrose" else 2,
                        key=f"g_{key}_tp{t}",
                    )
                    new_teams.append({"name": tname.strip() or f"Team {t + 1}", "players": tplayers})
                old["teams"] = new_teams
                old["stake"] = st.number_input("Stake per player ($)", 0.0, 500.0, float(old.get("stake", 5.0)), 1.0, key=f"g_{key}_stake")
                if key == "best_ball":
                    old["mode"] = st.radio(
                        "Scoring",
                        ["stableford", "stroke"],
                        index=0 if old.get("mode", "stableford") == "stableford" else 1,
                        horizontal=True,
                        key="g_bb_mode",
                    )
                    old["allowance"] = st.number_input("Handicap allowance (WHS four-ball: 85%)", 0.5, 1.0, float(old.get("allowance", 0.85)), 0.05, key="g_bb_allow")
                else:
                    if new_teams and new_teams[0]["players"]:
                        st.caption("Team handicap = combined handicaps ÷ (2 × team size). Override the divisor below if your club differs.")
                    old["divisor"] = st.number_input("Divisor (0 = auto)", 0.0, 20.0, float(old.get("divisor") or 0), 1.0, key="g_am_div") or None
            elif key == "wolf":
                old["order"] = st.multiselect("Tee order (exactly 4)", names, [p for p in (old.get("order") or names[:4]) if p in names], max_selections=4, key="g_wolf_order")
                old["value"] = st.number_input("$ per point", 0.0, 100.0, float(old.get("value", 1.0)), 0.5, key="g_wolf_val")
                old["lone_multiplier"] = st.number_input("Lone Wolf multiplier", 1, 5, int(old.get("lone_multiplier", 2)), key="g_wolf_mult")
            elif key == "nassau":
                sides = old.get("sides") or [names[:1], names[1:2]]
                s1, s2 = st.columns(2)
                a = s1.multiselect("Side A", names, [p for p in sides[0] if p in names], max_selections=2, key="g_na_a")
                b = s2.multiselect("Side B", [n for n in names if n not in a], [p for p in sides[1] if p in names and p not in a], max_selections=2, key="g_na_b")
                old["sides"] = [a, b]
                old["stake"] = st.number_input("$ per bet (front / back / overall / presses)", 0.0, 500.0, float(old.get("stake", 5.0)), 1.0, key="g_na_stake")
                old["auto_press"] = st.checkbox("Auto-press when 2 down", bool(old.get("auto_press", True)), key="g_na_press")
        new_games[key] = old
    problems = G.validate_games(new_games)
    for p in problems:
        st.error(p)
    if not problems and new_games != rnd.games:
        rnd.games = new_games
        save_round()

    st.divider()
    st.subheader("Live leaderboards")
    for res in G.compute_all(rnd):
        st.markdown(f"**{res.title}**")
        if res.error:
            st.warning(res.error)
            continue
        if res.standings:
            st.dataframe(res.standings, hide_index=True, width="stretch")
        for n in res.notes:
            st.caption(n)

# ------------------------------------------------------------------ fines & 19th
with tab_fines:
    st.subheader("💸 Fines & Shouts")
    tally = ST.fines_and_shouts_tally(rnd)
    fc1, fc2, fc3 = st.columns(3)
    fc1.metric("Running fines", S.money(tally["total_cents"]))
    fc2.metric("Offences logged", str(tally["count"]))
    fc3.metric("Shouts owed", str(tally["shouts_count"]))

    catalog = F.normalise_catalog(cfg.fines_catalog)
    who = st.pills("Who copped it?", rnd.player_names, selection_mode="single", key="fine_who")
    # 2-column grid for bigger thumb-friendly tap targets on phones
    cols = st.columns(2)
    for i, ft in enumerate(catalog):
        cols[i % 2].button(
            F.describe(ft),
            key=f"fine_{ft['key']}",
            disabled=not who,
            on_click=cb_fine,
            args=(who, ft) if who else None,
            type="primary" if ft.get("shout") else "secondary",
            width="stretch",
        )
    if rnd.fines:
        last = rnd.fines[-1]
        st.button(f"↩️ Undo last ({last['player']}: {last['label']})", on_click=cb_undo_fine, key="btn_undo_fine", width="stretch")
        st.dataframe(
            [
                {
                    "Hole": f.get("hole") or "-",
                    "Player": f["player"],
                    "Fine": f"{f.get('emoji', '')} {f['label']}",
                    "Amount": "Shout" if f.get("shout") and not f["amount_cents"] else S.money(f["amount_cents"]),
                }
                for f in reversed(rnd.fines)
            ],
            hide_index=True,
            width="stretch",
        )

    st.divider()
    st.subheader("🍻 19th-hole settlement")
    settlement = S.settle(rnd, cfg.fines_mode)
    net_rows = [{"Who": k, "Net": S.money(v)} for k, v in sorted(settlement.net.items(), key=lambda kv: -kv[1])]
    st.dataframe(net_rows, hide_index=True, width="stretch")
    for sh in settlement.shouts:
        st.info(f"🍻 **{sh['player']}** shouts the round ({sh['label']}" + (f", hole {sh['hole']})" if sh.get("hole") else ")"))
    if settlement.transfers:
        st.markdown(f"**Fewest payments ({len(settlement.transfers)}):**")
        for t in settlement.transfers:
            st.markdown(f"- {t.payer} → **{t.payee}**: {S.money(t.cents)}")
    else:
        st.success("All square. Nobody owes anything (yet).")
    st.caption("Share to the group chat (tap the copy icon):")
    st.code(S.summary_text(rnd, settlement), language=None)

# ------------------------------------------------------------------ setup
with tab_setup:
    st.subheader("⚙️ Setup")

    # Local Course Data Loader (JSON course templates + upload/export)
    with st.container(border=True):
        st.markdown("**📂 Local Course Loader (JSON)**")
        course_files = CR.list_course_files([CR.DEFAULT_COURSES_DIR, USER_COURSES_DIR])
        lc1, lc2 = st.columns([2.6, 1.4])
        if course_files:
            labels = {str(p): CR.course_label(p) for p in course_files}
            selected_path = lc1.selectbox(
                "Choose a saved course template",
                list(labels.keys()),
                format_func=lambda p: labels[p],
                key="course_loader_select",
            )
            if lc2.button("📥 Load course", key="btn_load_course", type="primary", width="stretch"):
                try:
                    loaded_course = CR.load_course_file(selected_path)
                    CR.apply_course_to_settings(cfg, loaded_course, rnd)
                    save_settings()
                    save_round()
                    st.success(f"Loaded {loaded_course.name} (Par {loaded_course.par}, {loaded_course.total_distance_m} m).")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not load course: {exc}")
        else:
            st.caption("No local JSON course files found in courses/.")

        up_col, dl_col = st.columns([2, 1.2])
        uploaded = up_col.file_uploader("Upload a course JSON file", type=["json"], key="course_upload")
        if uploaded is not None and up_col.button("💾 Save & load uploaded course", key="btn_upload_course", width="stretch"):
            try:
                loaded_course = CR.load_course_json(uploaded.getvalue())
                saved_to = CR.save_course_file(loaded_course, USER_COURSES_DIR)
                CR.apply_course_to_settings(cfg, loaded_course, rnd)
                save_settings()
                save_round()
                st.success(f"Loaded & saved {loaded_course.name} to {saved_to.name}.")
                st.rerun()
            except Exception as exc:
                st.error(f"Invalid course JSON: {exc}")

        dl_col.download_button(
            "⬇️ Export course JSON",
            data=CR.export_course_json(cfg.course),
            file_name="course_template.json",
            mime="application/json",
            key="btn_export_course",
            width="stretch",
        )

    with st.form("setup_form"):
        st.markdown("**🎯 Pre-Shot Routine / Swing Cue**")
        swing_cue_val = st.text_input(
            "Swing cue shown at the top of the Caddy tab",
            value=normalise_swing_cue(cfg.swing_cue),
            key="setup_swing_cue",
            placeholder=DEFAULT_SWING_CUE,
        )

        st.markdown("**Players** (defaults for new rounds)")
        players_df = st.data_editor(
            [{"name": p.name, "handicap": p.handicap} for p in cfg.players],
            num_rows="dynamic",
            key="ed_players",
            width="stretch",
        )
        st.markdown("**Course**")
        cc1, cc2 = st.columns([2, 1])
        course_name = cc1.text_input("Course name", cfg.course.name)
        course_tee = cc2.text_input("Tee", cfg.course.tee, placeholder="e.g. White")
        holes_df = st.data_editor(
            [
                {
                    "hole": hh.number,
                    "par": hh.par,
                    "stroke_index": hh.stroke_index,
                    "distance_m": hh.distance_m or hh.effective_distance_m,
                }
                for hh in cfg.course.holes
            ],
            disabled=["hole"],
            key="ed_holes",
            width="stretch",
        )
        st.markdown("**Club distances (carry, m)**")
        clubs_df = st.data_editor([{"club": c[0], "carry_m": c[1]} for c in cfg.clubs], num_rows="dynamic", key="ed_clubs")
        miss = st.selectbox("Typical miss", C.MISSES, index=C.MISSES.index(cfg.typical_miss) if cfg.typical_miss in C.MISSES else 0)
        st.markdown("**Fines & Shouts catalog**")
        fines_df = st.data_editor(
            F.normalise_catalog(cfg.fines_catalog),
            num_rows="dynamic",
            key="ed_fines",
            column_config={"key": None},
            width="stretch",
        )
        fines_mode = st.radio(
            "Fine money goes to",
            ["kitty", "split"],
            index=0 if cfg.fines_mode == "kitty" else 1,
            format_func=lambda m: "🍺 Kitty (bar tab)" if m == "kitty" else "Split among the other players",
            horizontal=True,
        )
        st.markdown("**Safety & weather**")
        phone = st.text_input("Pro Shop phone", cfg.pro_shop_phone or cfg.course.pro_shop_phone, placeholder="e.g. 02 9555 1234")
        sc1, sc2, sc3 = st.columns(3)
        loc_name = sc1.text_input("Location label", cfg.location_name)
        lat = sc2.number_input("Latitude", -90.0, 90.0, float(cfg.latitude) if cfg.latitude is not None else 0.0, format="%.4f")
        lon = sc3.number_input("Longitude", -180.0, 180.0, float(cfg.longitude) if cfg.longitude is not None else 0.0, format="%.4f")
        bc1, bc2 = st.columns(2)
        states = list(W.BOM_FEEDS)
        bom_state = bc1.selectbox(
            "BOM warnings state",
            states,
            index=states.index(cfg.bom_state) if cfg.bom_state in states else 0,
            format_func=lambda s: W.BOM_FEEDS[s][1],
        )
        district = bc2.text_input("BOM district keyword (optional)", cfg.bom_district, placeholder="e.g. Metropolitan, Hunter")
        apply_now = st.checkbox("Also apply players & course to the current round", value=not (rnd.scores or rnd.team_scores))
        submitted = st.form_submit_button("💾 Save setup", type="primary", width="stretch")

    if submitted:
        def rows(df):
            return df.to_dict("records") if hasattr(df, "to_dict") else list(df)

        existing_bearings = {hh.number: hh.bearing_deg for hh in cfg.course.holes}
        new_players = [
            Player(str(r["name"]).strip(), float(r.get("handicap") or 0))
            for r in rows(players_df)
            if str(r.get("name") or "").strip()
        ]
        new_course = Course(
            name=course_name.strip() or "My Club",
            holes=[
                Hole(
                    int(r["hole"]),
                    int(r["par"]),
                    int(r["stroke_index"]),
                    int(round(float(r.get("distance_m") or 0))),
                    existing_bearings.get(int(r["hole"])),
                )
                for r in rows(holes_df)
            ],
            tee=course_tee.strip(),
            pro_shop_name=cfg.course.pro_shop_name,
            pro_shop_phone=phone.strip(),
            pro_shop_notes=cfg.course.pro_shop_notes,
            location_name=loc_name.strip(),
            latitude=lat if (lat or lon) else None,
            longitude=lon if (lat or lon) else None,
            bom_state=bom_state,
            bom_district=district.strip(),
        )
        errs = new_course.validate()
        if len({p.name for p in new_players}) != len(new_players):
            errs.append("Player names must be unique.")
        if errs:
            for e in errs:
                st.error(e)
        else:
            cue_clean = normalise_swing_cue(swing_cue_val)
            cfg.swing_cue = cue_clean
            rnd.swing_cue = cue_clean
            cfg.players = new_players or cfg.players
            cfg.course = new_course
            cfg.clubs = [[str(r["club"]), int(r["carry_m"])] for r in rows(clubs_df) if r.get("club") and r.get("carry_m")]
            cfg.typical_miss = miss
            cfg.fines_catalog = F.normalise_catalog(rows(fines_df))
            cfg.fines_mode = fines_mode
            cfg.pro_shop_phone = phone.strip()
            cfg.location_name = loc_name.strip()
            cfg.latitude = lat if (lat or lon) else None
            cfg.longitude = lon if (lat or lon) else None
            cfg.bom_state = bom_state
            cfg.bom_district = district.strip()
            save_settings()
            if apply_now:
                rnd.players = copy.deepcopy(cfg.players)
                rnd.course = copy.deepcopy(cfg.course)
            save_round()
            st.success("Saved.")
            st.rerun()

    with st.expander("📍 Find course location"):
        q = st.text_input("Suburb or town", key="geo_q", placeholder="e.g. Rose Bay")
        if q and st.button("Search", key="btn_geo"):
            try:
                ss.geo_results = W.geocode(q)
            except Exception as e:  # network errors only affect this helper
                st.error(f"Search failed: {e}")
        for j, r in enumerate(ss.get("geo_results", [])):
            if st.button(f"Use {r['label']} ({r['latitude']:.3f}, {r['longitude']:.3f})", key=f"geo_use_{j}"):
                cfg.latitude, cfg.longitude, cfg.location_name = r["latitude"], r["longitude"], r["label"]
                save_settings()
                st.rerun()

    archived = store.list_archived()
    if archived:
        st.caption(f"🗂️ {len(archived)} archived round(s) in {store.rounds_dir}")
