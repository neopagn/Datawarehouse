"""Atomic read-only loads, readiness protection and sanitized public errors."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
import re
import time

import psycopg

from src.etl.pipeline import warehouse_reader
from . import queries
from .filters import FilterError, Filters, SCREENS, validate


class DashboardError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, repr=False)
class DatabaseConfig:
    # No password field, DSN or credential file is read/logged by this module.
    host: str = '127.0.0.1'
    port: int = 55432
    database: str = 'oulad_dw'
    user: str = 'oulad_local'

    @classmethod
    def from_env(cls):
        try:
            port = int(os.environ.get('PGPORT', '55432'))
        except ValueError:
            raise DashboardError('config', 'PGPORT phải là một số cổng hợp lệ.') from None
        database = os.environ.get('PGDATABASE', 'oulad_dw')
        if not 1 <= port <= 65535 or not re.fullmatch(r'oulad_[A-Za-z0-9_]+', database):
            raise DashboardError('config', 'Cấu hình cần cổng hợp lệ và database riêng tên oulad_*.')
        return cls(os.environ.get('PGHOST', '127.0.0.1'), port, database,
                   os.environ.get('PGUSER', 'oulad_local'))

    def connect(self):
        return psycopg.connect(host=self.host, port=self.port, dbname=self.database,
                               user=self.user, autocommit=True, connect_timeout=5,
                               options='-c statement_timeout=15000', application_name='oulad_dashboard')


@dataclass(frozen=True)
class Metadata:
    run_id: int
    offerings: list[dict]


@dataclass(frozen=True)
class DashboardData:
    screen: str
    filters: Filters
    run_id: int
    loaded_at: datetime
    elapsed_seconds: float
    selected_count: int
    week_coverage: int | None
    tables: dict = field(repr=False)


_GATE_ERRORS = {
    'DW unavailable: no ETL run': ('no_run', 'Kho chưa có nhật ký ETL để xác nhận sẵn sàng.'),
    'DW unavailable: latest ETL run is not SUCCESS': (
        'not_ready', 'Kho chưa sẵn sàng: lần ETL mới nhất chưa SUCCESS (hoặc chưa có lần chạy).'),
    'DW unavailable: ETL holds the warehouse lock': (
        'busy', 'Kho đang được ETL sử dụng. Hãy thử lại sau khi ETL hoàn tất.'),
}


@contextmanager
def read_session(config=None):
    """Rollback before gate unlock; always close this load's private connection."""
    try:
        config = config or DatabaseConfig.from_env()
        with config.connect() as conn:
            with warehouse_reader(conn) as run_id:
                with conn.transaction():
                    conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                    conn.execute("SET LOCAL statement_timeout = '15s'")
                    yield conn, run_id
    except DashboardError:
        raise
    except FilterError as exc:
        raise DashboardError('filter', str(exc)) from None
    except psycopg.errors.QueryCanceled:
        raise DashboardError('timeout', 'Truy vấn vượt thời gian cho phép. Hãy thu hẹp bộ lọc và thử lại.') from None
    except psycopg.OperationalError:
        raise DashboardError('connection', 'Không kết nối được PostgreSQL. Hãy kiểm tra server và cấu hình kết nối.') from None
    except psycopg.Error:
        raise DashboardError('query', 'Không đọc được dữ liệu kho. Hãy kiểm tra schema/quyền và nhật ký vận hành.') from None
    except RuntimeError as exc:
        code, message = _GATE_ERRORS.get(str(exc), ('query', 'Không tải được dữ liệu kho.'))
        raise DashboardError(code, message) from None


def load_metadata(config=None):
    with read_session(config) as (conn, run_id):
        result = Metadata(run_id, queries.offerings(conn))
    return result


def load_dashboard(screen, filters, expected_run_id=None, config=None):
    if screen not in SCREENS:
        raise DashboardError('filter', 'Màn hình không hợp lệ.')
    started = time.perf_counter()
    with read_session(config) as (conn, run_id):
        if expected_run_id is not None and run_id != expected_run_id:
            raise DashboardError('stale_run', 'Kho đã được nạp lại. Hãy thử lại để cập nhật bộ lọc theo lần ETL mới.')
        selected = validate(queries.offerings(conn), filters, screen)
        params = {'offering_keys': [row['offering_key'] for row in selected],
                  'week': filters.week, 'cutoff': None if filters.week is None else 7 * filters.week + 6}
        tables = queries.LOADERS[screen](conn, params)
    coverage = None if filters.week is None else sum(row['length_weeks'] > filters.week for row in selected)
    return DashboardData(screen, filters, run_id, datetime.now(timezone.utc), time.perf_counter() - started,
                         len(selected), coverage, tables)
