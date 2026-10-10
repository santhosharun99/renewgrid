# RenewGrid - local-first monitoring, forecasting and fault detection for solar and wind plants

A self-hosted monitoring, forecasting and fault-detection platform planned for
commercial solar and wind plants. It is tested and validated on a live
grid-tied rooftop solar installation in Trichy, Tamil Nadu, which is where all
the results below come from. Instead of relying on the vendor's third-party
cloud app, it reads the inverter directly over the local network, keeps every
reading, and builds physics-guided machine-learning models on top of it:
forecasting, outage classification, degradation analysis, and savings
computed from real utility bills.

The guiding principle: the plant owner should own the data. A dedicated
always-on logger writing to self-hosted storage removes the vendor cloud
from the loop entirely; this repository provides everything needed to run
that way.

## Results at a glance

**Forecast accuracy** - rolling-origin backtest over 17 months of held-out
data (daily kWh MAPE, event days excluded):

| Model | MAPE | Significance (Diebold-Mariano) |
|---|---|---|
| Hybrid: pvlib physics + LightGBM residual | **10.31%** | - |
| Calibrated pvlib physics alone | 10.94% | p = 0.044 vs hybrid |
| Persistence (yesterday's profile) | 19.03% | p < 1e-14 |
| Climatology (hour x day-of-year mean) | 19.73% | p < 1e-13 |

**Operational skill** - the deployed forecasting chain replayed against
archived weather forecasts (what the system actually receives in
production), by forecast horizon:

| Lead time | Hybrid MAPE | Physics-only MAPE | P10-P90 coverage (conformal) |
|---|---|---|---|
| 1 day | **11.01%** | 14.41% | 83.9% |
| 3 days | 13.29% | 16.25% | 79.3% |
| 7 days | 18.78% | 23.71% | 88.4% |

The ML residual layer contributes 2.8-4.9 MAPE points under operational
conditions - substantially more than it shows on reanalysis inputs -
because much of its value lies in correcting weather-forecast bias.
Uncertainty bands are calibrated with split-conformal prediction (raw
quantile bands covered only 67% at a nominal 80%; conformal restores
79-88% on held-out data) and widen with forecast horizon.

**Measured economics** - from real TNEB net-metering bills (bidirectional
meter), not estimates: over Rs 56,000 saved across 10 billing cycles (~21
months), a realized value of Rs 6.48 per solar kWh under the telescopic
tariff, ~43% self-consumption, and 38.9% of the Rs 1.5 lakh system cost
recovered - on track for breakeven in about five years.

**Plant health**: no detectable panel degradation over 22 months
(bootstrap 95% CI [-5.79, +3.59] %/yr) and no detectable soiling effect at
this site. 34 anomalous days classified across the record (grid outages,
logger gaps, underperformance), totalling 163 kWh of lost production.

## How it works

```
Inverter (Modbus over WiFi stick)          Solarman daily export (xlsx)
        |  logger.py, 5-min polls                  |  authoritative backfill
        v                                          v
     solar.db  <--------- load_all.py ---------> production.parquet
        |                                          |
        |     Open-Meteo: weather archive/forecast/previous-runs,
        |     air quality, 3x3 neighbouring-cell grid
        v                                          v
   physics.py (pvlib chain, calibrated)  ->  dataset.py (feature frame)
        |                                          |
        v                                          v
  outage_classifier.py                    LightGBM quantile models
  events.csv (kWh + Rs per event)         + conformal calibration
        |                                          |
        +-------------------+----------------------+
                            v
                 api.py (FastAPI)  ->  dashboard/ (React + Vite)
```

- **Physics first.** A calibrated `pvlib` model chain (fitted tilt,
  azimuth, effective capacity, inverter stage, and an eastern-horizon
  shading mask) produces the baseline expectation. LightGBM is trained
  only on the residual, so the ML layer corrects the physics rather than
  replacing it.
- **Two-tier ingestion, self-healing.** The live logger provides the
  real-time stream; the vendor's daily export is merged as the
  authoritative backfill, so any gap in live collection is repaired
  automatically.
- **Honest uncertainty.** All accuracy figures come from rolling-origin
  evaluation (never a random train/test split on time series), significance
  is tested rather than asserted, and prediction intervals are
  conformally calibrated per forecast horizon.
- **Event-aware.** A classifier separates grid outages, inverter faults,
  logger gaps, and underperformance days - using phase-voltage registers
  where available - and each event is priced in kWh and rupees. Anomalous
  days are excluded from model training and evaluation rather than
  learned as if they were weather.

## Dashboard

A React dashboard (localhost) with five views:

- **Live** - real-time power with a weather-reactive animation (clouds,
  rain, and wind driven by current conditions), plus an interactive
  appliance planner showing what current production can run.
- **Forecast** - 7-day probabilistic forecast with an hour slider; the
  scene renders each hour's forecast weather, and P10-P90 bands widen with
  horizon.
- **Savings** - measured savings from actual TNEB bills, per-cycle
  breakdown, realized Rs/kWh, and investment-recovery tracking.
- **Green impact** - CO2 avoided and equivalents.
- **Insights** - statistical soiling verdict (with confidence intervals,
  in plain language) and model-accuracy summary.

## Hardware

| | |
|---|---|
| Array | 3.0 kWp nameplate (fitted effective capacity ~2.78 kWp), tilt ~12 deg, azimuth ~104 deg (ESE) |
| Inverter | UTL 5F3 GT, 5 kW, 3-phase, grid-tied |
| Data logger | Solarman/IGEN LSW-3 WiFi stick, Modbus via `pysolarmanv5` |
| Consumption metering | none installed; the system is consumption-ready (see below) |

### Inverter register map (holding registers, read-only)

| Register | Meaning | Scale |
|---|---|---|
| 3-7 | inverter serial (ASCII) | |
| 60 | energy today | x0.1 kWh |
| 63+64 | lifetime energy (32-bit LE) | x0.1 kWh |
| 70-72 | line-to-line voltage | x0.1 V |
| 73-75 | phase voltage (used to distinguish grid outage from inverter fault) | x0.1 V |
| 76-78 | phase current | x0.1 A |
| 79 | grid frequency | x0.01 Hz |
| 93 | power factor | x0.001 |
| 96 | documented as DC input power, but observed values are inconsistent with that (falls below AC output); treated as unidentified | x0.1 W |
| 109 | AC output power; unreliable in low-light conditions (observed stuck near 2 kW while true output was <200 W), so the API sanity-checks it against the register-60 energy counter | W |
| 201+202 | lifetime energy mirror | x0.1 kWh |
| 88-91, 123, 126, 138, 145, 146 | unidentified; logged raw | |

Safety note: registers in the ~300-500 range hold grid-protection trip
thresholds. This project only ever reads registers; never write to them.

## Getting started

```bash
pip install -r requirements.txt
cd dashboard && npm install && cd ..
```

Data pipeline, in order:

| Step | Script | Output |
|---|---|---|
| 1 | `load_all.py` | vendor xlsx exports in `data/` -> `production.parquet` |
| 2 | `analyse.py` | weather archive -> `weather_all.csv`, daily table -> `daily.csv` |
| 3 | `aq.py` | air quality -> `aq_all.csv` |
| 4 | `fetch_spatial.py` | 3x3 grid instability features -> `spatial.csv` |
| 5 | `clearsky.py` | per-day variability index -> `days.csv` |
| 6 | `outage_classifier.py` | event classification -> `events.csv` (run with `test` for its unit tests) |
| 7 | `calibrate.py` | physics calibration -> `params.json` |
| 8 | `model.py` | quantile models -> `m10/m50/m90.txt` |
| 9 | `backtest.py` | rolling-origin evaluation, baselines, significance tests |
| 10 | `leadtime.py` | per-horizon skill + conformal band calibration |

Serve:

```bash
python api.py                    # FastAPI on :8000
cd dashboard && npm run dev      # dashboard on :5173
```

Live logging runs `logger.py` on any always-on host (Raspberry Pi,
mini-PC, or small VPS with VPN to the LAN); launchd unit files for macOS
are included as a reference installation, with a sun-aware heartbeat that
alerts on stale data only during daylight.

Shared modules: `quality.py` (data-quality gates used by every analysis),
`physics.py` (the pvlib chain and plant constants), `dataset.py` (the
modeling feature frame). Centralizing these exists for a reason: early
versions of two analysis scripts disagreed about which days were outages
because each carried its own inline thresholds.

## Consumption metering: not installed, but supported

The plant measures production only; nothing in this project fabricates
consumption data. Historical consumption and savings are reconstructed
exactly from TNEB net-metering bills (import/export units per cycle
combined with measured generation). For live consumption, an integration
contract is implemented and tested: any energy meter (Shelly EM,
PZEM-004T + ESP32, or a smart meter) that POSTs readings to
`/consumption/reading` activates measured-usage analytics automatically -
per-cycle tariff-slab position, live house load, and the self-consumption
split - with no code changes.

## Design principles

1. **Physics carries the structure; ML corrects it.** Site geometry,
   shading, and inverter behaviour do not transfer between plants, so no
   pretraining on other plants' data.
2. **Sequence models are the wrong shape for this problem.** Tomorrow's
   output is a function of tomorrow's weather, not yesterday's power, so
   no LSTM/CNN forecasters. (A sky-camera nowcasting layer, where sequence
   information is genuinely causal, is the planned exception.)
3. **Rolling-origin evaluation only.** Random train/test splits leak
   future information in time series.
4. **One model, attribution via SHAP.** Per-factor models mislead under
   confounding: at this site, temperature correlates positively with
   output (via sunshine) while its causal effect is negative.
5. **Alerts must identify their cause.** Grid outage, inverter fault,
   logger gap, and underperformance are distinguished explicitly; where
   the data cannot support the distinction (the historical export lacks
   phase voltage), the classifier reports the ambiguity instead of
   guessing.
6. **Surprisingly strong results get a confound hunt before a
   celebration.** This policy produced the negative results below.

## How this compares to existing options

- **Versus the vendor app** (the default for this hardware): the app shows
  production graphs on a third-party cloud and nothing else. It has no
  forecast, no outage-vs-fault diagnosis, no tariff-aware economics, and
  the data lives on servers the owner does not control. Everything in
  this repository is additive to that baseline and runs locally.
- **Versus standard forecasting baselines**: the hybrid model roughly
  halves the error of persistence (19.0% -> 10.3%) and climatology
  (19.7% -> 10.3%), with statistical significance at p < 1e-13. These are
  the baselines most commercial "smart solar" forecasts quietly resemble.
- **Versus physics alone**: a fully calibrated pvlib chain is a strong
  model - the ML layer's edge over it is modest on clean reanalysis
  inputs (10.9% -> 10.3%) but grows to 3-5 MAPE points in the operational
  setting, where it also corrects weather-forecast bias. Both numbers are
  reported; most published comparisons report only the flattering one.
- **Versus published research systems**: day-ahead site-level MAPE of
  ~11% and conformally calibrated intervals are in line with
  research-grade results reported for national PV fleets with far richer
  data (e.g. satellite-driven systems benchmarked on 6,400+ Swiss plants).
  This system reaches that tier for one rooftop with free public weather
  data and a Rs 0 sensing budget beyond the stock inverter.

## Known limitations - and the planned fix for each

| Limitation | Impact | Planned fix |
|---|---|---|
| No intraday nowcasting: inside the 0-2 h window, NWP-based forecasts cannot see individual clouds | Live-day predictions lag fast sky changes | Satellite optical-flow nowcasting from INSAT via MOSDAC (access requested); sky camera for the 0-30 min range |
| Collection depends on a host that may sleep | Gaps in the live stream (always repaired later by the export backfill, so no permanent data loss) | Dedicated always-on logger device writing to self-hosted storage |
| No live consumption measurement | Self-consumption split known per billing cycle, not per hour | Any household energy meter activates the already-implemented `/consumption/reading` contract |
| Historical bills priced at the current tariff | Pre-May-2026 savings slightly approximate | Period-aware tariff tables once older rate schedules are added |
| Two inverter registers misreport (96, 109 in low light) | Live power needs sanity-gating (implemented) | Register identification against vendor documentation; energy counter remains the ground truth |
| Single site | Findings (shading, soiling, tariff) are site-specific by design | The methodology, not the fitted model, is the transferable artifact |

## Negative results

Two early findings survived initial analysis, looked publishable, and were
wrong. Both are retained because they document the failure modes this
project is designed to avoid.

1. **"Panels degrading 4.2%/yr."** An artifact of a naive kWh-per-GHI
   metric applied across a cloudier second year. With clear-day gating and
   a bootstrap over the performance-ratio trend, the 95% CI is
   [-5.79, +3.59] %/yr: no detectable degradation.
2. **"Cumulative dust (PM10) drives soiling."** PM10 accumulation appeared
   significant in isolation (p = 0.042) but collapsed after controlling
   for days-since-rain (p = 0.827). Rain both washes panels and scrubs
   particulates from the air - a textbook confound. The separate question
   of same-day aerosol attenuation is real but small (~7% of SHAP
   attribution).

An early headline result ("physics 20.6% MAPE improved to 12.5% by ML")
was likewise retracted after the evaluation was found to include
logger-gap and outage days; all numbers above postdate that correction.

