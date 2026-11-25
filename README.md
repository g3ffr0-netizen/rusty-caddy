# ⛳ Rusty's Mental Caddy

Streamlit on-course companion: editable Pre-Shot Routine / Swing Cue card, Open-Meteo wind plays-like club advice,
high-contrast one-handed scoring & round stats (GIR/fairways/putts/penalties), local JSON course-data loader,
Social Club Mode games, Fines & Shouts with a 19th-hole settlement, and free weather and lightning safety alerts.

```powershell
py -3.14 -m pip install -r requirements.txt
py -3.14 -m streamlit run caddy_app.py          # phone on same Wi-Fi: http://<pc-ip>:8501
py -3.14 -m unittest discover -s tests -t . -v  # engine + headless UI tests
```

## Layout
| Path | What |
|---|---|
| `caddy/models.py` | Course / Hole (par, SI, distance, bearing) / Player / Round (scores, hole stats, swing cue) / Settings |
| `caddy/courses.py` | Local JSON course-data loader, validator, exporter, and settings applier |
| `caddy/stats.py` | Round stats summary (GIR, fairways, putts, penalties, blow-ups) + running Fines & Shouts tally |
| `caddy/storage.py` | Atomic save on **every tap** + `.bak` fallback; finished rounds archived to `data/rounds/` |
| `caddy/clubs.py` | Club-distance table, Open-Meteo vector wind plays-like adjuster (head/tail/cross + gusts), caddy advice |
| `caddy/handicap.py` | Strokes per hole (incl. plus handicaps), Stableford points |
| `caddy/formats.py` | Stableford, Ambrose/Scramble, Skins, 2-Ball Best Ball, Wolf, Nassau (integer cents, zero-sum) |
| `caddy/fines.py` | Editable Fines & Shouts catalog + ledger (kitty or split) |
| `caddy/settlement.py` | Combined balances → **fewest payments** (exact subset DP ≤14 parties) + share text |
| `caddy/weather.py` | Open-Meteo wind/storm/heat/UV, BOM state warnings RSS, 30-min lightning timer, Pro Shop call/SMS links |
| `courses/` | Bundled local JSON course templates (`course_template.json`, `coastal_links_sample.json`) |
| `.streamlit/config.toml` | High-contrast sunlight-readable light theme |
| `caddy_app.py` | Streamlit UI only. No game/stats/course/wind logic lives here |

The `caddy/` package has no Streamlit imports, so it can be wrapped as an offline PWA later.

## Data sources & safety
- **Open-Meteo** (free, no key): live wind speed/gusts/direction (feeds the plays-like adjuster), forecast CAPE,
  thunderstorm weather codes, UV, feels-like. Its `lightning_potential` is null for Australia, so storm risk comes
  from weather codes + CAPE.
- **BOM** warning RSS feeds (`https://www.bom.gov.au/fwo/IDZ000xx.warnings_<state>.xml`): free for
  personal, non-commercial use only.
- No free source provides live lightning strikes, so the **⚡ Heard Thunder** button starts a manual 30-minute
  all-clear timer that restarts on every tap.
- **Not a safety device.** The club siren, BOM warnings and your own judgement always come first.

Local data lives in `data/` (git-ignored). Override with the `RUSTY_CADDY_DATA` env var.
