"""Lifecycle/error unit tests. Real SQL/concurrency lives in test_dashboard_postgres."""
from contextlib import contextmanager
import unittest
from unittest.mock import patch

import psycopg

from src.dashboard import service
from src.dashboard.filters import Filters
from tests.test_dashboard_filters import OFFERINGS


class FakeConnection:
    def __init__(self, trace):
        self.trace = trace

    def __enter__(self):
        self.trace.append('connect')
        return self

    def __exit__(self, *exc):
        self.trace.append('close')

    @contextmanager
    def transaction(self):
        self.trace.append('begin')
        try:
            yield
        except BaseException:
            self.trace.append('rollback')
            raise
        else:
            self.trace.append('commit')

    def execute(self, query):
        self.trace.append(query)


class ServiceTests(unittest.TestCase):
    def contexts(self, gate_error=None):
        trace = []
        conn = FakeConnection(trace)

        @contextmanager
        def gate(connection):
            self.assertIs(connection, conn)
            trace.append('lock')
            try:
                if gate_error:
                    raise RuntimeError(gate_error)
                yield 5
            finally:
                trace.append('unlock')

        return trace, conn, gate

    def test_atomic_load_lifecycle_and_read_only_settings(self):
        trace, conn, gate = self.contexts()
        with patch.object(service.DatabaseConfig, 'connect', return_value=conn), \
                patch.object(service, 'warehouse_reader', gate), \
                patch.object(service.queries, 'offerings', return_value=OFFERINGS), \
                patch.dict(service.queries.LOADERS, overview=lambda c, p: {'params': p}):
            result = service.load_dashboard('overview', Filters(module='AAA'), 5, service.DatabaseConfig())
        self.assertEqual(result.tables['params']['offering_keys'], [1, 3])
        self.assertEqual(result.run_id, 5)
        self.assertEqual(trace[:3], ['connect', 'lock', 'begin'])
        self.assertIn('READ ONLY', trace[3])
        self.assertEqual(trace[-3:], ['commit', 'unlock', 'close'])

    def test_query_failure_rolls_back_before_unlock_and_sanitizes(self):
        trace, conn, gate = self.contexts()

        def fail(*args):
            raise psycopg.errors.DivisionByZero('private server details must not appear')

        with patch.object(service.DatabaseConfig, 'connect', return_value=conn), \
                patch.object(service, 'warehouse_reader', gate), \
                patch.object(service.queries, 'offerings', return_value=OFFERINGS), \
                patch.dict(service.queries.LOADERS, overview=fail):
            with self.assertRaises(service.DashboardError) as error:
                service.load_dashboard('overview', Filters())
        self.assertEqual(error.exception.code, 'query')
        self.assertNotIn('private', str(error.exception))
        self.assertEqual(trace[-3:], ['rollback', 'unlock', 'close'])

    def test_changed_run_blocks_loader(self):
        trace, conn, gate = self.contexts()
        with patch.object(service.DatabaseConfig, 'connect', return_value=conn), \
                patch.object(service, 'warehouse_reader', gate), \
                patch.object(service.queries, 'offerings') as query:
            with self.assertRaises(service.DashboardError) as error:
                service.load_dashboard('overview', Filters(), expected_run_id=4)
            query.assert_not_called()
        self.assertEqual(error.exception.code, 'stale_run')
        self.assertEqual(trace[-3:], ['rollback', 'unlock', 'close'])

    def test_gate_messages_and_unknown_exception_are_not_exposed(self):
        for message, code in [(key, value[0]) for key, value in service._GATE_ERRORS.items()] + [('secret details', 'query')]:
            trace, conn, gate = self.contexts(message)
            with patch.object(service.DatabaseConfig, 'connect', return_value=conn), \
                    patch.object(service, 'warehouse_reader', gate):
                with self.assertRaises(service.DashboardError) as error:
                    service.load_metadata()
            self.assertEqual(error.exception.code, code)
            self.assertNotIn('secret', str(error.exception))
            self.assertEqual(trace[-2:], ['unlock', 'close'])

    def test_connection_and_timeout_messages(self):
        for exception, code in ((psycopg.OperationalError('private'), 'connection'),
                                (psycopg.errors.QueryCanceled('private'), 'timeout')):
            with patch.object(service.DatabaseConfig, 'connect', side_effect=exception):
                with self.assertRaises(service.DashboardError) as error:
                    service.load_metadata()
            self.assertEqual(error.exception.code, code)
            self.assertNotIn('private', str(error.exception))

    def test_environment_config_validation(self):
        for overrides in ({'PGPORT': 'no'}, {'PGPORT': '0'}, {'PGDATABASE': 'postgres'}):
            with patch.dict('os.environ', overrides):
                with self.assertRaises(service.DashboardError) as error:
                    service.DatabaseConfig.from_env()
                self.assertEqual(error.exception.code, 'config')

    def test_disposable_database_names_are_guarded_before_connecting(self):
        from tests.dashboard_fixture import test_config
        for name in ('', 'oulad_dw', 'postgres', 'oulad_test_dashboard-other'):
            with patch.dict('os.environ', {'OULAD_DASHBOARD_TEST_DATABASE': name}):
                with self.assertRaises(ValueError):
                    test_config()
        with patch.dict('os.environ', {'OULAD_DASHBOARD_TEST_DATABASE': 'oulad_test_dashboard_local'}):
            self.assertEqual(test_config().database, 'oulad_test_dashboard_local')

    def test_invalid_filter_does_not_invoke_loader(self):
        trace, conn, gate = self.contexts()
        with patch.object(service.DatabaseConfig, 'connect', return_value=conn), \
                patch.object(service, 'warehouse_reader', gate), \
                patch.object(service.queries, 'offerings', return_value=OFFERINGS):
            with self.assertRaises(service.DashboardError) as error:
                service.load_dashboard('overview', Filters(module='invalid'))
        self.assertEqual(error.exception.code, 'filter')
        self.assertEqual(trace[-3:], ['rollback', 'unlock', 'close'])
