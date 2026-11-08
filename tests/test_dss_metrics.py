"""Hand-calculated ranking metrics."""
import unittest

import numpy as np
import pandas as pd

from src.dss import metrics


class CurveTests(unittest.TestCase):
    def test_distinct_scores(self):
        self.assertEqual(metrics.true_positive_curve([3, 2, 1], [1, 0, 1]).tolist(), [0, 1, 1, 2])

    def test_ties_share_positives_in_expectation(self):
        curve = metrics.true_positive_curve([5, 5, 5, 5, 1], [1, 1, 0, 0, 1])
        self.assertEqual(curve.tolist(), [0, 0.5, 1, 1.5, 2, 3])

    def test_infinite_score_ranks_first(self):
        self.assertEqual(metrics.true_positive_curve([np.inf, 100], [1, 0]).tolist(), [0, 1, 1])


class PrecisionTests(unittest.TestCase):
    def test_top_n_rounds_up_and_never_exceeds_size(self):
        self.assertEqual(metrics.top_n(0.05, 21), 2)
        self.assertEqual([metrics.top_n(share, 1000) for share in metrics.TOP_SHARES], [50, 100, 200, 300])
        self.assertEqual(metrics.top_n(0.30, 10), 3)
        self.assertEqual(metrics.top_n(1.0, 7), 7)

    def test_precision_uses_the_rounded_n(self):
        scores = list(range(20, 0, -1))
        labels = [1, 0] * 10
        self.assertEqual(metrics.precision_at(scores, labels, (0.10,))[0.10], 0.5)

    def test_brier(self):
        self.assertAlmostEqual(metrics.brier([0.5, 1.0], [1, 1]), 0.125)


class BaselineTests(unittest.TestCase):
    frame = pd.DataFrame({'missed_cum': [2, 0], 'days_since_last_activity': [None, 30], 'clicks_cum': [1, 9]})

    def test_higher_means_riskier(self):
        for name in metrics.BASELINES:
            scores = metrics.baseline_scores(self.frame, name)
            self.assertGreater(scores[0], scores[1], name)

    def test_unknown_baseline_is_rejected(self):
        with self.assertRaises(ValueError):
            metrics.baseline_scores(self.frame, 'nope')


if __name__ == '__main__':
    unittest.main()
