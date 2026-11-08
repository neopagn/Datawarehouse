"""Feature rules and the structural guarantees against outcome or future leakage."""
import re
import unittest

import numpy as np
import pandas as pd

from src.dss import features, queries


def frame(**overrides):
    base = {
        'offering_key': [1, 1, 1, 2],
        'clicks_cum': [0, 10, 100, 5],
        'clicks_week': [0, 5, 20, 5],
        'days_since_last_activity': [None, 3, 20, 0],
        'missed_cum': [1, 0, 3, 0],
        'due_cum': [2, 2, 2, 0],
        'score_lagged': [None, 70, 40, 90],
        'score_now': [10, 70, 40, 90],
        'num_prev_attempts': [0, 1, 5, 0],
        'studied_credits': [60, 60, 120, 30],
    }
    return pd.DataFrame({**base, **overrides})


class BuildTests(unittest.TestCase):
    def test_click_rank_stays_inside_the_offering(self):
        built = features.build(frame(), 27)
        self.assertEqual(built['click_rank'].round(4).tolist(), [0.3333, 0.6667, 1.0, 1.0])

    def test_never_active_is_flagged_not_treated_as_zero_silence(self):
        built = features.build(frame(), 27)
        self.assertEqual(built['never_active'].tolist(), [1, 0, 0, 0])
        self.assertAlmostEqual(built['silence'][0], np.log1p(28))

    def test_no_due_is_undefined_and_miss_rate_is_capped(self):
        built = features.build(frame(), 27)
        self.assertEqual(built['no_due'].tolist(), [0, 0, 0, 1])
        self.assertTrue(np.isnan(built['miss_rate'][3]))
        self.assertEqual(built['miss_rate'][2], 1.0)

    def test_score_uses_the_lagged_snapshot_by_default(self):
        self.assertTrue(np.isnan(features.build(frame(), 27)['score'][0]))
        self.assertEqual(features.build(frame(), 27, 'score_now')['score'][0], 0.1)

    def test_unrelated_columns_never_change_features(self):
        before = features.build(frame(), 27)
        after = features.build(frame(final_result=['Pass'] * 4, is_at_risk=[True] * 4), 27)
        pd.testing.assert_frame_equal(before, after)

    def test_silent_covers_never_active_and_fourteen_days(self):
        self.assertEqual(features.is_silent(frame()).tolist(), [True, False, True, False])

    def test_undefined_values_land_on_the_training_mean(self):
        built = features.build(frame(), 27)[['miss_rate', 'score']]
        means, stds = features.fit_scaling(built)
        scaled = features.standardize(built, means, stds)
        self.assertEqual(scaled['miss_rate'][3], 0.0)
        self.assertFalse(scaled.isna().any().any())


class QueryGuaranteeTests(unittest.TestCase):
    def test_feature_query_reads_no_outcome_or_lifetime_total(self):
        for column in ('final_result', 'is_at_risk', 'dim_result', 'result_key', 'total_clicks', 'active_days_cum',
                       'last_active_day_key', 'submitted_count', 'avg_coursework_score',
                       'weighted_coursework_score', 'has_status_conflict', 'unregistration_day_key'):
            self.assertNotIn(column, queries.FEATURE_ROWS)

    def test_feature_query_reads_only_cutoff_and_lagged_snapshots(self):
        conditions = re.findall(r'snapshot_day_key = ([^\n]+)', queries.FEATURE_ROWS)
        self.assertEqual(sorted(condition.split(' ORDER')[0].strip() for condition in conditions),
                         ['%(cutoff)s', '%(cutoff)s - %(lag)s'])

    def test_no_demographic_or_course_identity_feature(self):
        names = [name for group in features.CONCEPTS.values() for name in group]
        built = features.build(frame(), 27)
        self.assertEqual(sorted(built.columns), sorted(names))
        for banned in ('module', 'domain', 'imd', 'gender', 'age', 'disability', 'education', 'region'):
            self.assertFalse(any(banned in name for name in names))


if __name__ == '__main__':
    unittest.main()
