"""Integration tests for completion-bound Stage 5 artifacts."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from autosbd.evaluation_artifacts import (
    EvaluationArtifactError,
    build_evaluation_package,
    write_evaluation_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "stage5_size_heldout.yaml"


class EvaluationArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = build_evaluation_package(CONFIG, repository_root=ROOT)

    def test_real_package_is_balanced_grouped_and_claim_limited(self) -> None:
        package = self.package
        self.assertEqual(package["status"], "complete")
        self.assertFalse(
            package["claim_boundary"]["broad_family_generalization_claim_allowed"]
        )
        self.assertEqual(
            package["dataset"]["record_counts"],
            {
                "selected_measurements": 30,
                "candidate_rows": 10,
                "problem_instances": 5,
                "candidates_per_instance": 2,
                "repetitions_per_candidate": 3,
            },
        )
        primary = package["evaluation"]["primary"]
        self.assertEqual(primary["split"]["test_instance_ids"], ["fe4s4-prefix-0244"])
        self.assertEqual(len(primary["training_source_record_ids"]), 24)
        self.assertEqual(len(primary["test_source_record_ids"]), 6)
        self.assertFalse(
            set(primary["training_source_record_ids"]).intersection(
                primary["test_source_record_ids"]
            )
        )
        self.assertEqual(
            primary["models"]["autosbd_full_tree"]["hyperparameters"]["max_depth"],
            2,
        )

    def test_outputs_are_deterministic_changed_only_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            output = Path(name)
            first = write_evaluation_artifacts(self.package, output)
            second = write_evaluation_artifacts(self.package, output)
            self.assertTrue(all(first["changed"].values()))
            self.assertFalse(any(second["changed"].values()))
            self.assertEqual(len(first["files"]), 8)
            self.assertEqual(first["balanced_measurements"], 30)
            self.assertEqual(first["candidate_rows"], 10)
            self.assertEqual(first["secondary_folds"], 5)
            evaluation = json.loads((output / "evaluation.json").read_text())
            self.assertEqual(evaluation["status"], "complete")
            predictions = (output / "policy_predictions.csv").read_text().splitlines()
            summaries = (output / "policy_summary.csv").read_text().splitlines()
            self.assertEqual(len(predictions), 37)
            self.assertEqual(len(summaries), 13)
            policy_summary = json.loads((output / "policy_summary.json").read_text())
            self.assertEqual(
                policy_summary["policy_aliases"], {"upstream_default": "fixed_gpu"}
            )
            self.assertNotIn(
                "upstream_default",
                {row["policy"] for row in policy_summary["rows"]},
            )
            for row in policy_summary["rows"]:
                self.assertIsInstance(row["requested_instances"], int)
                self.assertIsInstance(row["failure_instances"], int)
                self.assertIsInstance(
                    row["geometric_mean_speedup_vs_oracle_inverse_valid_only"],
                    float,
                )

    def test_config_hash_and_completion_status_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as name:
            directory = Path(name)
            config = CONFIG.read_text().replace(
                "max_depth: 2", "max_depth: 3"
            )
            path = directory / "bad.yaml"
            path.write_text(config)
            with self.assertRaisesRegex(EvaluationArtifactError, "max_depth"):
                build_evaluation_package(path, repository_root=ROOT)

        with tempfile.TemporaryDirectory(dir=ROOT) as name:
            directory = Path(name)
            config = CONFIG.read_text().replace(
                "    - always_gpu", "    - unregistered_sentinel"
            )
            path = directory / "bad-threshold.yaml"
            path.write_text(config)
            with self.assertRaisesRegex(EvaluationArtifactError, "candidate_kinds"):
                build_evaluation_package(path, repository_root=ROOT)

        malformed = deepcopy(self.package)
        malformed["status"] = "incomplete"
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(EvaluationArtifactError, "not complete"):
                write_evaluation_artifacts(malformed, Path(name))


if __name__ == "__main__":
    unittest.main()
