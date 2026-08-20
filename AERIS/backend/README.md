# AERIS backend

FastAPI and geospatial analysis services for statewide screening, scoped parcel investigation, development envelopes, public grid context, and planning context.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Run

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Test

```bash
python -m unittest discover -s tests -v
```
