# solar - physics-guided ML for one rooftop PV plant

Forecasting, fault detection and attribution for a single residential
grid-tied array in Trichy, Tamil Nadu. Physics first: `pvlib` **is** the
pretrained model; LightGBM learns only the residual.

## Plant

| | |
|---|---|
| Array | 3.0 kWp nameplate (fitted effective size ≈ 2.67 kWp), tilt ~10°, azimuth ~105° (ESE, near-flat) |
| Inverter | UTL 5F3 GT, 5 kW, 3-phase, grid-tied |
| Location | 10.79 N, 78.70 E, Asia/Kolkata |
| Logger | Solarman/IGEN LSW-3 stick at `192.168.29.238:8899`, logger serial `2787693150`, `mb_slave_id=1` |
| CT clamp | **none** - consumption/grid-import data does not exist; only production is real. Do not add consumption/savings/battery features. |
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
| 96 | DC input power (per map - but observed values fall BELOW AC output through the afternoon, so this is NOT total DC power; do not trust until identified) | ×0.1 W |
| 109 | AC output power - UNRELIABLE in low sun: observed stuck near 2 kW while true output was <200 W (2026-07-10 afternoon, confirmed against cloud export + yield counter + phase currents). api.py sanity-gates it against the reg-60 counter slope | W |
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
  `max(ts)` is >30 min stale **while the sun is up** - the stick is powered
  by the inverter and is legitimately dark at night; a naive staleness check
  would false-alarm all night.
- **Two-tier ingestion, self-healing by design.** The live logger provides
  the real-time stream; the daily Solarman export is the authoritative
  backfill. `load_all.py` merges each new export and permanently fills any
  gap in the live stream (missing samples, restarts), so the historical
  record repairs itself with no manual intervention.
- **Deployment target: any always-on host** (Raspberry Pi, mini-PC, or a
  small VPS with a VPN back to the LAN). The logger is pure Python +
  `pysolarmanv5` and runs anywhere; the launchd units above are the macOS
  reference install.
- **The end goal: own your data, fully.** A small dedicated device logging
  every reading straight into your own cloud closes the loop - continuous
  collection with zero gaps and zero dependence on the vendor's servers.
  The panels are yours, the roof is yours, and with this the data is yours
  too.

## Pipeline - run in this order

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
| - | `export_forecast.py`, `api.py`, `dashboard/` | forecast JSON + web UI (blocked on validated classifier - now unblocked) |

Shared modules (import, never re-implement):
- `quality.py` - `usable_days` (≥130 samples), `clear_days` (vi < q40,
  drops ≤ 2), `exclude_events` (events.csv). analyse.py and model.py once
  disagreed about which days were outages purely because each had its own
  inline gates.
- `physics.py` - the pvlib chain + plant constants; reads `params.json`.
- `dataset.py` - hourly modeling frame + feature list.

## Headline numbers (2026-07-11)

Rolling-origin backtest (17 months, event days excluded, reanalysis
weather inputs, daily kWh MAPE):

