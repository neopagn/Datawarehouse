"""AppTest rendering fixtures are test-only; SQL-backed flows are opt-in below."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.dashboard import service
from src.dashboard.filters import Filters, SCREENS
from tests.dashboard_fixture import seed, test_config
from tests.test_dashboard_filters import OFFERINGS


APP = Path(__file__).resolve().parents[1] / 'src' / 'dashboard' / 'app.py'


def sample_data(screen, filters, expected_run_id=None):
    summary = {'enrollments': 3, 'students': 2, 'at_risk': 1, 'withdrawn': 1,
               'risk_pct': Decimal('33.33'), 'withdrawn_pct': Decimal('33.33'),
               'known_unregistration': 2, 'unknown_unregistration': 1, 'na_unregistration': 0,
               'avg_clicks': Decimal('2.50'), 'zero_click_pct': Decimal('50.00'), 'avg_missed': Decimal('0.50')}
    tables = {
        'overview': {'summary': summary,
                     'rollup': [dict(summary, domain='STEM', code_module='AAA', code_presentation='2014J', grouping=level)
                                for level in (0, 1, 3, 7)],
                     'breakdowns': {key: [dict(summary, label='Unknown')] for key in ('imd', 'education', 'disability')},
                     'attempts': [dict(summary, previous_attempts=2)]},
        'registration': {'summary': summary, 'cancellations': [{'phase': 'Ngày 0', 'enrollments': 2, 'share_pct': 100}],
                         'registrations': [dict(summary, phase='Không rõ')]},
        'engagement': {'summary': summary, 'outcomes': [dict(summary, final_result='Pass')],
                       'trend': [{'week_no': 0, 'final_result': 'Pass', 'enrollments': 30, 'avg_clicks': Decimal('2.50')},
                                 {'week_no': 1, 'final_result': 'Pass', 'enrollments': 30, 'avg_clicks': Decimal('1.50')}],
                       'activity': [{'activity_group': 'Content', 'activity_type': None, 'grouping': 1, 'clicks': 5, 'share_pct': 100},
                                    {'activity_group': 'Content', 'activity_type': 'oucontent', 'grouping': 0, 'clicks': 5, 'share_pct': 100}]},
        'assessments': {'by_type': [{'assessment_type': 'Exam', 'assessments': 1, 'records': 0, 'banked': 0, 'eligible_late': 0, 'avg_score': None},
                                    {'assessment_type': 'TMA', 'assessments': 1, 'records': 2, 'banked': 0, 'eligible_late': 2, 'avg_score': Decimal('70.00')}],
                        'detail': [{'id_assessment': 1, 'assessment_type': 'Exam', 'is_due_estimated': True,
                                    'has_recorded_results': False, 'avg_score': None, 'record_pct': 0}]},
        'signals': {'summary': summary, 'buckets': [dict(summary, missed_bucket=2)]},
    }[screen]
    return service.DashboardData(screen, filters, 5, datetime.now(timezone.utc), 0.01, 3,
                                 None if filters.week is None else 1, tables)


class DashboardAppTests(unittest.TestCase):
    def setUp(self):
        self.metadata = patch.object(service, 'load_metadata', return_value=service.Metadata(5, OFFERINGS)).start()
        self.loader = patch.object(service, 'load_dashboard', side_effect=sample_data).start()
        self.addCleanup(patch.stopall)

    def app(self):
        return AppTest.from_file(str(APP), default_timeout=20).run()

    def test_all_five_screens_render_and_only_selected_screen_is_loaded(self):
        app = self.app()
        for screen in SCREENS:
            if screen != 'overview':
                app.radio(key='screen').set_value(screen).run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(app.header[0].value, SCREENS[screen])
            self.assertTrue(app.metric)
            self.assertTrue(app.dataframe)
            self.assertEqual(self.loader.call_args.args[0], screen)
            filters = self.loader.call_args.args[1]
            self.assertEqual(filters.week is not None, screen in ('engagement', 'signals'))
            self.assertTrue(any('run_id=5' in caption.value for caption in app.caption))

    def test_filter_cascade_and_week_reset(self):
        app = self.app()
        app.selectbox(key='domain').set_value('STEM').run()
        app.selectbox(key='module').set_value('AAA').run()
        app.selectbox(key='presentation').set_value('2013J').run()
        app.selectbox(key='domain').set_value('Social Sciences').run()
        self.assertFalse(app.exception, app.exception)
        self.assertIsNone(app.selectbox(key='module').value)
        self.assertIsNone(app.selectbox(key='presentation').value)
        app.radio(key='screen').set_value('signals').run()
        self.assertEqual(app.selectbox(key='week').value, 7)
        app.selectbox(key='domain').set_value('STEM').run()
        self.assertEqual(app.selectbox(key='week').value, 0)
        app.radio(key='screen').set_value('assessments').run()
        self.assertFalse(app.exception, app.exception)
        self.assertIsNone(self.loader.call_args.args[1].week)
        self.assertNotIn('week', [widget.key for widget in app.selectbox])

    def test_error_after_success_removes_old_kpis_and_retry_recovers(self):
        app = self.app()
        self.assertTrue(app.metric)
        self.loader.side_effect = service.DashboardError('busy', 'ETL đang giữ lock.')
        app.button(key='retry').click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertFalse(app.metric)
        self.assertTrue(app.error)
        self.assertFalse(app.dataframe)
        self.loader.side_effect = sample_data
        app.button(key='retry').click().run()
        self.assertTrue(app.metric)
        self.assertFalse(app.error)

    def test_connection_failed_latest_failed_and_stale_run_show_safe_error(self):
        app = self.app()
        for code, message in (('connection', 'Không kết nối được PostgreSQL.'),
                              ('not_ready', 'Lần ETL chưa SUCCESS.'), ('stale_run', 'Kho đã nạp lại.')):
            self.metadata.side_effect = service.DashboardError(code, message)
            app.button(key='retry').click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertFalse(app.metric)
            self.assertEqual(app.error[0].value, message)

    def test_empty_metadata_has_no_fake_metrics(self):
        self.metadata.return_value = service.Metadata(5, [])
        app = self.app()
        self.assertFalse(app.exception)
        self.assertTrue(app.info)
        self.assertFalse(app.metric)
        self.loader.assert_not_called()

    def test_dynamic_activity_and_assessment_choices_reset_when_options_disappear(self):
        def changing_payload(screen, filters, expected_run_id=None):
            payload = sample_data(screen, filters, expected_run_id)
            if filters.module == 'BBB':
                if screen == 'engagement':
                    payload.tables['activity'] = [
                        {'activity_group': 'Assessment', 'activity_type': None, 'grouping': 1, 'clicks': 3, 'share_pct': 100},
                        {'activity_group': 'Assessment', 'activity_type': 'quiz', 'grouping': 0, 'clicks': 3, 'share_pct': 100},
                    ]
                elif screen == 'assessments':
                    payload.tables['detail'][0]['assessment_type'] = 'TMA'
            return payload

        self.loader.side_effect = changing_payload
        app = self.app()
        app.radio(key='screen').set_value('engagement').run()
        app.selectbox(key='activity_group').set_value('Content').run()
        app.selectbox(key='module').set_value('BBB').run()
        self.assertFalse(app.exception, app.exception)
        self.assertIsNone(app.selectbox(key='activity_group').value)
        self.assertEqual(app.dataframe[-1].value.iloc[0]['Nhóm tài nguyên'], 'Assessment')
        app.selectbox(key='module').set_value(None).run()
        app.radio(key='screen').set_value('assessments').run()
        app.selectbox(key='assessment_type').set_value('Exam').run()
        app.selectbox(key='module').set_value('BBB').run()
        self.assertFalse(app.exception, app.exception)
        self.assertIsNone(app.selectbox(key='assessment_type').value)
        self.assertEqual(app.dataframe[-1].value.iloc[0]['Loại bài'], 'TMA')

    def test_null_percentages_render_as_dash_not_zero(self):
        def no_observations(screen, filters, expected_run_id=None):
            payload = sample_data(screen, filters, expected_run_id)
            payload.tables['summary']['risk_pct'] = None
            payload.tables['summary']['withdrawn_pct'] = None
            return payload

        self.loader.side_effect = no_observations
        app = self.app()
        self.assertEqual(app.metric[2].value, '—')
        self.assertEqual(app.metric[3].value, '—')
        self.assertFalse(app.exception)

    def test_null_table_cells_render_as_dash(self):
        app = self.app()
        app.radio(key='screen').set_value('assessments').run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.dataframe[0].value.iloc[0]['Điểm trung bình'], '—')

    def test_required_assessment_and_retrospective_labels(self):
        app = self.app()
        app.radio(key='screen').set_value('assessments').run()
        self.assertFalse(app.exception, app.exception)
        self.assertIn('banked', app.info[0].value)
        detail = app.dataframe[-1].value
        self.assertEqual(detail.iloc[0]['Nguồn ngày hạn'], 'Ước tính')
        self.assertEqual(detail.iloc[0]['Tình trạng ghi nhận'], 'Không có kết quả được ghi nhận')
        self.assertTrue(any('Không so sánh điểm Exam ngoài CCC/DDD' in item.value for item in app.warning))
        app.radio(key='screen').set_value('signals').run()
        self.assertTrue(any('không phải mô hình dự báo' in item.value for item in app.warning))
        self.assertIn('ngày hủy không rõ', app.info[0].value.lower())

    def test_tables_use_vietnamese_headers_and_hide_internal_grouping(self):
        app = self.app()
        for screen in SCREENS:
            app.radio(key='screen').set_value(screen).run()
            self.assertFalse(app.exception, app.exception)
            for table in app.dataframe:
                self.assertNotIn('grouping', table.value.columns)
                self.assertNotIn('risk_pct', table.value.columns)
                self.assertNotIn('enrollments', table.value.columns)
            self.assertTrue(any('Chỉ so sánh các lần mở' in item.value for item in app.warning))
        self.assertIn('Số bài bỏ lỡ lũy kế', app.dataframe[0].value.columns)

    def test_requested_charts_and_categorical_missed_buckets(self):
        app = self.app()
        for screen, count in (('overview', 3), ('registration', 2), ('engagement', 4), ('assessments', 1), ('signals', 1)):
            app.radio(key='screen').set_value(screen).run()
            self.assertFalse(app.exception, app.exception)
            charts = app.get('vega_lite_chart')
            self.assertEqual(len(charts), count)
        spec = json.loads(charts[0].proto.spec)
        self.assertEqual(spec['encoding']['y']['type'], 'ordinal')
        self.assertEqual(spec['encoding']['x']['type'], 'quantitative')
        self.assertEqual(list(app.dataframe[0].value['Số bài bỏ lỡ lũy kế']), ['Từ 2 bài trở lên'])
        self.assertEqual(app.dataframe[0].value.iloc[0]['Fail + Withdrawn (%)'], 33.33)


class DashboardUnavailableAppTests(unittest.TestCase):
    def test_real_connection_failure_renders_no_metrics_or_traceback(self):
        # Reserve a non-listening local port: real connection refusal, no SQL/service mock.
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            config = service.DatabaseConfig(port=reserved.getsockname()[1])
            with patch.object(service.DatabaseConfig, 'from_env', return_value=config):
                app = AppTest.from_file(str(APP), default_timeout=20).run()
        self.assertFalse(app.exception, app.exception)
        self.assertFalse(app.metric)
        self.assertFalse(app.dataframe)
        self.assertIn('Không kết nối được PostgreSQL', app.error[0].value)
        self.assertTrue(app.button(key='retry'))


@unittest.skipUnless(os.environ.get('OULAD_DASHBOARD_TEST_DATABASE'), 'Set OULAD_DASHBOARD_TEST_DATABASE for SQL-backed AppTest')
class DashboardSqlAppTests(unittest.TestCase):
    def setUp(self):
        self.config = test_config()
        with self.config.connect() as conn:
            seed(conn)

    def test_all_screens_through_real_service_and_sql(self):
        # Only configuration is redirected; no production queries/loaders are mocked.
        with patch.object(service.DatabaseConfig, 'from_env', return_value=self.config):
            app = AppTest.from_file(str(APP), default_timeout=30).run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(app.metric[0].value, '9')
            self.assertEqual(app.metric[1].value, '8')
            for screen in ('registration', 'engagement', 'assessments', 'signals'):
                app.radio(key='screen').set_value(screen).run()
                self.assertFalse(app.exception, app.exception)
                self.assertFalse(app.error, app.error)
                self.assertTrue(app.dataframe)
