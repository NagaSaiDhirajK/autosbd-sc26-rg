#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PATCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

mkdir -p src/autosbd scripts tests reports
cp "$PATCH_ROOT/src/autosbd/submission_figures.py" src/autosbd/submission_figures.py
cp "$PATCH_ROOT/scripts/make_submission_figures.py" scripts/make_submission_figures.py
cp "$PATCH_ROOT/tests/test_submission_figures.py" tests/test_submission_figures.py
cp "$PATCH_ROOT/reports/SUBMISSION_FIGURE_PLAN.md" reports/SUBMISSION_FIGURE_PLAN.md

PYTHON=""
if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  echo "ERROR: python3 is not available." >&2
  exit 1
fi

if ! "$PYTHON" -c 'import matplotlib, numpy, sklearn' >/dev/null 2>&1; then
  if [[ "$PYTHON" != ".venv/bin/python" ]]; then
    python3 -m venv .venv
    PYTHON=.venv/bin/python
  fi
  "$PYTHON" -m pip install --upgrade pip
  "$PYTHON" -m pip install -r requirements-lock.txt
fi

PYTHONPATH=src "$PYTHON" -m unittest tests.test_submission_figures -v
PYTHONPATH=src "$PYTHON" scripts/make_submission_figures.py

echo
echo "Generated figures: $REPO_ROOT/figures/submission"
echo "Generated data:    $REPO_ROOT/results/processed/submission_figure_data"
