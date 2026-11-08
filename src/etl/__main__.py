"""Run from the repository root: python -m src.etl --help."""
import argparse
import os
from pathlib import Path
import re
import sys


def parser():
    result = argparse.ArgumentParser(description='OULAD J01-J13 SQL full reload (requires a dedicated oulad_* database).')
    result.add_argument('--raw-dir', type=Path, help='Directory containing the seven original OULAD CSV files')
    result.add_argument('--database', required=True, help='Dedicated database, e.g. oulad_dw (never postgres/template databases)')
    result.add_argument('--host', default=os.environ.get('PGHOST', '127.0.0.1'))
    result.add_argument('--port', type=int, default=os.environ.get('PGPORT', '5432'))
    result.add_argument('--user', default=os.environ.get('PGUSER'))
    result.add_argument('--allow-full-reload', action='store_true', help='Explicitly allow replacement of staging and dw, keeping etl history')
    result.add_argument('--check-ready', action='store_true', help='Read-only availability check; does not reload')
    result.add_argument('--evidence-dir', type=Path, default=Path('work/etl-runs'))
    return result


def main(argv=None):
    args_parser = parser()
    args = args_parser.parse_args(argv)
    if not re.fullmatch(r'oulad_[A-Za-z0-9_]+', args.database):
        args_parser.error('--database must be a dedicated database named oulad_*')
    if not args.check_ready and (args.raw_dir is None or not args.allow_full_reload):
        args_parser.error('reload requires --raw-dir and --allow-full-reload')
    # Import the DB driver only after argument validation (including --help).
    import psycopg
    from .pipeline import Pipeline, safe_error, warehouse_reader

    options = {'host': args.host, 'port': args.port, 'dbname': args.database, 'autocommit': True, 'connect_timeout': 10}
    if args.user:
        options['user'] = args.user
    try:
        with psycopg.connect(**options) as conn:
            if args.check_ready:
                with warehouse_reader(conn) as run_id:
                    print(f'DW READY run_id={run_id}')
            else:
                run_id = Pipeline(conn, args.raw_dir, args.evidence_dir / args.database).run()
                print(f'ETL SUCCESS run_id={run_id}')
        return 0
    except KeyboardInterrupt:
        print('ETL interrupted; inspect latest run before using DW.', file=sys.stderr)
        return 130
    except Exception as exc:
        # Runtime errors here are application-controlled, never raw connection strings.
        message = str(exc) if type(exc) is RuntimeError else safe_error(exc)
        print(f'ETL FAILED: {message}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
