#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$repository_root/src"

smoke_root="$(mktemp -d /tmp/autosbd-stage2-smoke.XXXXXX)"
results_dir="$smoke_root/results"
trial_logs_dir="$smoke_root/trial-logs"

.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v \
  >"$smoke_root/unittest.log" 2>&1

.venv/bin/python scripts/run_sweep.py configs/smoke.yaml \
  --project-root "$repository_root" \
  --results-dir "$results_dir" \
  --logs-dir "$trial_logs_dir" \
  --no-randomize >"$smoke_root/first-run.json"

.venv/bin/python scripts/run_sweep.py configs/smoke.yaml \
  --project-root "$repository_root" \
  --results-dir "$results_dir" \
  --logs-dir "$trial_logs_dir" \
  --no-randomize >"$smoke_root/resume-run.json"

.venv/bin/python - "$smoke_root" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

from autosbd.records import load_record


root = Path(sys.argv[1])
first = json.loads((root / "first-run.json").read_text(encoding="utf-8"))
resumed = json.loads((root / "resume-run.json").read_text(encoding="utf-8"))
expected = {"failed": 2, "oom": 1, "success": 1, "timeout": 1}
if first["total"] != 5 or first["launched"] != 5 or first["reused"] != 0:
    raise SystemExit(f"unexpected first-run summary: {first}")
if first["statuses"] != expected:
    raise SystemExit(f"unexpected terminal statuses: {first['statuses']}")
if resumed["total"] != 5 or resumed["launched"] != 0 or resumed["reused"] != 5:
    raise SystemExit(f"resume did not reuse all trials: {resumed}")
if resumed["records"] != first["records"]:
    raise SystemExit("resumed record paths differ from first-run record paths")
records = [load_record(Path(path)) for path in first["records"]]
if {record["status"] for record in records} != set(expected):
    raise SystemExit("durable record statuses do not match the summary")
if any("--init" in record["command"] for record in records):
    raise SystemExit("unsupported --init flag appeared in a command")
if any(record["upstream_url"] != "https://github.com/AMD-HPC/amd-sbd" for record in records):
    raise SystemExit("a record does not identify official AMD-HPC/amd-sbd")
print(json.dumps({"smoke_root": str(root), "statuses": expected}, sort_keys=True))
PY
