"""Opt-in SQL/concurrency tests on a disposable oulad_test_dashboard[_suffix] only."""
import os
import unittest
from unittest.mock import patch

from src.dashboard import queries, service
from src.dashboard.filters import Filters
from src.etl.pipeline import LOCK_ID
from tests.dashboard_fixture import seed, test_config


@unittest.skipUnless(os.environ.get('OULAD_DASHBOARD_TEST_DATABASE'), 'Set OULAD_DASHBOARD_TEST_DATABASE for disposable PostgreSQL tests')
class DashboardPostgresTests(unittest.TestCase):
    def setUp(self):
        self.config = test_config()
        self.conn = self.config.connect()
        self.addCleanup(self.conn.close)
        seed(self.conn)

    def load(self, screen='overview', filters=Filters()):
        return service.load_dashboard(screen, filters, config=self.config)

    def test_overview_distinct_rollup_and_filtered_denominators(self):
        data = self.load().tables
        self.assertEqual(data['summary']['enrollments'], 9)
        self.assertEqual(data['summary']['students'], 8)
        self.assertEqual(data['summary']['at_risk'], 5)
        self.assertAlmostEqual(float(data['summary']['risk_pct']), 55.56)
        root = next(row for row in data['rollup'] if row['grouping'] == 7)
        self.assertEqual(root['students'], 8)
        # Per-offering distinct totals are 9, not the root distinct value 8.
        self.assertEqual(sum(row['students'] for row in data['rollup'] if row['grouping'] == 0), 9)
        aaa = self.load(filters=Filters(module='AAA', presentation='2014J')).tables['summary']
        self.assertEqual((aaa['enrollments'], aaa['at_risk']), (7, 4))
        self.assertAlmostEqual(float(aaa['risk_pct']), 57.14)
        social = self.load(filters=Filters(domain='Social Sciences')).tables['summary']
        self.assertEqual((social['enrollments'], social['risk_pct']), (1, 100))
        attempts = {row['previous_attempts']: row for row in data['attempts']}
        self.assertEqual((attempts[2]['enrollments'], attempts[2]['at_risk']), (2, 2))
        unknown = next(row for row in data['breakdowns']['imd'] if row['label'] == 'Unknown')
        self.assertEqual(unknown['enrollments'], 5)

    def test_registration_known_dates_are_not_withdrawn(self):
        data = self.load('registration').tables
        summary = data['summary']
        self.assertEqual((summary['known_unregistration'], summary['withdrawn'],
                          summary['unknown_unregistration'], summary['na_unregistration']), (6, 3, 1, 2))
        self.assertEqual([row['enrollments'] for row in data['cancellations']], [1, 1, 2, 1, 1])
        self.assertEqual([row['enrollments'] for row in data['registrations']], [1, 3, 2, 2, 1])
        self.assertAlmostEqual(sum(float(row['share_pct']) for row in data['cancellations']), 100, places=1)

    def test_snapshot_zero_click_and_activity_have_different_cohorts(self):
        result = self.load('engagement', Filters(week=0))
        data = result.tables
        self.assertEqual((data['summary']['enrollments'], data['summary']['zero_click']), (5, 2))
        self.assertEqual(data['summary']['zero_click_pct'], 40)
        self.assertAlmostEqual(float(data['summary']['avg_clicks']), 3.2)
        self.assertEqual(result.week_coverage, 4)
        groups = [row for row in data['activity'] if row['grouping'] == 1]
        self.assertEqual(sum(row['clicks'] for row in groups), 23)  # snapshot clicks only 16
        self.assertEqual(sum(row['clicks'] for row in groups), self.conn.execute(
            'SELECT sum(sum_click) FROM dw.fact_vle_daily WHERE day_key BETWEEN 0 AND 6').fetchone()[0])
        filtered = self.load('engagement', Filters(module='AAA', presentation='2014J', week=0)).tables
        self.assertEqual(filtered['summary']['enrollments'], 4)
        self.assertEqual(sum(row['clicks'] for row in filtered['activity'] if row['grouping'] == 1), 19)

    def test_final_full_week_and_unobserved_weeks(self):
        # Day 13 is past length_days=9 but remains the baseline week-1 cutoff.
        data = self.load('engagement', Filters(module='AAA', presentation='2014J', week=1)).tables
        self.assertEqual(data['summary']['enrollments'], 4)
        empty = self.load('engagement', Filters(module='BBB', week=3)).tables['summary']
        self.assertEqual(empty['enrollments'], 0)
        self.assertIsNone(empty['zero_click_pct'])
        self.assertIsNone(empty['avg_clicks'])
        coverage = self.load('signals', Filters(week=7))
        self.assertEqual(coverage.week_coverage, 1)
        self.assertEqual(coverage.tables['summary']['enrollments'], 1)

    def test_assessment_banked_null_zero_late_and_missing_records(self):
        data = self.load('assessments').tables
        detail = {row['id_assessment']: row for row in data['detail']}
        first = detail[11]
        self.assertEqual((first['records'], first['banked'], first['scored'], first['avg_score']), (3, 1, 2, 40))
        self.assertEqual((first['eligible_late'], first['late'], first['late_pct']), (2, 1, 50))
        self.assertEqual(first['below_40_pct'], 50)
        self.assertAlmostEqual(float(first['record_pct']), 42.86)
        missing = detail[13]
        self.assertEqual((missing['records'], missing['record_pct']), (0, 0))
        self.assertIsNone(missing['avg_score'])
        self.assertTrue(missing['is_due_estimated'])
        self.assertFalse(missing['has_recorded_results'])
        self.assertIsNone(detail[15]['record_pct'])  # offering with zero enrollments
        exam = next(row for row in data['by_type'] if row['assessment_type'] == 'Exam')
        self.assertEqual((exam['records'], exam['eligible_late']), (1, 0))
        self.assertIsNone(exam['late_pct'])
        tma = next(row for row in data['by_type'] if row['assessment_type'] == 'TMA')
        self.assertAlmostEqual(float(tma['avg_score']), 46.67)
        self.assertAlmostEqual(float(tma['late_pct']), 33.33)

    def test_signals_use_snapshot_base_and_group_denominators(self):
        data = self.load('signals', Filters(week=0)).tables
        self.assertEqual((data['summary']['enrollments'], data['summary']['risk_pct']), (5, 20))
        self.assertEqual([(row['missed_bucket'], row['enrollments'], row['risk_pct']) for row in data['buckets']],
                         [(0, 2, 0), (1, 2, 0), (2, 1, 100)])

    def test_empty_counts_null_ratios_and_quoted_filter(self):
        empty = self.load(filters=Filters(module='CCC')).tables['summary']
        self.assertEqual(empty['enrollments'], 0)
        self.assertIsNone(empty['risk_pct'])
        self.conn.execute("INSERT INTO dw.dim_offering VALUES (5,%s,'STEM','2015J',2015,10,7,1)", ("A'B",))
        quoted = self.load(filters=Filters(module="A'B")).tables['summary']
        self.assertEqual(quoted['enrollments'], 0)
        with self.assertRaises(service.DashboardError) as error:
            self.load(filters=Filters(module="AAA' OR TRUE --"))
        self.assertEqual(error.exception.code, 'filter')

    def test_gate_latest_status_missing_empty_and_exclusive_lock(self):
        self.conn.execute('INSERT INTO etl.run(status) VALUES (%s)', ('FAILED',))
        with self.assertRaises(service.DashboardError) as error:
            service.load_metadata(self.config)
        self.assertEqual(error.exception.code, 'not_ready')
        self.conn.execute("UPDATE etl.run SET status='RUNNING'")
        with self.assertRaises(service.DashboardError):
            service.load_metadata(self.config)
        self.conn.execute("UPDATE etl.run SET status='SUCCESS'")
        self.conn.execute('SELECT pg_advisory_lock(%s)', (LOCK_ID,))
        try:
            with self.assertRaises(service.DashboardError) as error:
                service.load_metadata(self.config)
            self.assertEqual(error.exception.code, 'busy')
        finally:
            self.conn.execute('SELECT pg_advisory_unlock(%s)', (LOCK_ID,))
        self.conn.execute('DELETE FROM etl.run')
        with self.assertRaises(service.DashboardError) as error:
            service.load_metadata(self.config)
        self.assertEqual(error.exception.code, 'not_ready')
        self.conn.execute('DROP SCHEMA etl CASCADE')
        with self.assertRaises(service.DashboardError) as error:
            service.load_metadata(self.config)
        self.assertEqual(error.exception.code, 'no_run')

    def test_shared_lock_covers_queries_and_fresh_connections(self):
        pids = []
        for _ in range(2):
            with service.read_session(self.config) as (reader, run_id):
                pids.append(reader.info.backend_pid)
                self.assertEqual(reader.execute('SHOW transaction_read_only').fetchone()[0], 'on')
                self.assertFalse(self.conn.execute('SELECT pg_try_advisory_lock(%s)', (LOCK_ID,)).fetchone()[0])
                queries.offerings(reader)
                self.assertFalse(self.conn.execute('SELECT pg_try_advisory_lock(%s)', (LOCK_ID,)).fetchone()[0])
        self.assertNotEqual(pids[0], pids[1])
        self.assertTrue(self.conn.execute('SELECT pg_try_advisory_lock(%s)', (LOCK_ID,)).fetchone()[0])
        self.conn.execute('SELECT pg_advisory_unlock(%s)', (LOCK_ID,))

    def test_query_failure_and_read_only_write_cleanup(self):
        for query in ('SELECT 1/0', "INSERT INTO etl.run(status) VALUES ('FAILED')"):
            with self.assertRaises(service.DashboardError) as error:
                with service.read_session(self.config) as (reader, run_id):
                    reader.execute(query)
            self.assertEqual(error.exception.code, 'query')
            self.assertTrue(self.conn.execute('SELECT pg_try_advisory_lock(%s)', (LOCK_ID,)).fetchone()[0])
            self.conn.execute('SELECT pg_advisory_unlock(%s)', (LOCK_ID,))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM etl.run').fetchone()[0], 1)

    def test_stale_run_is_rejected(self):
        metadata = service.load_metadata(self.config)
        self.conn.execute("INSERT INTO etl.run(status) VALUES ('SUCCESS')")
        with self.assertRaises(service.DashboardError) as error:
            service.load_dashboard('overview', Filters(), metadata.run_id, self.config)
        self.assertEqual(error.exception.code, 'stale_run')

    def test_live_database_guard_prevents_destructive_seed(self):
        # Guard must refuse even a valid *configured* test name if live DB differs.
        with patch.dict(os.environ, {'OULAD_DASHBOARD_TEST_DATABASE': 'oulad_test_dashboard_other'}):
            with self.assertRaises(ValueError):
                seed(self.conn)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM dw.fact_enrollment').fetchone()[0], 9)
