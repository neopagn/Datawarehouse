"""One transaction per job; persistent log outside data transactions."""
from contextlib import contextmanager
import json
from pathlib import Path
import time

import psycopg
from psycopg import sql

from .source import copy_sources, validate_sources

SQL_ROOT = Path(__file__).resolve().parents[1] / 'sql'
LOCK_ID = 4031261  # All pipeline/readiness users must use this database-local key.
JOBS = (
    ('J03', 'etl_mau/j03_dim_student.sql', ('dim_student',)),
    ('J04', 'etl/j04_dim_offering.sql', ('dim_offering',)),
    ('J05', 'etl/j05_day_result.sql', ('dim_day', 'dim_result')),
    ('J06', 'etl/j06_assessment_site.sql', ('dim_assessment', 'dim_vle_site')),
    ('J07', 'etl/j07_fact_assessment.sql', ('fact_assessment',)),
    ('J08', 'etl_mau/j08_fact_vle_daily.sql', ('fact_vle_daily',)),
    ('J09', 'etl/j09_fact_enrollment.sql', ('fact_enrollment',)),
    ('J10', 'etl_mau/j10_fact_student_week.sql', ('fact_student_week',)),
    ('J11', 'etl/j11_refresh_aggregate.sql', ('agg_vle_offering_week_activity',)),
    ('J12', 'etl/j12_analyze.sql', ()),
)


class QualityFailure(RuntimeError):
    pass


def safe_error(exc: BaseException) -> str:
    """Never stringify a connection exception/DSN or COPY's source-row detail."""
    if isinstance(exc, psycopg.Error):
        primary = exc.diag.message_primary
        return f'{type(exc).__name__}: {primary or "database operation failed"} (SQLSTATE {exc.sqlstate})'
    if isinstance(exc, (ValueError, QualityFailure)):
        return str(exc)
    return type(exc).__name__


def assert_ready(conn) -> int:
    """Call while holding a shared advisory lock for the entire consumer read."""
    exists = conn.execute("SELECT to_regclass('etl.run')").fetchone()[0]
    if exists is None:
        raise RuntimeError('DW unavailable: no ETL run')
    row = conn.execute('SELECT run_id, status FROM etl.run ORDER BY run_id DESC LIMIT 1').fetchone()
    if row is None or row[1] != 'SUCCESS':
        raise RuntimeError('DW unavailable: latest ETL run is not SUCCESS')
    return row[0]


@contextmanager
def warehouse_reader(conn):
    """Hold the shared lock throughout all dashboard/DSS queries, not just status."""
    if not conn.autocommit:
        raise ValueError('Readiness requires an autocommit connection')
    acquired = conn.execute('SELECT pg_try_advisory_lock_shared(%s)', (LOCK_ID,)).fetchone()[0]
    if not acquired:
        raise RuntimeError('DW unavailable: ETL holds the warehouse lock')
    try:
        yield assert_ready(conn)
    finally:
        conn.execute('SELECT pg_advisory_unlock_shared(%s)', (LOCK_ID,))


