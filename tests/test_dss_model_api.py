"""Public model description and leaver counts, without a database."""
from contextlib import contextmanager
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api import app as api
from src.dss import features, queries, score
from tests.test_dss_score import ENTRY, OFFERINGS


DOCUMENT = {
    'run_id': 3, 'feature_version': features.FEATURE_VERSION, 'train_offerings': ['DDD-2013J'],
    'weeks': {'7': {**ENTRY, 'c': 0.01, 'cv_precision': 0.84, 'baseline': 'silence',
                    'baseline_cv_precision': {'silence': 0.77}, 'rows': 10, 'at_risk': 4}},
}
LEAVERS = {'enrollments': 100, 'left_before_first_cutoff': 7, 'left_before_cutoff': 7}


@contextmanager
def fake_session(_config=None):
    yield object(), 3


class ModelDescriptionTests(unittest.TestCase):
    def load(self):
        with patch.object(score, 'read_session', fake_session), \
                patch.object(score, 'read_json', return_value=DOCUMENT), \
                patch.object(score.dashboard_queries, 'offerings', return_value=OFFERINGS), \
                patch.object(score.queries, 'leavers', return_value=LEAVERS) as leavers:
            return score.load_model(), leavers

    def test_exposes_the_frozen_choices_and_withholds_scaling(self):
        body, _leavers = self.load()
        week = body['weeks']['7']
        self.assertEqual(week['coefficients'], ENTRY['coefficients'])
        self.assertEqual(body['train_offerings'], ['DDD-2013J'])
        self.assertFalse({'means', 'stds', 'intercept'} & set(week))

    def test_leavers_cover_the_whole_warehouse(self):
        body, leavers = self.load()
        self.assertEqual(body['leavers'], LEAVERS)
        self.assertEqual(leavers.call_args.args[1], [row['offering_key'] for row in OFFERINGS])

    def test_stale_model_is_refused(self):
        with patch.object(score, 'read_session', fake_session), \
                patch.object(score, 'read_json', return_value={**DOCUMENT, 'run_id': 2}):
            with self.assertRaises(score.DashboardError):
                score.load_model()

    def test_route_forwards_the_payload(self):
        client = TestClient(api.app)
        with patch.object(api.score, 'load_model', return_value={'run_id': 3}):
            self.assertEqual(client.get('/api/dss/model').json(), {'run_id': 3})


class LeaverQueryTests(unittest.TestCase):
    def test_sentinels_are_excluded_and_cutoffs_follow_the_week(self):
        self.assertEqual(queries.LEAVER_ROWS.count('unregistration_day_key > -9000'), 2)
        with patch.object(queries, 'rows', return_value=[LEAVERS]) as rows:
            queries.leavers(object(), [1], 7)
        params = rows.call_args.args[2]
        self.assertEqual((params['first_cutoff'], params['cutoff']), (6, 55))


if __name__ == '__main__':
    unittest.main()
