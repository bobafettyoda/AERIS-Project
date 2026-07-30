from app.config import (
    FEMA_FLOODPLAIN_URL,
    PROTECTED_LANDS_URL,
    ROADS_LAYER_URL,
    SUBSTATIONS_LAYER_URL,
    TRANSMISSION_LINES_LAYER_URL,
    WATERBODIES_URL,
)
from analysis.candidate_site import CandidateSiteEvaluator
from pathlib import Path

import yaml
from fastapi import APIRouter

from analysis.normalization import normalize_linear
from analysis.weighted_overlay import weighted_overlay

router = APIRouter(prefix="/analysis", tags=["analysis"])

BASE_DIR = Path(__file__).resolve().parents[3]
MODEL_PATH = BASE_DIR / "configs" / "decision_models" / "data_center_maryland_demo.yaml"


@router.post("/data-center-demo")
def run_data_center_demo():
    return {
        "status": "stub",
        "message": "AERIS Maryland data center siting analysis will run here.",
    }


@router.get("/data-center-demo/validate")
def validate_data_center_model():
    with MODEL_PATH.open("r", encoding="utf-8") as f:
        model = yaml.safe_load(f)

    weights = {name: values["weight"] for name, values in model["criteria"].items()}

    return {
        "model": model["name"],
        "weight_total": round(sum(weights.values()), 6),
        "weights": weights,
        "valid": abs(sum(weights.values()) - 1.0) < 0.001,
    }


@router.get("/data-center-demo/sample-score")
def sample_data_center_score():
    with MODEL_PATH.open("r", encoding="utf-8") as f:
        model = yaml.safe_load(f)

    weights = {name: values["weight"] for name, values in model["criteria"].items()}

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

    return {
        "model": model["name"],
        "method": model["analysis"]["overlay"],
        "scores": sample_scores,
        "weights": weights,
        "suitability_score": weighted_overlay(sample_scores, weights),
    }


@router.get("/data-center-demo/normalize-road-distance")
def normalize_road_distance(distance_m: float):
    score = normalize_linear(
        value=distance_m,
        best=800,
        worst=5000,
        higher_is_better=False,
    )

    return {
        "criterion": "road_access",
        "distance_m": distance_m,
        "best_m": 800,
        "worst_m": 5000,
        "score": score,
    }

candidate_site_evaluator = CandidateSiteEvaluator(
    roads_layer_url=ROADS_LAYER_URL,
    transmission_layer_url=TRANSMISSION_LINES_LAYER_URL,
    substation_layer_url=SUBSTATIONS_LAYER_URL,
    floodplain_layer_url=FEMA_FLOODPLAIN_URL,
    protected_lands_service_url=PROTECTED_LANDS_URL,
    waterbodies_service_url=WATERBODIES_URL,
)


@router.get("/data-center-demo/candidate-site")
def evaluate_candidate_site(
    lat: float,
    lon: float,
) -> dict:
    return candidate_site_evaluator.evaluate(
        lat=lat,
        lon=lon,
    )

