"""Pure feature construction shared by training and scoring; no sklearn or database access."""
import numpy as np
import pandas as pd


FEATURE_VERSION = 1
SILENT_DAYS = 14

# Each concept owns its missing-value flag, so a concept is always selected as a whole.
CONCEPTS = {
    'clicks': ('click_rank',),
    'silence': ('silence', 'never_active'),
    'missed': ('miss_rate', 'no_due'),
    'score': ('score', 'no_score'),
    'recent': ('recent_click_rank',),
    'attempts': ('prev_attempts',),
    'credits': ('credits',),
}


def as_float(series):
    # Decimal columns arrive as objects; None must become NaN, not fail.
    return pd.to_numeric(series, errors='coerce').astype(float)


def build(frame, cutoff, score_column='score_lagged'):
    """Ranks use only rows of the same offering x snapshot, so no other time or course leaks in."""
    offering = frame['offering_key']
    days = as_float(frame['days_since_last_activity'])
    due = as_float(frame['due_cum'])
    score = as_float(frame[score_column]) / 100
    return pd.DataFrame({
        'click_rank': as_float(frame['clicks_cum']).groupby(offering).rank(pct=True),
        'silence': np.log1p(days.fillna(cutoff + 1)),
        'never_active': days.isna().astype(float),
        'miss_rate': as_float(frame['missed_cum']).clip(upper=due) / due.where(due > 0),
        'no_due': (due == 0).astype(float),
        'score': score,
        'no_score': score.isna().astype(float),
        'recent_click_rank': as_float(frame['clicks_week']).groupby(offering).rank(pct=True),
        'prev_attempts': as_float(frame['num_prev_attempts']).clip(upper=2),
        'credits': as_float(frame['studied_credits']),
    }, index=frame.index)


def columns(concepts):
    return [column for concept in concepts for column in CONCEPTS[concept]]


def is_silent(frame):
    days = as_float(frame['days_since_last_activity'])
    return days.isna() | (days >= SILENT_DAYS)


def standardize(features, means, stds):
    """Undefined values land on the training mean; their flag column carries the signal."""
    names = list(means)
    return ((features[names] - pd.Series(means)) / pd.Series(stds)).fillna(0.0)[names]


def fit_scaling(features):
    means, stds = features.mean(), features.std(ddof=0).replace(0, 1.0)
    return ({name: float(value) for name, value in means.items()},
            {name: float(value) for name, value in stds.items()})
