"""Ranking metrics. Ties are shared in expectation, so results need no random seed."""
from math import ceil

import numpy as np

from .features import as_float


TOP_SHARES = (0.05, 0.10, 0.20, 0.30)
BASELINES = ('missed', 'silence', 'clicks')


def top_n(share, size):
    # Rounding first stops float noise such as 3.0000000000000004 adding a contact.
    return min(ceil(round(share * size, 9)), size)


def true_positive_curve(scores, labels):
    """curve[N] is the expected true positives among the N highest scores under random tie order."""
    values, inverse, counts = np.unique(-np.asarray(scores, dtype=float), return_inverse=True, return_counts=True)
    positives = np.bincount(inverse, weights=np.asarray(labels, dtype=float), minlength=len(values))
    return np.concatenate(([0.0], np.cumsum(np.repeat(positives / counts, counts))))


def baseline_scores(frame, name):
    if name == 'missed':
        return as_float(frame['missed_cum']).to_numpy()
    if name == 'silence':
        # Never active outranks every finite silence.
        return as_float(frame['days_since_last_activity']).fillna(np.inf).to_numpy()
    if name == 'clicks':
        return -as_float(frame['clicks_cum']).to_numpy()
    raise ValueError(f'Unknown baseline: {name}')


def precision_at(scores, labels, shares=TOP_SHARES):
    curve = true_positive_curve(scores, labels)
    size = len(curve) - 1
    return {share: float(curve[top_n(share, size)] / top_n(share, size)) for share in shares}


def brier(probabilities, labels):
    return float(np.mean((np.asarray(probabilities) - np.asarray(labels, dtype=float)) ** 2))
