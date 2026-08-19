from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from app.routers import parcels
from starlette.middleware.gzip import GZipMiddleware

from app.routers import statewide
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_cors_origins
from app.routers import analysis, decision_models, gis


app = FastAPI(
    title="AERIS Backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "project": "AERIS",
        "version": app.version,
    }


app.include_router(analysis.router)
app.include_router(decision_models.router)
app.include_router(gis.router)

app.add_middleware(
    GZipMiddleware,
    minimum_size=1024,
)

app.include_router(
    statewide.router
)

app.include_router(
    parcels.router
)
