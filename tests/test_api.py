"""HTTP contract of the forwarding layer; SQL behaviour is covered by the dashboard tests."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api import app as api
from src.dashboard import service
from src.dashboard.filters import Filters


def dashboard_data(tables):
    return service.DashboardData('signals', Filters(week=7), 3, datetime(2026, 11, 5, tzinfo=timezone.utc),
                                 0.1, 22, 22, tables)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app, raise_server_exceptions=False)

    def test_meta_forwards_run_and_offerings(self):
        metadata = service.Metadata(3, [{'code_module': 'AAA', 'length_weeks': 38}])
        with patch.object(api.service, 'load_metadata', return_value=metadata):
            response = self.client.get('/api/meta')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'run_id': 3, 'offerings': metadata.offerings})

    def test_screen_passes_filters_and_expected_run(self):
        with patch.object(api.service, 'load_dashboard', return_value=dashboard_data({})) as load:
            response = self.client.get('/api/screens/signals', params={
                'module': 'CCC', 'presentation': '2014B', 'week': 7, 'expected_run_id': 3})
        self.assertEqual(response.status_code, 200)
        load.assert_called_once_with('signals', Filters(None, 'CCC', '2014B', 7), expected_run_id=3)

    def test_decimal_stays_numeric_and_null_stays_null(self):
        tables = {'summary': {'risk_pct': Decimal('42.17'), 'avg_score': None, 'enrollments': 26523}}
        with patch.object(api.service, 'load_dashboard', return_value=dashboard_data(tables)):
            body = self.client.get('/api/screens/signals', params={'week': 7}).json()
        self.assertEqual(body['tables']['summary'], {'risk_pct': 42.17, 'avg_score': None, 'enrollments': 26523})

    def test_not_a_number_never_reaches_the_client(self):
        with patch.object(api.service, 'load_dashboard', return_value=dashboard_data({'x': float('nan')})):
            response = self.client.get('/api/screens/signals', params={'week': 7})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()['error']['code'], 'internal')

    def test_gate_and_filter_errors_map_to_status(self):
        for code, status in (('not_ready', 503), ('busy', 503), ('stale_run', 409), ('filter', 400),
                             ('timeout', 504), ('query', 500)):
            error = service.DashboardError(code, 'thông điệp')
            with patch.object(api.service, 'load_metadata', side_effect=error):
                response = self.client.get('/api/meta')
            self.assertEqual(response.status_code, status, code)
            self.assertEqual(response.json(), {'error': {'code': code, 'message': 'thông điệp'}})

    def test_unexpected_error_is_sanitized(self):
        with patch.object(api.service, 'load_metadata', side_effect=ValueError('secret dsn')):
            with self.assertLogs('src.api.app', level='ERROR'):
                response = self.client.get('/api/meta')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('secret', json.dumps(response.json()))

    def test_dss_routes_forward_filters_and_run(self):
        for path, name in (('/api/dss/students', 'load_students'), ('/api/dss/curve', 'load_curve')):
            with patch.object(api.score, name, return_value={'run_id': 3}) as load:
                response = self.client.get(path, params={
                    'module': 'CCC', 'presentation': '2014B', 'week': 7, 'expected_run_id': 3})
            self.assertEqual(response.status_code, 200, path)
            load.assert_called_once_with('CCC', '2014B', 7, 3)

    def test_dss_evaluation_forwards_the_stored_document(self):
        with patch.object(api.score, 'load_evaluation', return_value={'run_id': 3, 'weeks': {}}):
            self.assertEqual(self.client.get('/api/dss/evaluation').json(), {'run_id': 3, 'weeks': {}})

    def test_stale_model_is_a_conflict(self):
        error = service.DashboardError('stale_model', 'thông điệp')
        with patch.object(api.score, 'load_students', side_effect=error):
            response = self.client.get('/api/dss/students', params={'week': 7})
        self.assertEqual(response.status_code, 409)

    def test_invalid_week_is_a_filter_error(self):
        response = self.client.get('/api/screens/signals', params={'week': 'abc'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'filter')


if __name__ == '__main__':
    unittest.main()
