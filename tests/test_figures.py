"""Tests for deterministic, raw-traceable internal figures."""

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from autosbd.figures import (
    _require_summary,
    build_stage4_figure_data,
    generate_stage4_figures,
)


ROOT = Path(__file__).resolve().parents[1]
AGGREGATE = ROOT / "results" / "processed" / "stage4_final.json"
RAW_DIR = ROOT / "results" / "raw"


class Stage4FigureTests(unittest.TestCase):
    def test_zero_iqr_is_valid(self) -> None:
        summary = {
            "count": 1,
            "minimum": 1.0,
            "q1": 1.0,
            "median": 1.0,
            "q3": 1.0,
            "iqr": 0.0,
            "maximum": 1.0,
        }
        self.assertIs(_require_summary(summary, "fixture", "candidate"), summary)

    def test_final_data_geometry_trace_and_determinism(self) -> None:
        data = build_stage4_figure_data(AGGREGATE, RAW_DIR)
        self.assertEqual(len(data["crossover"]["rows"]), 10)
        self.assertEqual(len(data["gpu_memory"]["records"]), 19)
        self.assertEqual(len(data["gpu_memory"]["summaries"]), 5)
        self.assertFalse(data["gpu_memory"]["boundary_reached"])
        self.assertEqual(
            data["crossover"]["observed_winner_flip_bracket"],
            {
                "lower_n_configurations": 1024,
                "upper_n_configurations": 3025,
                "lower_winner": "amd-cpu-16",
                "upper_winner": "amd-l4-default",
                "interpretation": "observed bracket only; no fitted crossover",
            },
        )
        self.assertEqual(
            len(
                {
                    row["trial_id"]
                    for row in data["gpu_memory"]["records"]
                }
            ),
            19,
        )

        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            figures = directory / "figures"
            tables = directory / "tables"
            first = generate_stage4_figures(
                AGGREGATE, RAW_DIR, figures, tables
            )
            paths = sorted(figures.iterdir()) + sorted(tables.iterdir())
            first_hashes = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths
            }
            second = generate_stage4_figures(
                AGGREGATE, RAW_DIR, figures, tables
            )
            second_hashes = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths
            }
            self.assertEqual(first_hashes, second_hashes)
            self.assertTrue(all(first["changed"].values()))
            self.assertFalse(any(second["changed"].values()))
            crossover_svg = (figures / "cpu_gpu_crossover.svg").read_text()
            memory_svg = (figures / "gpu_memory_guard.svg").read_text()
            self.assertIn("observed winner-flip bracket", crossover_svg)
            self.assertIn("boundary not reached", memory_svg)
            self.assertNotIn("dc:date", crossover_svg)
            self.assertNotIn("dc:date", memory_svg)


if __name__ == "__main__":
    unittest.main()
