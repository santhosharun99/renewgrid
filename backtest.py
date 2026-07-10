"""Rolling-origin backtest: train on all months before M, test on month M.

Point track   : LightGBM residual models with objective l1 and l2 - the
                training objective now matches the reported error metrics
                (previously trained pinball/median but scored MAPE).
Baselines     : pvlib alone, persistence (most recent usable day's hourly
                profile), climatology (hour x day-of-year train-only mean).
Probabilistic : quantile models refit per fold, scored out-of-sample with
                pinball loss, P10-P90 coverage, interval width; calibration
                curve saved to calibration.png.
Significance  : Diebold-Mariano on daily absolute errors, hybrid vs each
                baseline (Newey-West variance, lag 7).

Never train_test_split; never score months with <100 daylight hours.
"""
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy import stats

import dataset

ALPHAS = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
LGB_KW = dict(n_estimators=600, learning_rate=0.03, num_leaves=31,
              subsample=0.8, colsample_bytree=0.8, verbose=-1)


_DONOR_PROFILES = None


def _donor_profiles(donors):
    """day -> {hour: W} for every usable day, built once."""
    global _DONOR_PROFILES
    if _DONOR_PROFILES is None:
        g = donors.groupby(donors.index.date)
        _DONOR_PROFILES = {d: dict(zip(s.index.hour, s.values)) for d, s in g}
    return _DONOR_PROFILES


def persistence_forecast(te, donors):
    """Hourly forecast for test rows: same hour of the most recent usable
    day strictly before each test day."""
    prof = _donor_profiles(donors)
    donor_days = np.array(sorted(prof))
    te_days = pd.Series([ts.date() for ts in te.index], index=te.index)
    out = pd.Series(0.0, index=te.index)
    for day, idx in te_days.groupby(te_days).groups.items():
        prior = donor_days[donor_days < day]
        if not len(prior):
            continue
        p = prof[prior[-1]]
        out[idx] = [p.get(ts.hour, 0.0) for ts in idx]
    return out


def climatology_forecast(tr, te, window=10):
    """hour x day-of-year mean of the training data, doy smoothed with a
    circular +/-window-day mean."""
    m = tr.groupby(["doy", tr.index.hour])["p"].mean().unstack()
    m = m.reindex(range(1, 367))
    ext = pd.concat([m.iloc[-window:], m, m.iloc[:window]])
    sm = ext.rolling(2 * window + 1, center=True, min_periods=1).mean()
    sm = sm.iloc[window:window + 366]
    hour_mean = tr.groupby(tr.index.hour)["p"].mean()
    for h in sm.columns:
        sm[h] = sm[h].fillna(hour_mean.get(h, 0.0))
    flat = sm.stack()
    key = pd.MultiIndex.from_arrays([te.index.dayofyear, te.index.hour])
    pred = flat.reindex(key).fillna(0).to_numpy()
    return pd.Series(pred, index=te.index).clip(lower=0)


def pinball(y, q, alpha):
    d = y - q
    return float(np.mean(np.maximum(alpha * d, (alpha - 1) * d)))


def dm_test(e1, e2, lag=7):
    """Diebold-Mariano on |e1| vs |e2| (daily). Negative DM => model 1
    better. Newey-West long-run variance, two-sided t p-value."""
    d = np.abs(e1) - np.abs(e2)
    n = len(d)
    dbar = d.mean()
    dc = d - dbar
    g0 = float((dc * dc).mean())
    var = g0
    for k in range(1, min(lag, n - 1) + 1):
        gk = float((dc[k:] * dc[:-k]).mean())
        var += 2 * (1 - k / (lag + 1)) * gk
    dm = dbar / np.sqrt(var / n)
    p = 2 * (1 - stats.t.cdf(abs(dm), df=n - 1))
    return dm, p


def daily_kwh(s):
    return s.resample("D").sum().dropna() / 1000


