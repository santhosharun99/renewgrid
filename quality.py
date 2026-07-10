"""Shared data-quality gates. Every analysis imports these instead of
re-implementing its own thresholds - analyse.py and model.py previously
disagreed about which days were outages because each had its own gate.

Conventions:
- "df" = raw production dataframe with columns t (naive local time), power_w
- day sets are sets of datetime.date
"""
import datetime
import pandas as pd

MIN_SAMPLES = 130          # expected ~150 five-minute samples per day
CLEAR_VI_Q = 0.40          # vi below this quantile
CLEAR_MAX_DROPS = 2
EVENT_CLASSES = ("logger_gap", "grid_outage", "inverter_fault",
                 "outage_or_fault", "underperformance")


def load_production(path="production.parquet"):
    return pd.read_parquet(path)


def usable_days(df, min_samples=MIN_SAMPLES):
    """Days with enough 5-min samples to trust daily aggregates."""
    n = df.groupby(df.t.dt.date).size()
    return set(n[n >= min_samples].index)


def clear_days(days=None, q=CLEAR_VI_Q, max_drops=CLEAR_MAX_DROPS):
    """Low-variability days: vi below the q-quantile and <= max_drops drops.

    days: dataframe indexed by date with vi/drops columns (days.csv),
    loaded from disk if None.
    """
    if days is None:
        days = pd.read_csv("days.csv", parse_dates=["date"]).set_index("date")
    m = (days.vi < days.vi.quantile(q)) & (days.drops <= max_drops)
    return set(d.date() for d in days.index[m])


def event_days(events=None, classes=EVENT_CLASSES):
    """Dates of outage/fault/gap/underperformance events.

    events: dataframe with date + class columns (events.csv), loaded from
    disk if None. Missing file -> empty set.
    """
    if events is None:
        try:
            events = pd.read_csv("events.csv", parse_dates=["date"])
        except FileNotFoundError:
            return set()
    ev = events[events["class"].isin(classes)]
    return set(pd.to_datetime(ev["date"]).dt.date)


def exclude_events(df, events=None, classes=EVENT_CLASSES):
    """Drop rows falling on event days. Works on a t-column dataframe or a
    DatetimeIndex-ed frame/series."""
    bad = event_days(events, classes)
    if "t" in getattr(df, "columns", ()):
        return df[~df.t.dt.date.isin(bad)]
    return df[[ts.date() not in bad for ts in df.index]]


def keep_days(df, dates):
    """Restrict a DatetimeIndex-ed frame/series to the given set of dates."""
    dates = {d.date() if isinstance(d, (pd.Timestamp, datetime.datetime)) else d
             for d in dates}
    return df[[ts.date() in dates for ts in df.index]]
