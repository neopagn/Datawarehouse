"""Run from repo root: python -m src.api. Loopback only; the app has no authentication."""
import uvicorn


if __name__ == '__main__':
    uvicorn.run('src.api.app:app', host='127.0.0.1', port=8000)
