"""Rusty's Caddy: Streamlit UI. All logic lives in the tested `caddy` engine package."""
from __future__ import annotations

import copy
import os
import time
from pathlib import Path

import streamlit as st

from caddy import clubs as C
from caddy import fines as F
from caddy import formats as G
from caddy import settlement as S
from caddy import weather as W
from caddy.models import N_HOLES, Course, Hole, Player, new_round
from caddy.storage import Store

DATA_DIR = Path(os.environ.get("RUSTY_CADDY_DATA") or Path(__file__).with_name("data"))

st.set_page_config(page_title="Rusty's Caddy", page_icon="⛳", layout="wide")

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


def cb_wolf_pick(hole: int, key: str) -> None:
    val = ss[key]
    ss.round.wolf_picks[hole] = "" if val == "🐺 Lone Wolf" else val
    save_round()


def cb_finish() -> None:
    ss.round.finished_at = time.time()
    save_round()


def cb_new_round() -> None:
    old = ss.round
    if old.scores or old.team_scores or old.fines:
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
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        if stop:
            st.error(f"⚡ **STOP PLAY: SEEK SHELTER.** All clear in **{W.format_countdown(remaining)}** (resets on every new strike/thunder).")
        elif r.lightning_last:
            st.success("✅ 30 minutes since the last thunder/lightning. All clear (check the sky and club siren).")
        else:
            st.caption("If you hear thunder, you're within striking distance. Tap below to start the 30-minute timer.")
    with c2:
        st.button("⚡ Heard Thunder / Saw Lightning", on_click=cb_thunder, type="primary", key="btn_thunder", width="stretch")
    with c3:
        phone = W.normalise_phone(cfg.pro_shop_phone)
        if phone:
            msg = W.pro_shop_message(r.current_hole, r.course.name, time.strftime("%H:%M"))
            st.link_button("📞 Call Pro Shop", W.tel_link(phone), width="stretch")
            st.link_button("💬 SMS Pro Shop", W.sms_link(phone, msg), width="stretch")
        else:
            st.caption("📞 Save the Pro Shop number in ⚙️ Setup for one-tap alerts.")
    if stop:
        with st.expander("False alarm?"):
            if st.checkbox("I'm sure it was a false alarm", key="chk_false_alarm"):
                st.button("Clear lightning timer", on_click=cb_clear_lightning, key="btn_clear_lightning")


def weather_banner() -> dict | None:
    alerts, conditions = gather_weather()
    with st.container(border=True):
        if conditions:
            st.caption(
                f"🌡️ {conditions['temp_c']}°C (feels {conditions['feels_c']}°C) · 💨 {conditions['wind_kmh']} km/h "
                f"{W.compass(conditions['wind_dir_deg'])}, gusts {conditions['gust_kmh']} · ☀️ UV {conditions['uv']}"
                + (f" · {cfg.location_name}" if cfg.location_name else "")
            )
        elif cfg.latitude is None:
            st.caption("📍 Set your course location in ⚙️ Setup for live storm, heat and UV alerts.")
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


# ------------------------------------------------------------------ header
st.title("⛳ Rusty's Mental Caddy")
st.markdown("##### Clear the head. Play the percentages.")
conditions = weather_banner()

tab_card, tab_caddy, tab_games, tab_fines, tab_setup = st.tabs(
    ["📝 Scorecard", "🧠 Caddy", "🏆 Games", "💸 Fines & 19th", "⚙️ Setup"]
)

