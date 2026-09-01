from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
PROJECT_DIRECTORY = BACKEND_DIRECTORY.parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("scope_id")
    return parser.parse_args()


def main() -> None:
    options = arguments()
    manifest_path = (
        PROJECT_DIRECTORY
        / "data"
        / "manifests"
        / "parcel_site_feasibility"
        / f"{options.scope_id}.json"
    )
    require(manifest_path.exists(), f"Manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_path = PROJECT_DIRECTORY / manifest["outputs"]["geopackage"]
    require(output_path.exists(), f"Output is missing: {output_path}")

    layers = {str(row[0]) for row in pyogrio.list_layers(output_path)}
    required_layers = {
        "parcel_site_analysis",
        "site_envelopes",
        "largest_site_components",
    }
    require(
        required_layers.issubset(layers),
        "Missing site-feasibility layers: "
        + ", ".join(sorted(required_layers - layers)),
    )
    parcels = gpd.read_file(output_path, layer="parcel_site_analysis")
    envelopes = gpd.read_file(output_path, layer="site_envelopes")

    required_columns = {
        "parcel_id",
        "base_development_envelope_acres",
        "mapped_wetland_overlap_acres",
        "steep_slope_overlap_acres",
        "final_site_area_acres",
        "largest_contiguous_site_acres",
        "road_access_status",
        "road_frontage_proxy_m",
        "redevelopment_burden_class",
        "site_feasibility_class",
        "site_candidate_score",
        "legal_buildability_confirmed",
        "road_access_confirmed",
        "wetland_delineation_confirmed",
    }
    missing = required_columns - set(parcels.columns)
    require(not missing, "Missing columns: " + ", ".join(sorted(missing)))
    require(parcels["parcel_id"].is_unique, "Parcel IDs are not unique.")
    require(parcels.geometry.is_valid.all(), "Invalid parcel geometry exists.")
    require(envelopes.geometry.is_valid.all(), "Invalid site envelope exists.")

    base = pd.to_numeric(
        parcels["base_development_envelope_acres"], errors="coerce"
    ).fillna(0)
    final = pd.to_numeric(parcels["final_site_area_acres"], errors="coerce").fillna(0)
    largest = pd.to_numeric(
        parcels["largest_contiguous_site_acres"], errors="coerce"
    ).fillna(0)
    require(final.ge(0).all(), "Negative final site area exists.")
    require(final.le(base + 0.01).all(), "Final site area exceeds base envelope.")
    require(largest.le(final + 0.01).all(), "Largest component exceeds site area.")
    require(
        (~parcels["legal_buildability_confirmed"].astype(bool)).all(),
        "Legal buildability was incorrectly confirmed.",
    )
    require(
        (~parcels["road_access_confirmed"].astype(bool)).all(),
        "Road access was incorrectly confirmed.",
    )
    require(
        (~parcels["wetland_delineation_confirmed"].astype(bool)).all(),
        "Wetland delineation was incorrectly confirmed.",
    )
    require(
        all(value is False for value in manifest["safeguards"].values()),
        "One or more site-feasibility safeguards were enabled.",
    )

    print()
    print("PARCEL SITE-FEASIBILITY REVIEW PASSED")
    print("Scope:", options.scope_id)
    print("Parcels:", f"{len(parcels):,}")
    print("Site envelopes:", f"{len(envelopes):,}")
    print()
    print("Domain status:")
    for name, status in manifest["domain_status"].items():
        print(f"  {name}: {status['state']}" + (f" | {status['error']}" if status.get("error") else ""))
    print()
    print("Site-feasibility classes:")
    print(parcels["site_feasibility_class"].value_counts(dropna=False).to_string())
    print()
    print("Road-access classes:")
    print(parcels["road_access_status"].value_counts(dropna=False).to_string())
    print()
    print("This output remains preliminary screening evidence, not confirmed buildable land.")


if __name__ == "__main__":
    main()
