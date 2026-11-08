"""Opt-in leakage proof on a disposable oulad_test_dashboard[_suffix] database only."""
import os
import unittest

from src.dss import queries
from tests.dashboard_fixture import seed, test_config


OFFERING = 1
WEEK = 1


@unittest.skipUnless(os.environ.get('OULAD_DASHBOARD_TEST_DATABASE'), 'Set OULAD_DASHBOARD_TEST_DATABASE for disposable PostgreSQL tests')
class FeatureLeakageTests(unittest.TestCase):
    def setUp(self):
        self.conn = test_config().connect()
        self.addCleanup(self.conn.close)
        seed(self.conn)

    def inputs(self):
        return queries.feature_rows(self.conn, [OFFERING], WEEK)

    def test_rows_and_lagged_score_come_from_the_expected_snapshots(self):
        self.conn.execute("""
            UPDATE dw.fact_student_week SET avg_score_cum = 11 WHERE snapshot_day_key = 6 AND student_key = 1 AND offering_key = 1;
        """)
        rows = {row['student_key']: row for row in queries.rows(self.conn, queries.FEATURE_ROWS, {
            'offering_keys': [OFFERING], 'cutoff': 13, 'lag': 7})}
        self.assertEqual(sorted(rows), [1, 4, 7, 9])
        self.assertEqual((rows[1]['score_now'], rows[1]['score_lagged']), (50, 11))

    def test_outcome_change_leaves_every_input_unchanged(self):
        before = self.inputs()
        self.conn.execute('UPDATE dw.fact_enrollment SET result_key = 5 - result_key')
        self.assertEqual(self.inputs(), before)

    def test_later_activity_leaves_every_input_unchanged(self):
        before = self.inputs()
        self.conn.execute("""
            INSERT INTO dw.fact_student_week
            SELECT student_key, offering_key, snapshot_day_key + 7, 999, 7, 999, 99, 0, 9, 9, 0, 100
            FROM dw.fact_student_week WHERE snapshot_day_key = 13 AND offering_key = 1;
            UPDATE dw.fact_enrollment SET total_clicks = 999999, submitted_count = 99, avg_coursework_score = 1;
        """)
        self.assertEqual(self.inputs(), before)


if __name__ == '__main__':
    unittest.main()
