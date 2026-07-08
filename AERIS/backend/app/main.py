from pathlib import Path

import yaml
from fastapi import FastAPI

app = FastAPI(title="AERIS Backend")

from analysis.weighted_overlay import weighted_overlay

BASE_DIR = Path(__file__).resolve().parents[2]
MODEL_PATH = BASE_DIR / "configs" / "decision_models" / "data_center_maryland_demo.yaml"


@app.get("/health")
def health():
    return {"ok": True, "project": "AERIS"}


@app.get("/decision-models/data-center-demo")
def get_data_center_model():
    with MODEL_PATH.open("r", encoding="utf-8") as f:
        model = yaml.safe_load(f)

    return model


@app.post("/analysis/data-center-demo")
def run_data_center_demo():
    return {
        "status": "stub",
        "message": "AERIS Maryland data center siting analysis will run here.",
    }
@app.get("/analysis/data-center-demo/validate")
def validate_data_center_model():
    with MODEL_PATH.open("r", encoding="utf-8") as f:
        model = yaml.safe_load(f)

    weights = {
        name: values["weight"]
        for name, values in model["criteria"].items()
    }

    return {
        "model": model["name"],
        "weight_total": round(sum(weights.values()), 6),
        "weights": weights,
        "valid": abs(sum(weights.values()) - 1.0) < 0.001,
    }
@app.get("/analysis/data-center-demo/sample-score")
def sample_data_center_score():
    with MODEL_PATH.open("r", encoding="utf-8") as f:
        model = yaml.safe_load(f)

    weights = {
        name: values["weight"]
        for name, values in model["criteria"].items()
    }

    sample_scores = {
        "climate": 0.70,
        "grid_infrastructure": 0.90,
        "telecom_infrastructure": 0.80,
        "protected_areas": 1.00,
        "water_bodies": 0.60,
        "population_density": 0.75,
        "road_access": 0.85,
        "hydro_hazard": 0.40,
    }

    suitability_score = weighted_overlay(sample_scores, weights)

    return {
        "model": model["name"],
        "method": model["analysis"]["overlay"],
        "scores": sample_scores,
        "weights": weights,
        "suitability_score": suitability_score,
    }