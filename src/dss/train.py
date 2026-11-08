"""Fit on 2013 only and freeze: run from repo root with python -m src.dss.train."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from src.dashboard import queries as dashboard_queries
from src.dashboard.service import read_session
from . import features, metrics, queries
from .score import linear_score


MODEL_PATH = Path(__file__).parent / 'model' / 'risk-model.json'
TRAIN_YEAR = '2013'
# Nested, simplest first: selection takes the first set within TOLERANCE of the best.
CONCEPT_SETS = (
    ('clicks', 'silence', 'missed'),
    ('clicks', 'silence', 'missed', 'score'),
    ('clicks', 'silence', 'missed', 'score', 'recent'),
    ('clicks', 'silence', 'missed', 'score', 'recent', 'attempts'),
    ('clicks', 'silence', 'missed', 'score', 'recent', 'attempts', 'credits'),
)
REGULARIZATION = (0.01, 0.1, 1.0, 10.0)
TOLERANCE = 0.002


def fit(train_x, labels, c):
    means, stds = features.fit_scaling(train_x)
    classifier = LogisticRegression(C=c, max_iter=5000).fit(features.standardize(train_x, means, stds), labels)
    return {'intercept': float(classifier.intercept_[0]), 'means': means, 'stds': stds,
            'coefficients': dict(zip(train_x.columns, map(float, classifier.coef_[0])))}


def cross_validate(x, labels, offerings, c):
    """Mean precision over the top shares, leaving one whole offering out each fold."""
    results = []
    for held_out in offerings.unique():
        mask = (offerings == held_out).to_numpy()
        fitted = fit(x[~mask], labels[~mask], c)
        results.append(np.mean(list(metrics.precision_at(linear_score(x[mask], fitted), labels[mask]).values())))
    return float(np.mean(results))


def select(frame, labels, cutoff):
    built = features.build(frame, cutoff)
    grid = [{'concepts': list(concepts), 'c': c,
             'cv_precision': cross_validate(built[features.columns(concepts)], labels, frame['offering_key'], c)}
            for concepts in CONCEPT_SETS for c in REGULARIZATION]
    best = max(row['cv_precision'] for row in grid)
    return next(row for row in grid if row['cv_precision'] >= best - TOLERANCE), best


def frozen_baseline(frame, labels):
    """Best single signal on training data: the same rule as the model, chosen before any test row."""
    def score(name, part):
        return np.mean(list(metrics.precision_at(metrics.baseline_scores(frame[part], name), labels[part]).values()))
    means = {name: float(np.mean([score(name, (frame['offering_key'] == offering).to_numpy())
                                  for offering in frame['offering_key'].unique()])) for name in metrics.BASELINES}
    return max(means, key=means.get), means


def train_offering_keys(offerings):
    keys = [row['offering_key'] for row in offerings if row['code_presentation'].startswith(TRAIN_YEAR)]
    if not keys:
        raise ValueError('No training offerings')
    return keys


def load_frame(conn, offering_keys, week):
    frame = pd.DataFrame(queries.feature_rows(conn, offering_keys, week))
    labels = pd.DataFrame(queries.label_rows(conn, offering_keys))
    merged = frame.merge(labels, on=['student_key', 'offering_key'], validate='one_to_one', how='left')
    if merged['is_at_risk'].isna().any():
        raise ValueError('Snapshot row without enrollment label')
    return merged.drop(columns='is_at_risk'), merged['is_at_risk'].astype(int).to_numpy()


def train_week(frame, labels, week):
    cutoff = queries.cutoff_day(week)
    chosen, best = select(frame, labels, cutoff)
    names = features.columns(chosen['concepts'])
    fitted = fit(features.build(frame, cutoff)[names], labels, chosen['c'])
    baseline, baseline_cv = frozen_baseline(frame, labels)
    return {**chosen, 'best_cv_precision': best, 'baseline': baseline, 'baseline_cv_precision': baseline_cv,
            'rows': len(frame), 'at_risk': int(labels.sum()), **fitted}


def main():
    with read_session() as (conn, run_id):
        offerings = dashboard_queries.offerings(conn)
        keys = train_offering_keys(offerings)
        weeks = {}
        for week in queries.CHECKPOINT_WEEKS:
            frame, labels = load_frame(conn, keys, week)
            weeks[str(week)] = train_week(frame, labels, week)
    model = {'feature_version': features.FEATURE_VERSION, 'run_id': run_id,
             'train_offerings': sorted(row['code_module'] + '-' + row['code_presentation'] for row in offerings
                                       if row['offering_key'] in keys),
             'weeks': weeks}
    MODEL_PATH.write_text(json.dumps(model, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    for week, entry in weeks.items():
        print(week, entry['concepts'], 'C', entry['c'], 'cv', round(entry['cv_precision'], 4),
              'best', round(entry['best_cv_precision'], 4), 'baseline', entry['baseline'],
              {k: round(v, 4) for k, v in entry['baseline_cv_precision'].items()}, 'rows', entry['rows'])


if __name__ == '__main__':
    main()
