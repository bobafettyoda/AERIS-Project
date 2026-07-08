from fastapi import FastAPI

from app.routers import analysis, decision_models, gis

app = FastAPI(title="AERIS Backend")


@app.get("/health")
def health():
    return {
        "ok": True,
        "project": "AERIS",
    }


app.include_router(analysis.router)
app.include_router(decision_models.router)
app.include_router(gis.router)