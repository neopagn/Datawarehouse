"""HTTP forwarding only: every figure comes from service.py, nothing is recomputed here."""
from datetime import date, datetime
from decimal import Decimal
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from src.dashboard import service
from src.dashboard.filters import Filters
from src.dss import score


DIST = Path(__file__).resolve().parents[1] / 'frontend' / 'dist'
STATUS_BY_CODE = {'filter': 400, 'stale_run': 409, 'stale_model': 409, 'no_run': 503, 'not_ready': 503, 'busy': 503,
                  'connection': 503, 'timeout': 504}
LOG = logging.getLogger(__name__)

app = FastAPI(title='OULAD DSS API', docs_url=None, redoc_url=None, openapi_url=None)


def encode(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f'Unsupported JSON type: {type(value).__name__}')


def payload_response(content):
    # allow_nan=False: an unobserved value must stay null, never become invalid JSON.
    body = json.dumps(content, default=encode, ensure_ascii=False, allow_nan=False)
    return Response(body, media_type='application/json')


def error_response(status, code, message):
    return JSONResponse({'error': {'code': code, 'message': message}}, status_code=status)


@app.exception_handler(service.DashboardError)
def dashboard_error(_request: Request, error: service.DashboardError):
    return error_response(STATUS_BY_CODE.get(error.code, 500), error.code, str(error))


@app.exception_handler(RequestValidationError)
def invalid_request(_request: Request, _error: RequestValidationError):
    return error_response(400, 'filter', 'Tham số truy vấn không hợp lệ.')


@app.exception_handler(Exception)
def unexpected_error(_request: Request, error: Exception):
    # The cause stays in the server log; clients never see internals.
    LOG.error('Unhandled API error: %s', type(error).__name__, exc_info=error)
    return error_response(500, 'internal', 'Không tải được dữ liệu kho.')


# Sync endpoints: psycopg blocks, so these must run on the worker thread pool.
@app.get('/api/meta')
def meta():
    metadata = service.load_metadata()
    return payload_response({'run_id': metadata.run_id, 'offerings': metadata.offerings})


@app.get('/api/screens/{screen}')
def screen_data(screen: str, domain: str | None = None, module: str | None = None,
                presentation: str | None = None, week: int | None = None,
                expected_run_id: int | None = None):
    data = service.load_dashboard(screen, Filters(domain, module, presentation, week),
                                  expected_run_id=expected_run_id)
    return payload_response({
        'screen': data.screen, 'run_id': data.run_id, 'loaded_at': data.loaded_at,
        'elapsed_seconds': data.elapsed_seconds, 'selected_count': data.selected_count,
        'week_coverage': data.week_coverage, 'tables': data.tables,
    })


@app.get('/api/dss/students')
def dss_students(module: str | None = None, presentation: str | None = None, week: int | None = None,
                 expected_run_id: int | None = None):
    return payload_response(score.load_students(module, presentation, week, expected_run_id))


@app.get('/api/dss/curve')
def dss_curve(module: str | None = None, presentation: str | None = None, week: int | None = None,
              expected_run_id: int | None = None):
    return payload_response(score.load_curve(module, presentation, week, expected_run_id))


@app.get('/api/dss/model')
def dss_model():
    return payload_response(score.load_model())


@app.get('/api/dss/evaluation')
def dss_evaluation():
    return payload_response(score.load_evaluation())


if DIST.is_dir():
    # Mounted last so it can never shadow an /api route.
    app.mount('/', StaticFiles(directory=DIST, html=True), name='frontend')