| model | MAPE | DM test vs hybrid |
|---|---|---|
| **hybrid (pvlib + LGBM residual, l1, AQ + spatial 3x3 features)** | **10.31%** | - |
| pvlib alone (calibrated) | 10.94% | p = 0.044 - significant |
| persistence (yesterday's profile) | 19.03% | p ~ 1e-15 |
| climatology (hour x doy train mean) | 19.73% | p ~ 1e-14 |

**Operational (served-chain) skill** - replayed against archived weather
*forecasts* (previous-runs API), i.e. what the system actually serves:

| lead | hybrid MAPE | pvlib MAPE | band coverage (conformal, holdout) |
|---|---|---|---|
| day-1 | **11.01%** | 14.41% | 83.9% |
| day-3 | 13.29% | 16.25% | 79.3% |
| day-7 | 18.78% | 23.71% | 88.4% |

- The ML layer earns 2.8-4.9 MAPE points in the operational setting
  (correcting forecast-weather bias) - far more than the ~0.5 points it
  shows on reanalysis inputs. Train/serve skew matters; measure both.
- **⚠️ Superseded claim:** the early "pvlib 20.56% → hybrid 12.51%" was a
  dirty-data artifact (gap/outage days were scored). Kept as a caution.
- Probabilistic: raw P10-P90 undercovers (67%); **split-conformal (CQR)
  restores 79-88%**, bands widen with horizon (leadtime_calibration.json).
- Clear-day R² (top-5% VI days): **0.9016** - unchanged by full physics
  calibration (fitted tilt 11.8, azim 104, pdc0 2782 W, 7-deg eastern shade
  horizon, pvwatts inverter). Ceiling set by weather-data noise.
- Degradation: bootstrap 95% CI **[-5.79, +3.59] %/yr** → none detectable.
- Events (677 days): 20 outage-or-fault, 10 logger gaps, 4 underperformance;
  163 kWh lost. Logger gaps are lost *data*, not production.
- **Measured economics (real TNEB net-metering bills, 9 cycles):**
  ₹51,317 saved (₹58.3k incl. current-cycle estimate), realized value
  **₹6.48/kWh** (trailing ₹7.56), actual usage ~919 units/cycle,
  self-consumption 44.8%, **38.9% of the ₹1.5L system recovered** in
  ~20 months → breakeven ~5 years total.

## Consumption-ready (no CT clamp installed - by design, not omission)

The plant measures only production; nothing here fakes consumption data.
But the integration contract exists and is tested (consumption.py):
any energy meter (Shelly EM, PZEM-004T + ESP32, smart meter) POSTing
`{"load_w": ...}` to `POST /consumption/reading` activates, with zero
refactoring: measured bi-monthly usage per TNEB cycle (>=80% coverage),
real telescopic-slab position and savings, live house load, and the
self-consumption vs export split. Until then /savings labels every
figure as computed from *assumed* usage.

## Standing decisions - do not re-litigate

1. **Physics first.** `pvlib` is the pretrained model. Do not pretrain on
   other plants' public datasets - geometry/shading/inverter don't transfer.
2. **LightGBM on the residual** (actual − pvlib), never on raw power
   (exception: the SHAP attribution model, which is explanatory, not a forecaster).
3. **No CNN/LSTM/ConvLSTM.** Tomorrow's output is a function of tomorrow's
   weather, not yesterday's power. Deep sequence models are wrong-shaped here.
   (Possible future exception: sky-camera nowcasting.)
4. **Rolling-origin backtests only.** Never `train_test_split` on time series.
5. **One model with all features; attribution via SHAP.** Never
   one-model-per-factor - temperature correlates +0.34 with power via
   sunshine while its true causal effect is negative.
6. **Every alert must distinguish plant fault / grid outage / logger gap**
   before shipping (see `outage_classifier.py`; the historical app export has
   no phase voltage, so the outage-vs-fault split there is honestly
   `outage_or_fault`, not a guess).
7. **Never commit API keys.** `nsrdb.py` reads `NREL_KEY`/`NREL_EMAIL` from
   the environment and is gitignored.

Also: never report R² on data including night-time zeros; distrust any
result where RMSE < MAE (impossible - indicates a bug); if a result looks
surprisingly strong, hunt the confound first.

## Killed hypotheses - and why (do not resurrect without new controls)

1. **"Panels degrading 4.2%/yr"** - artifact of a naive kWh/GHI metric on a
   cloudier second year. With clear-day gating and bootstrap over the PR
   trend the 95% CI is **[−5.79, +3.59] %/yr** → no detectable degradation.
   The metric, not the panels, was degrading.
2. **"Cumulative dust/PM10 drives soiling"** - PM10 looked significant alone
   (p = 0.042), but after controlling for days-since-rain it collapsed to
   p = 0.827. Rain both washes panels *and* scrubs PM out of the air:
   classic confound. Dead. (The separate *attenuation* question - does
   today's aerosol dim today's output - is answered by SHAP in
   `shap_attribution.py`.)

These two entries are the most valuable content in this repo: both were
confident, plausible, and wrong.
