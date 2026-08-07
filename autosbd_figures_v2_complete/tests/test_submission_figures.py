from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from autosbd.submission_figures import (
    SubmissionFigureError,
    extract_runtime_rows,
    load_deployment_tree,
    render_architecture,
)


class SubmissionFigureTests(unittest.TestCase):
    def test_runtime_extraction_uses_only_explicit_summaries(self) -> None:
        aggregate = {
            "analysis_type": "autosbd_timing_aggregation",
            "candidate_groups": [
                {
                    "candidate": {"name": "amd-cpu-16"},
                    "problem_instance": "fe4s4-prefix-0032",
                    "wall_time_s": {"count": 3, "q1": 1.0, "median": 1.1, "q3": 1.2, "iqr": 0.2},
                    "solver_time_s": {"median": 0.8},
                    "record_ids": ["a", "b", "c"],
                },
                {
                    "candidate": {"name": "amd-l4-default"},
                    "problem_instance": "fe4s4-prefix-0032",
                    "wall_time_s": {"count": 3, "q1": 1.3, "median": 1.4, "q3": 1.5, "iqr": 0.2},
                    "solver_time_s": {"median": 0.9},
                    "record_ids": ["d", "e", "f"],
                },
            ],
            "rows": [
                {
                    "problem_instance": "fe4s4-prefix-0032",
                    "features": {"n_configurations": 1024},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "aggregate.json"
            path.write_text(json.dumps(aggregate), encoding="utf-8")
            rows = extract_runtime_rows(
                path,
                fallback_family="fe4s4",
                fallback_molecule="Fe4S4",
                fallback_basis=None,
            )
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["candidate"] for row in rows}, {"amd-cpu-16", "amd-l4-default"})
        self.assertTrue(all(row["n_configurations"] == 1024 for row in rows))

    def test_deployment_tree_must_not_be_used_for_heldout_metrics(self) -> None:
        model = {
            "deployment_model_scope": {"used_for_heldout_metrics": True},
            "deployment_models": {
                "autosbd_full_tree": {
                    "tree": {"nodes": [{"node_id": 0, "type": "leaf"}]}
                }
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "models.json"
            path.write_text(json.dumps(model), encoding="utf-8")
            with self.assertRaisesRegex(SubmissionFigureError, "excluded from held-out"):
                load_deployment_tree(path)

    def test_architecture_writes_vector_and_raster_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            stem = Path(temporary_directory) / "architecture"
            changed = render_architecture(stem)
            self.assertEqual(set(Path(path).suffix for path in changed), {".svg", ".pdf", ".png"})
            self.assertTrue(all(Path(path).is_file() for path in changed))


if __name__ == "__main__":
    unittest.main()
