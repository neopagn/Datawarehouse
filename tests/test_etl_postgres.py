"""Opt-in integration tests on a disposable oulad_test* database ONLY."""
from contextlib import redirect_stdout
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

import psycopg

from src.etl.pipeline import LOCK_ID, Pipeline, QualityFailure, assert_ready, warehouse_reader
from tests.etl_fixture import write_sources


@unittest.skipUnless(os.environ.get('OULAD_TEST_DATABASE'), 'Set OULAD_TEST_DATABASE=oulad_test* for real PostgreSQL tests')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        name = os.environ['OULAD_TEST_DATABASE']
        if not name.startswith('oulad_test'):
            self.fail('Refusing destructive tests outside an oulad_test* database')
        self.conn = psycopg.connect(dbname=name, autocommit=True, connect_timeout=5)
        self.addCleanup(self.conn.close)
        self.conn.execute('DROP SCHEMA IF EXISTS dw CASCADE; DROP SCHEMA IF EXISTS staging CASCADE; DROP SCHEMA IF EXISTS etl CASCADE;')
        self.tmp = tempfile.TemporaryDirectory(prefix='oulad integration ')
        self.addCleanup(self.tmp.cleanup)
        self.raw = Path(self.tmp.name) / 'raw'
        self.raw.mkdir()
        write_sources(self.raw)
        self.pipeline = Pipeline(self.conn, self.raw, Path(self.tmp.name) / 'evidence')

    def fixture_pipeline(self):
        # The tiny fixture MUST fail original full-OULAD acceptance, never fake a SUCCESS.
        with redirect_stdout(io.StringIO()), self.assertRaises(QualityFailure):
            self.pipeline.run()
        self.assertEqual(self.conn.execute('SELECT status FROM etl.run ORDER BY run_id DESC LIMIT 1').fetchone()[0], 'FAILED')
        self.assertEqual(self.conn.execute("SELECT status FROM etl.job_log WHERE job_id='J13'").fetchone()[0], 'FAILED')

    def test_transformations_and_hand_calculated_snapshots(self):
        self.fixture_pipeline()
        self.assertEqual(self.conn.execute('SELECT count(*) FROM dw.dim_student').fetchone()[0], 5)
        # Regression: freshly loaded small dimensions must have stats before J07/J08.
        self.assertEqual(self.conn.execute("SELECT reltuples FROM pg_class WHERE oid='dw.dim_offering'::regclass").fetchone()[0], 2)
        self.assertEqual(self.conn.execute('SELECT count(DISTINCT id_student) FROM dw.dim_student').fetchone()[0], 4)
        self.assertEqual(self.conn.execute("SELECT imd_band,imd_order,version_no,is_current FROM dw.dim_student WHERE id_student=1 ORDER BY version_no").fetchall(),
                         [('10-20%', 2, 1, False), ('10-20%', 2, 2, True)])
        self.assertEqual(self.conn.execute('SELECT week_no,block_no FROM dw.dim_day WHERE day_key=-1').fetchone(), (-1, -1))
        first = self.conn.execute('SELECT clicks_week,active_days_week,clicks_cum,active_days_cum,days_since_last_activity,submitted_cum,due_cum,missed_cum,avg_score_cum FROM dw.fact_student_week WHERE student_key=1 AND offering_key=1 AND snapshot_day_key=6').fetchone()
        self.assertEqual(first, (9, 1, 11, 2, 6, 1, 1, 0, Decimal('81.00')))
        second = self.conn.execute('SELECT clicks_week,clicks_cum,submitted_cum,due_cum,missed_cum FROM dw.fact_student_week WHERE student_key=1 AND offering_key=1 AND snapshot_day_key=13').fetchone()
        self.assertEqual(second, (5, 16, 2, 2, 0))
        # Late registration starts at day 13; submission day 14 must not cover due work yet.
        third = self.conn.execute('SELECT snapshot_day_key,submitted_cum,missed_cum FROM dw.fact_student_week w JOIN dw.dim_student s USING(student_key) WHERE s.id_student=3').fetchall()
        self.assertEqual(third, [(13, 0, 2)])
        self.assertEqual(self.conn.execute('SELECT count(*) FROM dw.fact_student_week w JOIN dw.dim_student s USING(student_key) WHERE s.id_student=2').fetchone()[0], 0)
        # All source rows and future activity remain in transaction facts/enrollment.
        self.assertEqual(self.conn.execute('SELECT total_clicks,active_days FROM dw.fact_enrollment WHERE student_key=1 AND offering_key=1').fetchone(), (115, 4))
        self.assertEqual(self.conn.execute('SELECT source_rows,sum_click FROM dw.fact_vle_daily WHERE student_key=1 AND site_key=1 AND day_key=0').fetchone(), (2, 5))
        banked = self.conn.execute('SELECT submitted_day_key,days_late,is_after_unregistration FROM dw.fact_assessment f JOIN dw.dim_student s USING(student_key) WHERE s.id_student=2').fetchone()
        self.assertEqual(banked, (-9998, None, True))  # Explicit legacy compatibility, not a new event.
        self.assertEqual(self.conn.execute('SELECT unregistration_day_key FROM dw.fact_enrollment e JOIN dw.dim_student s USING(student_key) WHERE s.id_student=4').fetchone()[0], -9999)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM etl.check_result WHERE check_name LIKE \'integrity:%\' AND NOT passed').fetchone()[0], 0)
        result = json.loads((self.pipeline.evidence_dir / str(self.pipeline.run_id) / 'result.json').read_text(encoding='utf-8'))
        self.assertEqual(result['status'], 'FAILED')
        self.assertGreaterEqual(len(result['checks']), 29)

    def test_null_score_zero_weight_exam_and_no_activity(self):
        self.fixture_pipeline()
        self.assertEqual(self.conn.execute('SELECT weighted_points,days_late FROM dw.fact_assessment WHERE student_key=1 AND assessment_key=1').fetchone(), (Decimal('10.12'), 1))
        self.assertEqual(self.conn.execute('SELECT avg_coursework_score,weighted_coursework_score,submitted_count FROM dw.fact_enrollment WHERE student_key=1 AND offering_key=1').fetchone(), (Decimal('81.00'), Decimal('80.96'), 2))
        self.assertEqual(self.conn.execute('SELECT days_late,is_late FROM dw.fact_assessment WHERE assessment_key=3').fetchone(), (None, None))
        self.assertEqual(self.conn.execute('SELECT weighted_coursework_score FROM dw.fact_enrollment e JOIN dw.dim_student s USING(student_key) WHERE s.id_student=3').fetchone(), (None,))
        self.assertEqual(self.conn.execute('SELECT clicks_week,clicks_cum,days_since_last_activity FROM dw.fact_student_week WHERE student_key=2 ORDER BY snapshot_day_key').fetchall(), [(0, 0, None), (0, 0, None)])
        self.assertEqual(self.conn.execute('SELECT submitted_cum,missed_cum,avg_score_cum FROM dw.fact_student_week w JOIN dw.dim_student s USING(student_key) WHERE s.id_student=4 AND snapshot_day_key=6').fetchone(), (0, 0, None))

    def test_registration_and_unregistration_exactly_at_cutoff(self):
        self.fixture_pipeline()
        self.conn.execute('UPDATE dw.fact_enrollment SET registration_day_key=13 WHERE student_key=1 AND offering_key=1')
        self.conn.execute('TRUNCATE dw.fact_student_week')
        self.pipeline.execute_file('etl_mau/j10_fact_student_week.sql')
        self.assertEqual(self.conn.execute('SELECT snapshot_day_key FROM dw.fact_student_week WHERE student_key=1 AND offering_key=1').fetchall(), [(13,)])
        self.conn.execute('UPDATE dw.fact_enrollment SET unregistration_day_key=13 WHERE student_key=1 AND offering_key=1')
        self.conn.execute('TRUNCATE dw.fact_student_week')
        self.pipeline.execute_file('etl_mau/j10_fact_student_week.sql')
        self.assertEqual(self.conn.execute('SELECT count(*) FROM dw.fact_student_week WHERE student_key=1 AND offering_key=1').fetchone()[0], 0)

    def test_csv_type_error_rolls_back_J02(self):
        self.fixture_pipeline()
        with (self.raw / 'studentVle.csv').open('a', encoding='utf-8') as stream:
            stream.write('\"AAA\",\"2013J\",\"1\",\"100\",\"0\",\"bad-int\"\\n')
        with redirect_stdout(io.StringIO()), self.assertRaises(psycopg.errors.InvalidTextRepresentation):
            Pipeline(self.conn, self.raw, self.pipeline.evidence_dir).run()
        self.assertEqual(self.conn.execute('SELECT count(*) FROM dw.fact_enrollment').fetchone()[0], 5)
        self.assertEqual(self.conn.execute("SELECT status FROM etl.job_log WHERE run_id=2 AND job_id='J02'").fetchone()[0], 'FAILED')

    def test_failed_gate_is_durable_and_rerun_keeps_history(self):
        self.fixture_pipeline()
        first = self.pipeline.run_id
        with redirect_stdout(io.StringIO()), self.assertRaises(QualityFailure):
            Pipeline(self.conn, self.raw, self.pipeline.evidence_dir).run()
        self.assertEqual(self.conn.execute('SELECT count(*) FROM etl.run').fetchone()[0], 2)
        # Four baseline checks also hold for this tiny fixture: day/result dimensions,
        # missed<=due, and no snapshot after a recorded cancellation. Other 25 fail.
        self.assertEqual(self.conn.execute('SELECT count(*) FROM etl.check_result WHERE run_id=%s AND NOT passed', (first,)).fetchone()[0], 25)
        with self.assertRaises(RuntimeError):
            assert_ready(self.conn)

    def test_header_failure_preserves_existing_dw(self):
        self.fixture_pipeline()
        before = self.conn.execute('SELECT count(*) FROM dw.fact_vle_daily').fetchone()[0]
        (self.raw / 'courses.csv').write_text('wrong\n', encoding='utf-8')
        with redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            Pipeline(self.conn, self.raw, self.pipeline.evidence_dir).run()
        self.assertEqual(self.conn.execute('SELECT count(*) FROM dw.fact_vle_daily').fetchone()[0], before)
        self.assertEqual(self.conn.execute('SELECT job_id,status FROM etl.job_log WHERE run_id=2').fetchall(), [('J01', 'FAILED')])

    def test_source_offering_mismatch_rolls_back_J02(self):
        self.fixture_pipeline()
        before = self.conn.execute('SELECT sum(sum_click) FROM dw.fact_vle_daily').fetchone()[0]
        with (self.raw / 'studentVle.csv').open('a', encoding='utf-8') as stream:
            stream.write('"AAA","2014J","1","100","0","1"\n')
        with redirect_stdout(io.StringIO()), self.assertRaises(QualityFailure):
            Pipeline(self.conn, self.raw, self.pipeline.evidence_dir).run()
        self.assertEqual(self.conn.execute('SELECT sum(sum_click) FROM dw.fact_vle_daily').fetchone()[0], before)
        self.assertEqual(self.conn.execute("SELECT passed FROM etl.check_result WHERE run_id=2 AND check_name='source: VLE wrong offering or enrollment'").fetchone(), (False,))

    def test_job_rollback_and_null_check(self):
        self.pipeline.bootstrap()
        self.pipeline.run_id = self.conn.execute('INSERT INTO etl.run DEFAULT VALUES RETURNING run_id').fetchone()[0]
        self.conn.execute('CREATE SCHEMA dw; CREATE TABLE dw.test_transaction (value int)')
        def fail():
            self.conn.execute('INSERT INTO dw.test_transaction VALUES (1)')
            self.conn.execute('SELECT 1/0')
        with redirect_stdout(io.StringIO()), self.assertRaises(psycopg.errors.DivisionByZero):
            self.pipeline.run_job('J99', 'dw.test_transaction', fail)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM dw.test_transaction').fetchone()[0], 0)
        path = Path(self.tmp.name) / 'null_check.sql'
        path.write_text("SELECT 'null test', 1::bigint, NULL::bigint, NULL::boolean", encoding='utf-8')
        with redirect_stdout(io.StringIO()), self.assertRaises(QualityFailure):
            self.pipeline.run_job('J98', 'quality', lambda: self.pipeline.quality(path))
        self.assertEqual(self.conn.execute("SELECT actual,passed FROM etl.check_result WHERE check_name='null test'").fetchone(), (None, False))

    def test_locks_and_readiness_states(self):
        self.pipeline.bootstrap()
        with self.assertRaises(RuntimeError):
            assert_ready(self.conn)
        # Test readiness's state machine with explicit log fixtures, not fake ETL data.
        self.conn.execute("INSERT INTO etl.run(status) VALUES ('SUCCESS')")
        with warehouse_reader(self.conn) as run_id:
            self.assertEqual(run_id, 1)
            with psycopg.connect(dbname=os.environ['OULAD_TEST_DATABASE'], autocommit=True) as other:
                with self.assertRaises(RuntimeError):
                    Pipeline(other, self.raw, self.pipeline.evidence_dir).run()
        self.conn.execute("INSERT INTO etl.run(status) VALUES ('RUNNING')")
        with self.assertRaises(RuntimeError):
            assert_ready(self.conn)
        with psycopg.connect(dbname=os.environ['OULAD_TEST_DATABASE'], autocommit=True) as other:
            other.execute('SELECT pg_advisory_lock(%s)', (LOCK_ID,))
            with self.assertRaises(RuntimeError):
                with warehouse_reader(self.conn):
                    self.fail('Reader must not run during reload')
        self.conn.execute("UPDATE etl.run SET status='FAILED' WHERE run_id=2")
        with self.assertRaises(RuntimeError):
            assert_ready(self.conn)

    def test_missing_baseline_check_cannot_be_hidden_by_extra_checks(self):
        root = Path(self.tmp.name) / 'sql'
        (root / 'etl').mkdir(parents=True)
        (root / '03_kiem_tra_sau_nap.sql').write_text("SELECT 'baseline '||n, 1, 1, true FROM generate_series(1,28) n", encoding='utf-8')
        (root / 'etl/check_dw_integrity.sql').write_text("SELECT 'extra '||n, 1, 1, true FROM generate_series(1,11) n", encoding='utf-8')
        pipeline = Pipeline(self.conn, self.raw, self.pipeline.evidence_dir, sql_root=root)
        with self.assertRaisesRegex(QualityFailure, 'missing baseline checks'):
            pipeline.final_quality()

    def test_incompatible_log_schema_is_not_silently_repaired(self):
        self.conn.execute('CREATE SCHEMA etl; CREATE TABLE etl.run (run_id bigint PRIMARY KEY)')
        with self.assertRaisesRegex(ValueError, 'Incompatible ETL log columns'):
            self.pipeline.bootstrap()
        self.assertEqual(self.conn.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='etl' AND table_name='run'").fetchone()[0], 1)

    def test_interrupted_run_recovered_under_lock(self):
        self.pipeline.bootstrap()
        self.conn.execute('INSERT INTO etl.run DEFAULT VALUES')
        self.conn.execute("INSERT INTO etl.job_log(run_id,job_id,started_at,status) VALUES (1,'J02',now(),'RUNNING')")
        with redirect_stdout(io.StringIO()), self.assertRaises(QualityFailure):
            self.pipeline.run()
        self.assertEqual(self.conn.execute('SELECT status FROM etl.run WHERE run_id=1').fetchone()[0], 'FAILED')
        self.assertEqual(self.conn.execute('SELECT status FROM etl.job_log WHERE run_id=1').fetchone()[0], 'FAILED')


if __name__ == '__main__':
    unittest.main()
