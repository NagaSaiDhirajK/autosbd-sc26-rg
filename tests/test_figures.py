"""Tests for deterministic, raw-traceable internal figures."""

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from autosbd.figures import (
    FigureError,
    _require_summary,
    build_multifamily_figure_data,
    build_stage4_figure_data,
    generate_multifamily_figures,
    generate_stage4_figures,
)


ROOT = Path(__file__).resolve().parents[1]
AGGREGATE = ROOT / "results" / "processed" / "stage4_final.json"
RAW_DIR = ROOT / "results" / "raw"
MULTIFAMILY_DIR = ROOT / "results" / "processed" / "stage5_multifamily"
POLICY_SUMMARY = MULTIFAMILY_DIR / "policy_summary.csv"
POLICY_PREDICTIONS = MULTIFAMILY_DIR / "policy_predictions.csv"
POLICY_SUMMARY_SHA256 = (
    "5f34333500332f3c28b181b3b333d7662f49a0246a984506ebafba1f640cd154"
)
POLICY_PREDICTIONS_SHA256 = (
    "e29de16120ad611a13adde46fa5e21624880f04afc5d5621c83b249cb58629c4"
)


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


class MultifamilyFigureTests(unittest.TestCase):
    def test_sealed_geometry_cross_checks_and_determinism(self) -> None:
        data = build_multifamily_figure_data(POLICY_SUMMARY, POLICY_PREDICTIONS)
        self.assertEqual(len(data["policy_summaries"]), 6)
        self.assertEqual(len(data["instances"]), 15)
        self.assertEqual(
            data["source"]["policy_summary_sha256"], POLICY_SUMMARY_SHA256
        )
        self.assertEqual(
            data["source"]["policy_predictions_sha256"],
            POLICY_PREDICTIONS_SHA256,
        )
        self.assertEqual(
            {row["family_id"] for row in data["instances"]},
            {"fe4s4", "n2", "h2o"},
        )
        full_errors = sum(
            not row["decisions"]["autosbd_full_tree"]["selection_correct"]
            for row in data["instances"]
        )
        threshold_errors = sum(
            not row["decisions"]["static_size_threshold"]["selection_correct"]
            for row in data["instances"]
        )
        size_errors = sum(
            not row["decisions"]["size_only_tree_ablation"]["selection_correct"]
            for row in data["instances"]
        )
        self.assertEqual((full_errors, threshold_errors, size_errors), (2, 2, 3))

        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            figures = directory / "figures"
            tables = directory / "tables"
            first = generate_multifamily_figures(
                POLICY_SUMMARY, POLICY_PREDICTIONS, figures, tables
            )
            paths = sorted(figures.iterdir()) + sorted(tables.iterdir())
            first_hashes = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths
            }
            second = generate_multifamily_figures(
                POLICY_SUMMARY, POLICY_PREDICTIONS, figures, tables
            )
            second_hashes = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths
            }
            self.assertEqual(first_hashes, second_hashes)
            self.assertTrue(all(first["changed"].values()))
            self.assertFalse(any(second["changed"].values()))
            policy_svg = (figures / "multifamily_policy_regret.svg").read_text()
            decisions_svg = (
                figures / "multifamily_instance_decisions.svg"
            ).read_text()
            for svg in (policy_svg, decisions_svg):
                self.assertIn(POLICY_SUMMARY_SHA256, svg)
                self.assertIn(POLICY_PREDICTIONS_SHA256, svg)
                self.assertNotIn("dc:date", svg)
                self.assertTrue(
                    all(line == line.rstrip() for line in svg.splitlines())
                )
            self.assertIn("Held-out policy runtime overhead", policy_svg)
            self.assertIn("Held-out per-instance decisions", decisions_svg)

    def test_summary_prediction_disagreement_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            altered = Path(directory_name) / "policy_summary.csv"
            source = POLICY_SUMMARY.read_text(encoding="utf-8")
            altered.write_text(
                source.replace(
                    ",1.0229922425736244,", ",1.0,", 1
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                FigureError, "pooled geometric mean disagrees"
            ):
                build_multifamily_figure_data(altered, POLICY_PREDICTIONS)


if __name__ == "__main__":
    unittest.main()
