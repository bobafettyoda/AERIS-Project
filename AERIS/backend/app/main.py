from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.config import get_cors_origins
from app.release import release_metadata
from app.routers import analysis, decision_models, gis, parcels, statewide


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    parcels.build_coordinator.shutdown()


release = release_metadata()

app = FastAPI(
    title="AERIS Backend",
    version=str(release["version"]),
    description=(
        "Maryland statewide site screening, scoped parcel investigation, "
        "mapped physical constraints, public grid context, and planning context."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    GZipMiddleware,
    minimum_size=1024,
)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "project": release["name"],
        "version": app.version,
        "release_label": release["release_label"],
        "release_stage": release["release_stage"],
    }


app.include_router(analysis.router)
app.include_router(decision_models.router)
app.include_router(gis.router)
app.include_router(statewide.router)
app.include_router(parcels.router)
