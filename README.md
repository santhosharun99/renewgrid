# solar — physics-guided ML for one rooftop PV plant

Forecasting, fault detection and attribution for a single residential
grid-tied array in Trichy, Tamil Nadu. Physics first: `pvlib` **is** the
pretrained model; LightGBM learns only the residual.

## Plant

| | |
|---|---|
| Array | 3.0 kWp nameplate (fitted effective size ≈ 2.67 kWp), tilt ~10°, azimuth ~105° (ESE, near-flat) |
| Inverter | UTL 5F3 GT, 5 kW, 3-phase, grid-tied |
| Location | 10.7905 N, 78.7047 E, Asia/Kolkata |
| Logger | Solarman/IGEN LSW-3 stick at `192.168.29.238:8899`, logger serial `2787693150`, `mb_slave_id=1` |
| CT clamp | **none** — consumption/grid-import data does not exist; only production is real. Do not add consumption/savings/battery features. |
| Shading | house to the east: production step at ~07:30, costs ~0.3–0.5 kWh/day |

### Register map (holding registers, READ-ONLY)

| reg | meaning | scale |
|---|---|---|
| 3–7 | inverter serial (ASCII) | |
| 60 | yield today | ×0.1 kWh |
| 63+64 | total yield, 32-bit little-endian | ×0.1 kWh |
| 70–72 | line-to-line voltage | ×0.1 V |
| 73–75 | **phase voltage** (outage-vs-fault discriminator) | ×0.1 V |
| 76–78 | phase current | ×0.1 A |
| 79 | frequency | ×0.01 Hz |
| 93 | power factor | ×0.001 |
| 96 | DC input power | ×0.1 W |
| 109 | AC output power | W |
| 201+202 | total yield mirror | ×0.1 kWh |
| 90, 91 | identical/lockstep; no per-string separation available | raw |
| 88/89, 123, 126, 138, 145, 146 | unidentified, logged raw | raw |

**NEVER write to Modbus registers.** Registers ~300–500 hold grid-protection
trip thresholds. Read-only, always.

## Live logging

- `logger.py` polls the stick every 5 min into `solar.db` table `readings`.
- Runs via launchd: `com.solar.logger.plist` (KeepAlive + RunAtLoad,
  logs to `logger_stdout.log`/`logger_stderr.log`):
  `cp com.solar.logger.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.solar.logger.plist`
- `heartbeat.py` (via `com.solar.heartbeat.plist`, every 30 min) alerts if
  `max(ts)` is >30 min stale **while the sun is up** — the stick is powered
  by the inverter and is legitimately dark at night; a naive staleness check
  would false-alarm all night.
- ⚠️ **This MacBook sleeps.** The logger must move to an always-on device
  (Raspberry Pi / old phone running Termux / small VPS + VPN home). Stopgap:
  `caffeinate -is` in a terminal, or
  `sudo pmset -a sleep 0` while on mains power. Until then expect gaps.

## Pipeline — run in this order

| step | script | writes |
|---|---|---|
| 1 | `load_all.py` | Solarman app xlsx exports in `data/` → `production.parquet` |
| 2 | `analyse.py` | fetches Open-Meteo archive → `weather_all.csv`, daily eff table → `daily.csv` |
| 3 | `aq.py` | Open-Meteo air quality → `aq_all.csv` |
| 4 | `clearsky.py` | per-day variability index → `days.csv` |
| 5 | `outage_classifier.py` | event classification → `events.csv` (`test` arg runs its unit tests) |
| 6 | `calibrate.py` | fits tilt/azim/pdc0/shading/temp-model → `params.json` |
| 7 | `pr.py`, `clear.py` | performance ratio, degradation CI → `pr_daily.csv` |
| 8 | `model.py` | single-split diagnostic + quantile boosters → `m10/m50/m90.txt` |
| 9 | `backtest.py` | rolling-origin eval, baselines, DM tests → `calibration.png` |
| 10 | `shap_attribution.py` | factor attribution → `shap_attribution.csv` |
| — | `export_forecast.py`, `api.py`, `dashboard/` | forecast JSON + web UI (blocked on validated classifier — now unblocked) |

Shared modules (import, never re-implement):
- `quality.py` — `usable_days` (≥130 samples), `clear_days` (vi < q40,
  drops ≤ 2), `exclude_events` (events.csv). analyse.py and model.py once
  disagreed about which days were outages purely because each had its own
  inline gates.
- `physics.py` — the pvlib chain + plant constants; reads `params.json`.
- `dataset.py` — hourly modeling frame + feature list.

## Headline numbers

<!-- NUMBERS -->

## Standing decisions — do not re-litigate

1. **Physics first.** `pvlib` is the pretrained model. Do not pretrain on
   other plants' public datasets — geometry/shading/inverter don't transfer.
2. **LightGBM on the residual** (actual − pvlib), never on raw power
   (exception: the SHAP attribution model, which is explanatory, not a forecaster).
3. **No CNN/LSTM/ConvLSTM.** Tomorrow's output is a function of tomorrow's
   weather, not yesterday's power. Deep sequence models are wrong-shaped here.
   (Possible future exception: sky-camera nowcasting.)
4. **Rolling-origin backtests only.** Never `train_test_split` on time series.
5. **One model with all features; attribution via SHAP.** Never
   one-model-per-factor — temperature correlates +0.34 with power via
   sunshine while its true causal effect is negative.
6. **Every alert must distinguish plant fault / grid outage / logger gap**
   before shipping (see `outage_classifier.py`; the historical app export has
   no phase voltage, so the outage-vs-fault split there is honestly
   `outage_or_fault`, not a guess).
7. **Never commit API keys.** `nsrdb.py` reads `NREL_KEY`/`NREL_EMAIL` from
   the environment and is gitignored.

Also: never report R² on data including night-time zeros; distrust any
result where RMSE < MAE (impossible — indicates a bug); if a result looks
surprisingly strong, hunt the confound first.

## Killed hypotheses — and why (do not resurrect without new controls)

1. **"Panels degrading 4.2%/yr"** — artifact of a naive kWh/GHI metric on a
   cloudier second year. With clear-day gating and bootstrap over the PR
   trend the 95% CI is **[−5.79, +3.59] %/yr** → no detectable degradation.
   The metric, not the panels, was degrading.
2. **"Cumulative dust/PM10 drives soiling"** — PM10 looked significant alone
   (p = 0.042), but after controlling for days-since-rain it collapsed to
   p = 0.827. Rain both washes panels *and* scrubs PM out of the air:
   classic confound. Dead. (The separate *attenuation* question — does
   today's aerosol dim today's output — is answered by SHAP in
   `shap_attribution.py`.)

These two entries are the most valuable content in this repo: both were
confident, plausible, and wrong.