class Pipeline:
    def __init__(self, conn, raw_dir, evidence_dir=Path('work/etl-runs'), sql_root=SQL_ROOT):
        if not conn.autocommit:
            raise ValueError('Pipeline requires an autocommit connection')
        self.conn = conn
        self.raw_dir = Path(raw_dir)
        self.evidence_dir = Path(evidence_dir)
        self.sql_root = Path(sql_root)
        self.run_id = None
        self.checks = []
        self.job_results = []

    def execute_file(self, relative):
        self.conn.execute((self.sql_root / relative).read_text(encoding='utf-8'))

    def bootstrap(self):
        # A pre-existing but incompatible log schema must not be silently repaired.
        expected = {
            'run': ('run_id', 'started_at', 'finished_at', 'status'),
            'job_log': ('run_id', 'job_id', 'target_table', 'started_at', 'finished_at', 'rows_written', 'status', 'message'),
            'check_result': ('run_id', 'check_name', 'expected', 'actual', 'passed'),
        }
        with self.conn.transaction():
            self.execute_file('etl/00_bootstrap_log.sql')
            for table, columns in expected.items():
                actual = self.conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='etl' AND table_name=%s ORDER BY ordinal_position",
                    (table,),
                ).fetchall()
                if tuple(row[0] for row in actual) != columns:
                    raise ValueError(f'Incompatible ETL log columns: {table}')
                primary = self.conn.execute(
                    "SELECT count(*) FROM pg_constraint WHERE conrelid=%s::regclass AND contype='p'",
                    (f'etl.{table}',),
                ).fetchone()[0]
                if primary != 1:
                    raise ValueError(f'Missing primary key: etl.{table}')

    def record_checks(self):
        if not self.checks:
            return
        with self.conn.transaction(), self.conn.cursor() as cursor:
            cursor.executemany(
                'INSERT INTO etl.check_result VALUES (%s,%s,%s,%s,%s) '
                'ON CONFLICT (run_id,check_name) DO UPDATE SET expected=EXCLUDED.expected, actual=EXCLUDED.actual, passed=EXCLUDED.passed',
                [(self.run_id, name, expected, actual, passed is True)
                 for name, expected, actual, passed in self.checks],
            )

    def quality(self, relative):
        rows = self.conn.execute((self.sql_root / relative).read_text(encoding='utf-8')).fetchall()
        self.checks.extend(rows)
        if not rows or any(row[3] is not True for row in rows):
            failures = [row[0] for row in rows if row[3] is not True]
            raise QualityFailure(f'Quality gate failed: {", ".join(failures) or "empty check set"}')
        return rows

    def count_tables(self, tables):
        return {table: self.conn.execute(sql.SQL('SELECT count(*) FROM dw.{}').format(sql.Identifier(table))).fetchone()[0]
                for table in tables}

    def run_job(self, job_id, target, action):
        self.conn.execute(
            "INSERT INTO etl.job_log (run_id,job_id,target_table,started_at,status) VALUES (%s,%s,%s,clock_timestamp(),'RUNNING')",
            (self.run_id, job_id, target),
        )
        start = time.monotonic()
        print(f'{job_id} RUNNING', flush=True)
        try:
            with self.conn.transaction():
                counts = action() or {}
        except BaseException as exc:
            # Data transaction has rolled back before these durable log writes.
            self.record_checks()
            message = safe_error(exc)
            self.conn.execute(
                "UPDATE etl.job_log SET status='FAILED',finished_at=clock_timestamp(),message=%s WHERE run_id=%s AND job_id=%s",
                (message, self.run_id, job_id),
            )
            self.job_results.append({'job': job_id, 'status': 'FAILED', 'message': message})
            raise
        self.record_checks()
        elapsed = round(time.monotonic() - start, 3)
        message = json.dumps({'rows': counts, 'seconds': elapsed}, ensure_ascii=False)
        self.conn.execute(
            "UPDATE etl.job_log SET status='SUCCESS',finished_at=clock_timestamp(),rows_written=%s,message=%s WHERE run_id=%s AND job_id=%s",
            (sum(counts.values()), message, self.run_id, job_id),
        )
        self.job_results.append({'job': job_id, 'status': 'SUCCESS', 'rows': counts, 'seconds': elapsed})
        print(f'{job_id} SUCCESS {counts} ({elapsed}s)', flush=True)

    def load_staging(self):
        self.execute_file('00_ddl_staging.sql')
        self.execute_file('01_ddl_dw.sql')
        counts = copy_sources(self.conn, self.raw_dir)
        self.execute_file('etl/prepare_staging.sql')
        self.quality('etl/check_source_integrity.sql')
        return counts

    def transform(self, filename, tables):
        self.execute_file(filename)
        # Downstream joins run before J12. Small dimensions may never reach the
        # auto-analyze threshold; stale estimates caused multi-million nested loops.
        for table in tables:
            self.conn.execute(sql.SQL('ANALYZE dw.{}').format(sql.Identifier(table)))
        return self.count_tables(tables)

    def final_quality(self):
        # Fetch both sets BEFORE evaluating, so evidence includes every check.
        baseline = self.conn.execute((self.sql_root / '03_kiem_tra_sau_nap.sql').read_text(encoding='utf-8')).fetchall()
        integrity = self.conn.execute((self.sql_root / 'etl/check_dw_integrity.sql').read_text(encoding='utf-8')).fetchall()
        rows = baseline + integrity
        self.checks.extend(rows)
        if len(baseline) != 29 or not integrity or any(row[3] is not True for row in rows):
            failed = [row[0] for row in rows if row[3] is not True]
            raise QualityFailure(f'Quality gate failed: {", ".join(failed) or "missing baseline checks"}')
        return {'checks': len(rows)}

    def save_evidence(self, status):
        target = self.evidence_dir / str(self.run_id)
        target.mkdir(parents=True, exist_ok=False)
        result = {
            'run_id': self.run_id, 'status': status,
            'postgresql_version': self.conn.info.server_version,
            'psycopg_version': psycopg.__version__,
            'jobs': self.job_results,
            # PostgreSQL SUM(bigint) returns NUMERIC/Decimal even for integer counts.
            'checks': [{'check_name': name, 'expected': int(expected),
                        'actual': None if actual is None else int(actual), 'passed': passed is True}
                       for name, expected, actual, passed in self.checks],
        }
        (target / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    def run(self):
        acquired = self.conn.execute('SELECT pg_try_advisory_lock(%s)', (LOCK_ID,)).fetchone()[0]
        if not acquired:
            raise RuntimeError('Another ETL run or consumer holds the warehouse lock')
        try:
            self.bootstrap()
            with self.conn.transaction():
                self.conn.execute("UPDATE etl.job_log SET status='FAILED',finished_at=clock_timestamp(),message='Previous process interrupted' WHERE status='RUNNING'")
                self.conn.execute("UPDATE etl.run SET status='FAILED',finished_at=clock_timestamp() WHERE status='RUNNING'")
                self.run_id = self.conn.execute('INSERT INTO etl.run DEFAULT VALUES RETURNING run_id').fetchone()[0]
            print(f'ETL run_id={self.run_id}', flush=True)
            try:
                self.run_job('J01', 'source CSV headers', lambda: validate_sources(self.raw_dir))
                self.run_job('J02', 'staging.*, dw DDL', self.load_staging)
                for job_id, filename, tables in JOBS:
                    target = ', '.join(tables) or 'dw statistics'
                    self.run_job(job_id, target, lambda f=filename, t=tables: self.transform(f, t))
                self.run_job('J13', 'etl.check_result', self.final_quality)
                # Evidence must be written before publishing SUCCESS.
                self.save_evidence('SUCCESS')
                self.conn.execute("UPDATE etl.run SET status='SUCCESS',finished_at=clock_timestamp() WHERE run_id=%s", (self.run_id,))
            except BaseException:
                self.conn.execute("UPDATE etl.run SET status='FAILED',finished_at=clock_timestamp() WHERE run_id=%s", (self.run_id,))
                if not (self.evidence_dir / str(self.run_id)).exists():
                    self.save_evidence('FAILED')
                raise
            return self.run_id
        finally:
            self.conn.execute('SELECT pg_advisory_unlock(%s)', (LOCK_ID,))
