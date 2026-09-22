from pathlib import Path

import yaml


PROJECT_DIRECTORY = (
    Path(__file__).resolve().parents[2]
)

EXPECTED_DNR_WHERE = (
    "Type IN ("
    "'Estuarine', 'Lacustrine', 'Marine', "
    "'Palustrine', 'Riverine'"
    ")"
)


def test_production_dnr_wetland_filter_excludes_upland():
    path = (
        PROJECT_DIRECTORY
        / "configs"
        / "parcels"
        / "site_feasibility.yaml"
    )

    config = yaml.safe_load(
        path.read_text(encoding="utf-8")
    )

    where = (
        config["inputs"]["wetlands"]
        ["layers"]["dnr_polygon"]
        ["where"]
    )

    assert where == EXPECTED_DNR_WHERE
    assert "Upland" not in where