# ------------------------------------------------------------------ scorecard
with tab_card:
    h = rnd.current_hole
    hole = rnd.course.hole(h)
    team = rnd.is_team_scoring
    n1, n2, n3 = st.columns([1, 2, 1])
    n1.button("◀ Prev", on_click=cb_hole, args=(-1,), disabled=h <= 1, key="btn_prev", width="stretch")
    n2.markdown(f"### Hole {h} · Par {hole.par} · SI {hole.stroke_index}")
    n3.button("Next ▶", on_click=cb_hole, args=(1,), disabled=h >= N_HOLES, key="btn_next", width="stretch")

    if "wolf" in rnd.games:
        order = list(rnd.games["wolf"].get("order") or rnd.player_names)
        if len(order) == 4:
            wolf_name = G.wolf_for_hole(order, h)
            opts = ["🐺 Lone Wolf"] + [p for p in order if p != wolf_name]
            cur = rnd.wolf_picks.get(h)
            idx = 0 if cur in (None, "") else (opts.index(cur) if cur in opts else 0)
            key = f"wolf_{rnd.round_id}_{h}"
            st.radio(f"🐺 {wolf_name} is the Wolf. Partner:", opts, index=idx if h in rnd.wolf_picks else None,
                     key=key, horizontal=True, on_change=cb_wolf_pick, args=(h, key))

    entities = rnd.scoring_entities()
    if not entities:
        st.warning("Set up Ambrose teams in 🏆 Games first." if team else "Add players in ⚙️ Setup.")
    for i, name in enumerate(entities):
        c = st.columns([3, 1, 1.2, 1, 1, 1])
        has = rnd.has_score(name, h, team)
        val = rnd.gross(name, h, team) if has else None
        strokes_txt = "—" if not has else ("P/U" if val is None else str(val))
        sub = ""
        if has and val is not None:
            diff = val - hole.par
            sub = {-3: "albatross", -2: "eagle", -1: "birdie", 0: "par", 1: "bogey", 2: "double"}.get(diff, f"+{diff}" if diff > 0 else str(diff))
        tot, played, _ = rnd.total_gross(name, team)
        c[0].markdown(f"**{name}**  \n<small>{tot} thru {played}</small>", unsafe_allow_html=True)
        c[1].button("−", key=f"minus_{i}", on_click=cb_adjust, args=(name, -1, team), width="stretch")
        c[2].markdown(f"<div style='text-align:center;font-size:1.6em;font-weight:700'>{strokes_txt}</div>"
                      f"<div style='text-align:center;font-size:0.8em'>{sub}</div>", unsafe_allow_html=True)
        c[3].button("+", key=f"plus_{i}", on_click=cb_adjust, args=(name, 1, team), width="stretch")
        c[4].button("P/U", key=f"pu_{i}", on_click=cb_pickup, args=(name, team), help="Pick up / no return", width="stretch")
        c[5].button("✖", key=f"clr_{i}", on_click=cb_clear, args=(name, team), help="Clear this hole", width="stretch")

    done = len(rnd.holes_complete(team=team))
    st.progress(done / N_HOLES, text=f"{done}/{N_HOLES} holes complete")
    if rnd.is_complete():
        if rnd.finished_at:
            st.success("🏁 Round finished. Head to 💸 Fines & 19th to settle up.")
        else:
            st.button("🏁 Finish round", on_click=cb_finish, type="primary", key="btn_finish")

    if not team and rnd.players:
        me = rnd.players[0]
        blow = 0
        from caddy.handicap import playing_handicap, strokes_on_hole

        ph = playing_handicap(me.handicap)
        for hh in range(1, N_HOLES + 1):
            if rnd.has_score(me.name, hh):
                g = rnd.gross(me.name, hh)
                hl = rnd.course.hole(hh)
                if g is None or g - strokes_on_hole(ph, hl.stroke_index) >= hl.par + 2:
                    blow += 1
        st.caption(f"💥 {me.name}'s blow-up holes (net double or worse): {blow}")

    st.button("🔄 Start new round (archives this one)", on_click=cb_new_round, key="btn_new_round")

