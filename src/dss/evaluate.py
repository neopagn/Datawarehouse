"""Score the frozen model on 2014 once: python -m src.dss.evaluate. Writes model/evaluation.json."""
import hashlib
import json

import numpy as np
import pandas as pd

from src.dashboard import queries as dashboard_queries
from src.dashboard.service import read_session
from . import features, metrics, queries, score, train


GROUPS = ('2014B', '2014J', 'CCC')
SAME_TERM_MODULES = ('BBB', 'DDD', 'FFF')
BINS = 10


def group_of(module, presentation):
    # CCC never appears in 2013, so its results must not blend into the macro average.
    return 'CCC' if module == 'CCC' else presentation


def share_keys(precisions):
    return {f'{round(share * 100)}': value for share, value in precisions.items()}


def ranked_results(frame, labels, model_scores, mask=None):
    """Model and every baseline ranked on the same rows, with N taken from those rows."""
    mask = np.ones(len(frame), dtype=bool) if mask is None else mask
    kept, outcome = frame[mask], labels[mask]
    result = {'model': share_keys(metrics.precision_at(model_scores[mask], outcome))}
    for name in metrics.BASELINES:
        result[name] = share_keys(metrics.precision_at(metrics.baseline_scores(kept, name), outcome))
    return result


def offering_result(frame, labels, x, entry):
    scores = score.linear_score(x, entry)
    probabilities = score.probability(x, entry)
    silent = features.is_silent(frame).to_numpy()
    return {
        'rows': len(frame), 'at_risk': int(labels.sum()), 'base_rate': float(labels.mean()),
        'mean_probability': float(probabilities.mean()), 'brier': metrics.brier(probabilities, labels),
        'silent_rows': int(silent.sum()),
        'silent_precision': float(labels[silent].mean()) if silent.any() else None,
        'precision': ranked_results(frame, labels, scores),
        'precision_without_silent': ranked_results(frame, labels, scores, ~silent),
    }


def macro(results):
    """Offering-level average: every offering counts once, whatever its size."""
    def average(key):
        return {name: {share: float(np.mean([r[key][name][share] for r in results]))
                       for share in results[0][key][name]} for name in results[0][key]}
    return {'offerings': len(results), 'rows': sum(r['rows'] for r in results),
            'base_rate': float(np.mean([r['base_rate'] for r in results])),
            'mean_probability': float(np.mean([r['mean_probability'] for r in results])),
            'brier': float(np.mean([r['brier'] for r in results])),
            'silent_rows': sum(r['silent_rows'] for r in results),
            'precision': average('precision'), 'precision_without_silent': average('precision_without_silent')}


def calibration(probabilities, labels):
    bins = pd.qcut(probabilities, BINS, labels=False, duplicates='drop')
    table = pd.DataFrame({'p': probabilities, 'y': labels, 'bin': bins}).groupby('bin').agg(
        rows=('y', 'size'), predicted=('p', 'mean'), observed=('y', 'mean'))
    return table.reset_index(drop=True).to_dict('records')


def sensitivity_macro(pieces):
    """Macro precision per share for (frame, labels, scores) pieces, one per offering."""
    ranked = [ranked_results(frame, labels, scores) for frame, labels, scores in pieces]
    return {'offerings': len(ranked), 'rows': sum(len(piece[0]) for piece in pieces),
            'precision': {name: {share: float(np.mean([r[name][share] for r in ranked])) for share in ranked[0][name]}
                          for name in ranked[0]}}


def refit(frame, labels, entry, cutoff, score_column='score_lagged'):
    names = list(entry['means'])
    return train.fit(features.build(frame, cutoff, score_column)[names], labels, entry['c'])


def split_by_offering(frame, labels):
    for _key, index in frame.groupby('offering_key', sort=True).indices.items():
        yield frame.iloc[index], labels[index], index


def non_ccc_rows(frame):
    return (frame['code_module'] != 'CCC').to_numpy()


def evaluate_week(week, entry, train_frame, train_labels, test_frame, test_labels):
    cutoff = queries.cutoff_day(week)
    names = list(entry['means'])
    test_x = features.build(test_frame, cutoff)[names]
    per_offering, by_group = {}, {group: [] for group in GROUPS}
    for part, labels, index in split_by_offering(test_frame, test_labels):
        first = part.iloc[0]
        result = offering_result(part, labels, test_x.iloc[index], entry)
        per_offering[f"{first['code_module']}-{first['code_presentation']}"] = result
        by_group[group_of(first['code_module'], first['code_presentation'])].append(result)

    probabilities = score.probability(test_x, entry)
    ccc = ~non_ccc_rows(test_frame)
    calibrations = {'excluding_ccc': calibration(probabilities[~ccc], test_labels[~ccc]),
                    'ccc': calibration(probabilities[ccc], test_labels[ccc])}

    # Every sensitivity excludes CCC so it compares with the same offerings as the headline numbers.
    unlagged = refit(train_frame, train_labels, entry, cutoff, 'score_now')
    unlagged_x = features.build(test_frame, cutoff, 'score_now')[names]
    repeaters = test_frame['id_student'].isin(train_frame['id_student']).to_numpy()
    pieces = {'no_score_lag': [], 'without_repeat_students': []}
    for part, labels, index in split_by_offering(test_frame, test_labels):
        if part.iloc[0]['code_module'] == 'CCC':
            continue
        pieces['no_score_lag'].append((part, labels, score.linear_score(unlagged_x.iloc[index], unlagged)))
        keep = ~repeaters[index]
        pieces['without_repeat_students'].append(
            (part[keep], labels[keep], score.linear_score(test_x.iloc[index][keep], entry)))

    same_term_train = (train_frame['code_presentation'] == '2013B').to_numpy()
    same_term = refit(train_frame[same_term_train], train_labels[same_term_train], entry, cutoff)
    same_term_x = test_x
    pieces['train_2013b_test_2014b'] = [
        (part, labels, score.linear_score(same_term_x.iloc[index], same_term))
        for part, labels, index in split_by_offering(test_frame, test_labels)
        if part.iloc[0]['code_presentation'] == '2014B' and part.iloc[0]['code_module'] in SAME_TERM_MODULES]
    return {
        'concepts': entry['concepts'], 'c': entry['c'], 'frozen_baseline': entry['baseline'],
        'groups': {group: macro(results) for group, results in by_group.items()},
        'offerings': per_offering, 'calibration': calibrations,
        'sensitivity': {name: sensitivity_macro(value) for name, value in pieces.items()},
        'repeat_rows': int(repeaters.sum()), 'test_rows': len(test_frame),
    }


def main():
    raw_model = score.MODEL_DIR.joinpath('risk-model.json').read_bytes()
    model = json.loads(raw_model)
    with read_session() as (conn, run_id):
        score.checked(model, run_id)
        offerings = dashboard_queries.offerings(conn)
        train_keys = train.train_offering_keys(offerings)
        test_keys = [row['offering_key'] for row in offerings if row['code_presentation'].startswith(score.SERVED_YEAR)]
        weeks = {}
        for week in queries.CHECKPOINT_WEEKS:
            train_frame, train_labels = train.load_frame(conn, train_keys, week)
            test_frame, test_labels = train.load_frame(conn, test_keys, week)
            weeks[str(week)] = evaluate_week(week, model['weeks'][str(week)], train_frame, train_labels,
                                             test_frame, test_labels)
    document = {'feature_version': features.FEATURE_VERSION, 'run_id': run_id,
                'model_sha256': hashlib.sha256(raw_model).hexdigest(), 'weeks': weeks}
    score.MODEL_DIR.joinpath('evaluation.json').write_text(
        json.dumps(document, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
