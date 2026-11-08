"""Serve a frozen model: dependency-free scoring, explanations and API-facing loads."""
from contextlib import contextmanager
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.dashboard import queries as dashboard_queries
from src.dashboard.filters import FilterError, Filters, selected_offerings
from src.dashboard.service import DashboardError, read_session
from . import features, metrics, queries


MODEL_DIR = Path(__file__).parent / 'model'
SERVED_YEAR = '2014'
REASONS_SHOWN = 2
MODEL_FIELDS = ('concepts', 'c', 'cv_precision', 'baseline', 'baseline_cv_precision', 'rows', 'at_risk',
                'coefficients')


def linear_score(x, fitted):
    scaled = features.standardize(x, fitted['means'], fitted['stds'])
    return fitted['intercept'] + scaled.to_numpy() @ np.array([fitted['coefficients'][name] for name in scaled.columns])


def probability(x, fitted):
    return 1 / (1 + np.exp(-linear_score(x, fitted)))


def contributions(x, fitted):
    """Per-concept push on the log-odds relative to an average training row: association, not cause."""
    scaled = features.standardize(x, fitted['means'], fitted['stds'])
    result = {}
    for concept in fitted['concepts']:
        names = features.CONCEPTS[concept]
        result[concept] = sum(scaled[name].to_numpy() * fitted['coefficients'][name] for name in names)
    return pd.DataFrame(result, index=x.index)


def read_json(name):
    try:
        return json.loads((MODEL_DIR / name).read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise DashboardError('stale_model', 'Chưa có mô hình DSS. Hãy huấn luyện lại.') from None


def checked(document, run_id):
    if document.get('run_id') != run_id or document.get('feature_version') != features.FEATURE_VERSION:
        raise DashboardError('stale_model', 'Mô hình DSS không khớp lần nạp kho hiện tại. Hãy huấn luyện lại.')
    return document


def resolve_offering(offerings, module, presentation, week):
    """Exactly one 2014 offering at a checkpoint week: 2013 scores would be in-sample."""
    if type(week) is not int or week not in queries.CHECKPOINT_WEEKS:
        raise FilterError('Tuần phải là 3, 7 hoặc 11.')
    selected = selected_offerings(offerings, Filters(None, module, presentation))
    if len(selected) != 1 or not selected[0]['code_presentation'].startswith(SERVED_YEAR):
        raise FilterError('Hãy chọn đúng một lần mở năm 2014.')
    return selected[0]


def scored_frame(conn, offering, week, entry):
    frame = pd.DataFrame(queries.feature_rows(conn, [offering['offering_key']], week))
    x = features.build(frame, queries.cutoff_day(week))[list(entry['means'])]
    return frame, x


def student_rows(frame, x, entry):
    """Ranked list without outcomes; ties resolve by student_key so the order is reproducible."""
    pushes = contributions(x, entry)
    concepts = list(pushes.columns)
    values = pushes.to_numpy()
    strongest = np.argsort(-values, axis=1, kind='stable')[:, :REASONS_SHOWN]
    silent = features.is_silent(frame).to_numpy()
    risks = probability(x, entry)
    ordered = pd.DataFrame({'p': risks, 'key': frame['student_key'].to_numpy()}).sort_values(
        ['p', 'key'], ascending=[False, True], kind='stable').index
    records = frame.to_dict('records')
    result = []
    for rank, position in enumerate(ordered, start=1):
        row = records[position]
        result.append({
            'rank': rank, 'id_student': int(row['id_student']),
            'risk': round(float(risks[position]), 4),
            'silent': bool(silent[position]),
            'clicks_cum': int(row['clicks_cum']),
            'days_since_last_activity': optional_int(row['days_since_last_activity']),
            'missed_cum': int(row['missed_cum']), 'due_cum': int(row['due_cum']),
            'score_lagged': optional_float(row['score_lagged']),
            'reasons': [{'concept': concepts[column], 'push': round(float(values[position, column]), 3)}
                        for column in strongest[position] if values[position, column] > 0],
        })
    return result


def optional_int(value):
    return None if pd.isna(value) else int(value)


def optional_float(value):
    return None if pd.isna(value) else float(value)


@contextmanager
def checkpoint_read(module, presentation, week, expected_run_id, config):
    """Every student-level read: run check, model check, then one valid 2014 offering."""
    with read_session(config) as (conn, run_id):
        if expected_run_id is not None and run_id != expected_run_id:
            raise DashboardError('stale_run', 'Kho đã được nạp lại. Hãy tải lại trang.')
        model = checked(read_json('risk-model.json'), run_id)
        offering = resolve_offering(dashboard_queries.offerings(conn), module, presentation, week)
        yield conn, run_id, offering, model['weeks'][str(week)]


def load_students(module, presentation, week, expected_run_id=None, config=None):
    with checkpoint_read(module, presentation, week, expected_run_id, config) as (conn, run_id, offering, entry):
        frame, x = scored_frame(conn, offering, week, entry)
    return {'run_id': run_id, 'offering': offering, 'week': week, 'cutoff_day': queries.cutoff_day(week),
            'concepts': entry['concepts'], 'students': student_rows(frame, x, entry)}


def load_curve(module, presentation, week, expected_run_id=None, config=None):
    """Retrospective true positives per contact count; aggregates only, never per-student outcomes."""
    with checkpoint_read(module, presentation, week, expected_run_id, config) as (conn, run_id, offering, entry):
        frame, x = scored_frame(conn, offering, week, entry)
        labels = pd.DataFrame(queries.label_rows(conn, [offering['offering_key']]))
        leavers = queries.leavers(conn, [offering['offering_key']], week)
    merged = frame[['student_key', 'offering_key']].merge(labels, on=['student_key', 'offering_key'],
                                                          validate='one_to_one', how='left')
    outcome = merged['is_at_risk'].astype(int).to_numpy()
    model_curve = metrics.true_positive_curve(linear_score(x, entry), outcome)
    baseline_curve = metrics.true_positive_curve(metrics.baseline_scores(frame, entry['baseline']), outcome)
    return {'run_id': run_id, 'offering': offering, 'week': week, 'baseline': entry['baseline'],
            'enrolled': len(frame), 'at_risk': int(outcome.sum()), 'leavers': leavers,
            'tp_model': np.round(model_curve, 2).tolist(), 'tp_baseline': np.round(baseline_curve, 2).tolist()}


def load_model(config=None):
    """The frozen model in reviewable form; scaling constants stay in the JSON file."""
    with read_session(config) as (conn, run_id):
        model = checked(read_json('risk-model.json'), run_id)
        keys = [row['offering_key'] for row in dashboard_queries.offerings(conn)]
        leavers = queries.leavers(conn, keys)
    weeks = {week: {name: entry[name] for name in MODEL_FIELDS} for week, entry in model['weeks'].items()}
    return {'run_id': run_id, 'train_offerings': model['train_offerings'], 'served_year': SERVED_YEAR,
            'weeks': weeks, 'leavers': leavers}


def load_evaluation(config=None):
    with read_session(config) as (_conn, run_id):
        document = checked(read_json('evaluation.json'), run_id)
    return document
