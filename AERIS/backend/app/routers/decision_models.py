from pathlib import Path

import yaml
from fastapi import APIRouter

router = APIRouter(prefix="/decision-models", tags=["decision-models"])

BASE_DIR = Path(__file__).resolve().parents[3]
MODEL_PATH = BASE_DIR / "configs" / "decision_models" / "data_center_maryland_demo.yaml"


@router.get("/data-center-demo")
def get_data_center_model():
    with MODEL_PATH.open("r", encoding="utf-8") as f:
        model = yaml.safe_load(f)

    return model