def run(include_aq=True, make_plot=True, label=""):
    j, FEAT = dataset.build(include_aq=include_aq)
    donors = dataset.hourly_actual_all_days()

    months = sorted(set(j.index.to_period("M")))[6:]
    monthly, derr, qpred = [], {}, []
    for mth in months:
        tr = j[j.index.to_period("M") < mth]
        te = j[j.index.to_period("M") == mth]
        if len(te) < 100:
            continue
        preds = {"pvlib": te.pvlib,
                 "persistence": persistence_forecast(te, donors),
                 "climatology": climatology_forecast(tr, te)}
        for name, obj in (("hybrid_l1", "l1"), ("hybrid_l2", "regression")):
            m = lgb.LGBMRegressor(objective=obj, **LGB_KW)
            m.fit(tr[FEAT], tr.target)
            preds[name] = (te.pvlib + m.predict(te[FEAT])).clip(lower=0)

        q = np.empty((len(te), len(ALPHAS)))
        for i, a in enumerate(ALPHAS):
            m = lgb.LGBMRegressor(objective="quantile", alpha=a, **LGB_KW)
            m.fit(tr[FEAT], tr.target)
            q[:, i] = (te.pvlib + m.predict(te[FEAT])).clip(lower=0)
        q.sort(axis=1)  # fix quantile crossing
        qpred.append(pd.DataFrame(q, index=te.index,
                                  columns=[f"q{int(a*100):02d}" for a in ALPHAS])
                     .assign(actual=te.p))

        a = daily_kwh(te.p)
        row = {"month": str(mth)}
        for name, pr in preds.items():
            f = daily_kwh(pr).reindex(a.index)
            row[name] = float((abs(a - f) / a).mean() * 100)
            derr.setdefault(name, []).append((a - f).values)
        monthly.append(row)

    r = pd.DataFrame(monthly).set_index("month")
    cols = ["pvlib", "persistence", "climatology", "hybrid_l2", "hybrid_l1"]
    print(f"\n=== daily kWh MAPE by month {label} ===")
    print(r[cols].round(2).to_string())
    print("\nmean MAPE: " + "  ".join(f"{c} {r[c].mean():.2f}%" for c in cols))
    for c in cols[:-1]:
        print(f"hybrid_l1 beats {c:12s} in {(r.hybrid_l1 < r[c]).sum()}/{len(r)} months")

    print("\n=== Diebold-Mariano: hybrid_l1 vs baselines (daily errors) ===")
    e1 = np.concatenate(derr["hybrid_l1"])
    for c in ["pvlib", "persistence", "climatology", "hybrid_l2"]:
        dm, p = dm_test(e1, np.concatenate(derr[c]))
        verdict = "hybrid_l1 better" if dm < 0 else "baseline better"
        sig = "significant" if p < 0.05 else "NOT significant"
        print(f"  vs {c:12s} DM {dm:+6.2f}  p {p:.2g}   ({verdict}, {sig} at 5%)")

    Q = pd.concat(qpred)
    print(f"\n=== probabilistic track {label} (hourly, out-of-sample) ===")
    for a in (0.1, 0.5, 0.9):
        print(f"  pinball a={a}: {pinball(Q.actual, Q[f'q{int(a*100):02d}'], a):.1f} W")
    cov = float(((Q.actual >= Q.q10) & (Q.actual <= Q.q90)).mean())
    print(f"  P10-P90 coverage: {cov*100:.1f}%  (target 80%, miscal {cov*100-80:+.1f} pts)")
    print(f"  mean interval width P90-P10: {(Q.q90 - Q.q10).mean():.0f} W")

    calib = [(a, float((Q.actual <= Q[f"q{int(a*100):02d}"]).mean())) for a in ALPHAS]
    print("  calibration (nominal -> empirical): "
          + "  ".join(f"{a:.2f}->{e:.2f}" for a, e in calib))

    if make_plot:
        plot_calibration(calib)
    return r, Q


def plot_calibration(calib):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5, 5), dpi=150)
    xs, ys = zip(*calib)
    ax.plot([0, 1], [0, 1], color="#94a3b8", lw=1, ls="--", label="perfect")
    ax.plot(xs, ys, marker="o", color="#2563eb", lw=1.5, label="model")
    ax.set_xlabel("nominal quantile level")
    ax.set_ylabel("empirical frequency")
    ax.set_title("Quantile calibration (rolling-origin, hourly)")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig("calibration.png")
    print("  saved calibration.png")


if __name__ == "__main__":
    run(include_aq=True, label="[with AQ]")
    run(include_aq=False, make_plot=False, label="[no AQ]")