# ------------------------------------------------------------------ caddy
with tab_caddy:
    hole = rnd.course.hole(rnd.current_hole)
    st.subheader(f"Hole {rnd.current_hole} | Par {hole.par}")
    a1, a2, a3 = st.columns(3)
    distance = a1.number_input("Distance to pin (m)", 10, 650, 150 if hole.par == 3 else 380, step=5, key="cad_dist")
    default_wind = int(round(conditions["wind_kmh"])) if conditions and conditions.get("wind_kmh") is not None else 10
    wind = a2.slider("Wind (km/h)", 0, 60, min(60, default_wind), key="cad_wind")
    wind_dir = a3.selectbox("Wind relative to shot", C.WIND_DIRECTIONS, key="cad_wdir")
    b1, b2, b3 = st.columns(3)
    elevation = b1.number_input("Elevation change (m, uphill +)", -40, 40, 0, key="cad_elev")
    pressure = b2.slider("Mental pressure (1-10)", 1, 10, 5, key="cad_press")
    miss_idx = C.MISSES.index(cfg.typical_miss) if cfg.typical_miss in C.MISSES else 0
    miss = b3.selectbox("Typical miss", C.MISSES, index=miss_idx, key="cad_miss")

    adv = C.get_caddy_advice(cfg.clubs, hole.par, distance, wind, wind_dir, pressure, miss, elevation)
    m1, m2 = st.columns(2)
    with m1:
        st.metric("Recommended club", adv.club, f"plays like {adv.plays_like_m} m (carry {adv.carry_m} m)", delta_color="off")
        st.info(adv.strategy + (f"  \n{adv.aim_tip}" if adv.aim_tip else ""))
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
                    tplayers = tc2.multiselect("Players", names, [p for p in prev["players"] if p in names],
                                               max_selections=None if key == "ambrose" else 2, key=f"g_{key}_tp{t}")
                    new_teams.append({"name": tname.strip() or f"Team {t + 1}", "players": tplayers})
                old["teams"] = new_teams
                old["stake"] = st.number_input("Stake per player ($)", 0.0, 500.0, float(old.get("stake", 5.0)), 1.0, key=f"g_{key}_stake")
                if key == "best_ball":
                    old["mode"] = st.radio("Scoring", ["stableford", "stroke"], index=0 if old.get("mode", "stableford") == "stableford" else 1, horizontal=True, key="g_bb_mode")
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
    catalog = F.normalise_catalog(cfg.fines_catalog)
    who = st.pills("Who copped it?", rnd.player_names, selection_mode="single", key="fine_who")
    cols = st.columns(min(len(catalog), 3) or 1)
    for i, ft in enumerate(catalog):
        cols[i % len(cols)].button(
            F.describe(ft), key=f"fine_{ft['key']}", disabled=not who,
            on_click=cb_fine, args=(who, ft) if who else None, width="stretch",
        )
    if rnd.fines:
        last = rnd.fines[-1]
        st.button(f"↩️ Undo last ({last['player']}: {last['label']})", on_click=cb_undo_fine, key="btn_undo_fine")
        st.dataframe(
            [{"Hole": f.get("hole") or "-", "Player": f["player"], "Fine": f"{f.get('emoji', '')} {f['label']}",
              "Amount": "Shout" if f.get("shout") and not f["amount_cents"] else S.money(f["amount_cents"])} for f in reversed(rnd.fines)],
            hide_index=True, width="stretch",
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
    with st.form("setup_form"):
        st.markdown("**Players** (defaults for new rounds)")
        players_df = st.data_editor(
            [{"name": p.name, "handicap": p.handicap} for p in cfg.players],
            num_rows="dynamic", key="ed_players", width="stretch",
        )
        st.markdown("**Course**")
        course_name = st.text_input("Course name", cfg.course.name)
        holes_df = st.data_editor(
            [{"hole": hh.number, "par": hh.par, "stroke_index": hh.stroke_index} for hh in cfg.course.holes],
            disabled=["hole"], key="ed_holes", width="stretch",
        )
        st.markdown("**Club distances (carry, m)**")
        clubs_df = st.data_editor([{"club": c[0], "carry_m": c[1]} for c in cfg.clubs], num_rows="dynamic", key="ed_clubs")
        miss = st.selectbox("Typical miss", C.MISSES, index=C.MISSES.index(cfg.typical_miss) if cfg.typical_miss in C.MISSES else 0)
        st.markdown("**Fines & Shouts catalog**")
        fines_df = st.data_editor(F.normalise_catalog(cfg.fines_catalog), num_rows="dynamic", key="ed_fines",
                                  column_config={"key": None}, width="stretch")
        fines_mode = st.radio("Fine money goes to", ["kitty", "split"], index=0 if cfg.fines_mode == "kitty" else 1,
                              format_func=lambda m: "🍺 Kitty (bar tab)" if m == "kitty" else "Split among the other players", horizontal=True)
        st.markdown("**Safety & weather**")
        phone = st.text_input("Pro Shop phone", cfg.pro_shop_phone, placeholder="e.g. 02 9555 1234")
        sc1, sc2, sc3 = st.columns(3)
        loc_name = sc1.text_input("Location label", cfg.location_name)
        lat = sc2.number_input("Latitude", -90.0, 90.0, float(cfg.latitude) if cfg.latitude is not None else 0.0, format="%.4f")
        lon = sc3.number_input("Longitude", -180.0, 180.0, float(cfg.longitude) if cfg.longitude is not None else 0.0, format="%.4f")
        bc1, bc2 = st.columns(2)
        states = list(W.BOM_FEEDS)
        bom_state = bc1.selectbox("BOM warnings state", states, index=states.index(cfg.bom_state) if cfg.bom_state in states else 0,
                                  format_func=lambda s: W.BOM_FEEDS[s][1])
        district = bc2.text_input("BOM district keyword (optional)", cfg.bom_district, placeholder="e.g. Metropolitan, Hunter")
        apply_now = st.checkbox("Also apply players & course to the current round", value=not (rnd.scores or rnd.team_scores))
        submitted = st.form_submit_button("💾 Save setup", type="primary")

    if submitted:
        def rows(df):
            return df.to_dict("records") if hasattr(df, "to_dict") else list(df)

        new_players = [Player(str(r["name"]).strip(), float(r.get("handicap") or 0)) for r in rows(players_df) if str(r.get("name") or "").strip()]
        new_course = Course(course_name.strip() or "My Club",
                            [Hole(int(r["hole"]), int(r["par"]), int(r["stroke_index"])) for r in rows(holes_df)])
        errs = new_course.validate()
        if len({p.name for p in new_players}) != len(new_players):
            errs.append("Player names must be unique.")
        if errs:
            for e in errs:
                st.error(e)
        else:
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
