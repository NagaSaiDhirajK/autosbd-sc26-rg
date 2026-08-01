#!/usr/bin/env python3
"""Build or check the external immutable-evidence Fe4S4 family registry."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from autosbd.family_registry import (
    EXPECTED_AGGREGATE_PATH,
    EXPECTED_COMPLETION_PATH,
    EXPECTED_RAW_DIRECTORY,
    FamilyRegistryError,
    build_fe4s4_family_registry,
    write_family_registry,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = "reports/stage4_fe4s4_family_registry.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--completion", type=Path, default=Path(EXPECTED_COMPLETION_PATH))
    parser.add_argument("--aggregate", type=Path, default=Path(EXPECTED_AGGREGATE_PATH))
    parser.add_argument("--raw-dir", type=Path, default=Path(EXPECTED_RAW_DIRECTORY))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT),
        help=f"proposed generated output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify output bytes exactly and never write",
    )
    arguments = parser.parse_args(argv)
    root = arguments.repository_root.resolve()

    def rooted(path: Path) -> Path:
        return path if path.is_absolute() else root / path

    output = rooted(arguments.output)
    raw_dir = rooted(arguments.raw_dir)
    try:
        registry = build_fe4s4_family_registry(
            rooted(arguments.completion),
            rooted(arguments.aggregate),
            raw_dir,
            repository_root=root,
        )
        changed = write_family_registry(
            registry,
            output,
            check=arguments.check,
            forbidden_directory=raw_dir,
        )
    except (FamilyRegistryError, OSError) as error:
        print(f"family registry failed: {error}", file=sys.stderr)
        return 1
    payload = (
        json.dumps(registry, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    print(
        json.dumps(
            {
                "status": "verified" if arguments.check else "complete",
                "changed": changed,
                "check_mode": arguments.check,
                "output": str(output),
                "registry_id": registry["registry_id"],
                "sha256": hashlib.sha256(payload).hexdigest(),
                "workload_entries": registry["record_counts"]["workload_entries"],
                "raw_records": registry["record_counts"]["raw_records"],
            },
            allow_nan=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
