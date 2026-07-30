from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIRECTORY = (
    Path(__file__).resolve().parents[1]
)

PROJECT_DIRECTORY = (
    BACKEND_DIRECTORY.parent
)

if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(
        0,
        str(BACKEND_DIRECTORY),
    )


from analysis.statewide.acquisition import (
    FoundationAcquirer,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire and validate AERIS "
            "statewide foundational datasets."
        )
    )

    parser.add_argument(
        "--source",
        choices=(
            "all",
            "tiger",
            "acs",
            "enviroscreen",
        ),
        default="all",
        help=(
            "Source to process. "
            "Default: all."
        ),
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Discard complete cached output "
            "and download a fresh snapshot."
        ),
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume a partial TIGER download "
            "or cached EnviroScreen pages."
        ),
    )

    parser.add_argument(
        "--validate-only",
        action="store_true",
        help=(
            "Validate cached files without "
            "downloading data."
        ),
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help=(
            "Show acquisition and cache status."
        ),
    )

    return parser.parse_args()


def selected_sources(
    source: str,
) -> list[str]:
    mapping = {
        "all": [
            "tiger_tracts",
            "acs_population",
            "md_enviroscreen",
        ],
        "tiger": [
            "tiger_tracts",
        ],
        "acs": [
            "acs_population",
        ],
        "enviroscreen": [
            "md_enviroscreen",
        ],
    }

    return mapping[source]


def main() -> None:
    arguments = parse_arguments()

    config_path = (
        PROJECT_DIRECTORY
        / "configs"
        / "statewide"
        / "foundation_sources.yaml"
    )

    acquirer = FoundationAcquirer(
        config_path=config_path,
    )

    sources = selected_sources(
        arguments.source
    )

    if arguments.status:
        print(
            json.dumps(
                acquirer.status(),
                indent=2,
            )
        )

        return

    if arguments.validate_only:
        acquirer.validate(sources)
        return

    results = acquirer.acquire(
        source_names=sources,
        refresh=arguments.refresh,
        resume=arguments.resume,
    )

    print()
    print(
        "Statewide foundation acquisition "
        "complete"
    )

    print(
        json.dumps(
            results,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
