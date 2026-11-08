"""Frozen-model serving and training rules, without a database."""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.dashboard.filters import FilterError
from src.dashboard.service import DashboardError
from src.dss import features, queries, score, train


OFFERINGS = [
    {'offering_key': 1, 'domain': 'STEM', 'code_module': 'CCC', 'code_presentation': '2014B', 'length_weeks': 38},
    {'offering_key': 2, 'domain': 'STEM', 'code_module': 'CCC', 'code_presentation': '2014J', 'length_weeks': 38},
    {'offering_key': 3, 'domain': 'STEM', 'code_module': 'DDD', 'code_presentation': '2013J', 'length_weeks': 38},
]
ENTRY = {
    'concepts': ['clicks', 'silence'], 'intercept': -0.5,
    'means': {'click_rank': 0.5, 'silence': 1.0, 'never_active': 0.0},
    'stds': {'click_rank': 0.25, 'silence': 1.0, 'never_active': 1.0},
    'coefficients': {'click_rank': -1.0, 'silence': 0.5, 'never_active': 2.0},
}


def student_frame():
    return pd.DataFrame({
        'student_key': [3, 1, 2], 'offering_key': [1, 1, 1], 'id_student': [30, 10, 20],
        'clicks_cum': [50, 5, 5], 'clicks_week': [5, 0, 0], 'days_since_last_activity': [1, None, None],
        'missed_cum': [0, 1, 1], 'due_cum': [1, 1, 1], 'score_lagged': [80, None, None],
    })


def scored():
    frame = student_frame()
    x = features.build(frame.assign(num_prev_attempts=0, studied_credits=60), 27)[list(ENTRY['means'])]
    return frame, x


class ScoringTests(unittest.TestCase):
    def test_contributions_add_up_to_the_linear_score(self):
        _frame, x = scored()
        total = score.contributions(x, ENTRY).sum(axis=1).to_numpy() + ENTRY['intercept']
        np.testing.assert_allclose(total, score.linear_score(x, ENTRY))

    def test_ranks_with_reproducible_tie_order_and_no_outcome(self):
        frame, x = scored()
        rows = score.student_rows(frame, x, ENTRY)
        self.assertEqual([row['id_student'] for row in rows], [10, 20, 30])
        self.assertEqual([row['rank'] for row in rows], [1, 2, 3])
        self.assertEqual(rows[0]['reasons'][0]['concept'], 'silence')
        self.assertTrue(rows[0]['silent'])
        self.assertIsNone(rows[0]['days_since_last_activity'])
        self.assertFalse({'final_result', 'is_at_risk', 'label'} & set(rows[0]))

    def test_only_positive_pushes_become_reasons(self):
        frame, x = scored()
        safest = score.student_rows(frame, x, ENTRY)[-1]
        self.assertTrue(all(reason['push'] > 0 for reason in safest['reasons']))


class GateTests(unittest.TestCase):
    def test_accepts_one_2014_offering_at_a_checkpoint(self):
        self.assertEqual(score.resolve_offering(OFFERINGS, 'CCC', '2014B', 7)['offering_key'], 1)

    def test_rejects_other_weeks_many_offerings_and_2013(self):
        for args in (('CCC', '2014B', 5), ('CCC', '2014B', None), ('CCC', None, 7), (None, None, 7),
                     ('DDD', '2013J', 7), ('ZZZ', '2014B', 7)):
            with self.assertRaises(FilterError, msg=args):
                score.resolve_offering(OFFERINGS, *args)

    def test_model_must_match_run_and_feature_version(self):
        current = {'run_id': 3, 'feature_version': features.FEATURE_VERSION}
        self.assertIs(score.checked(current, 3), current)
        for document, run_id in ((current, 4), ({**current, 'feature_version': -1}, 3), ({}, 3)):
            with self.assertRaises(DashboardError) as caught:
                score.checked(document, run_id)
            self.assertEqual(caught.exception.code, 'stale_model')

    def test_missing_model_is_stale_not_internal(self):
        with patch.object(score, 'MODEL_DIR', score.MODEL_DIR / 'does-not-exist'):
            with self.assertRaises(DashboardError) as caught:
                score.read_json('risk-model.json')
        self.assertEqual(caught.exception.code, 'stale_model')


class TrainingTests(unittest.TestCase):
    def test_training_set_is_2013_only(self):
        self.assertEqual(train.train_offering_keys(OFFERINGS), [3])

    def test_no_2013_offering_refuses_to_train(self):
        with self.assertRaises(ValueError):
            train.train_offering_keys(OFFERINGS[:2])

    def test_fit_is_reproducible_and_scoring_matches_sklearn_probability(self):
        rng = np.random.default_rng(0)
        x = pd.DataFrame({'a': rng.normal(size=200), 'b': rng.normal(size=200)})
        labels = (x['a'] + rng.normal(size=200) > 0).astype(int).to_numpy()
        first, second = train.fit(x, labels, 1.0), train.fit(x, labels, 1.0)
        self.assertEqual(first, second)
        self.assertGreater(first['coefficients']['a'], 0)
        probabilities = score.probability(x, first)
        self.assertTrue(((probabilities > 0) & (probabilities < 1)).all())

    def test_checkpoints_are_fixed(self):
        self.assertEqual(queries.CHECKPOINT_WEEKS, (3, 7, 11))
        self.assertEqual(queries.cutoff_day(7), 55)


if __name__ == '__main__':
    unittest.main()
