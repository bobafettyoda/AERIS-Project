from pathlib import Path

import yaml
from fastapi import FastAPI

app = FastAPI(title="AERIS Backend")

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
