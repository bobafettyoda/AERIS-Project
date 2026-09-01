from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
PROJECT_DIRECTORY = BACKEND_DIRECTORY.parent
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from analysis.site_feasibility.pipeline import build_site_feasibility


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build parcel-scale terrain, wetlands, road-access, existing-"
            "development, and assemblage evidence."
        )
    )
    parser.add_argument("scope_id")
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def main() -> None:
    options = arguments()
    manifest = build_site_feasibility(
        config_path=(
            PROJECT_DIRECTORY
            / "configs"
            / "parcels"
            / "site_feasibility.yaml"
        ),
        scope_id=options.scope_id,
        refresh=options.refresh,
    )
    print()
    print("Parcel site-feasibility build complete")
    print(
        json.dumps(
            {
                "scope_id": manifest["scope_id"],
                "counts": manifest["counts"],
                "domain_status": manifest["domain_status"],
                "site_feasibility_class_counts": manifest[
                    "site_feasibility_class_counts"
                ],
                "outputs": manifest["outputs"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
