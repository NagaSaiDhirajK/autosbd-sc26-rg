#!/usr/bin/env python3
"""Generate internal, traceable AutoSBD figures from processed evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autosbd.figures import FigureError, generate_stage4_figures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage4", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--table-dir", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        status = generate_stage4_figures(
            arguments.stage4,
            arguments.raw_dir,
            arguments.output_dir,
            arguments.table_dir,
        )
    except FigureError as error:
        parser.error(str(error))
    print(json.dumps(status, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
