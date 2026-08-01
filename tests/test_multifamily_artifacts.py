"""Integration tests for hash-bound multifamily evaluation artifacts."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from autosbd.evaluation import (
    FULL_FEATURE_NAMES,
    POLICY_FULL_TREE,
    POLICY_ORDER,
    REQUIRED_SKLEARN_VERSION,
    SIZE_ONLY_FEATURE_NAMES,
    TREE_RANDOM_STATE,
)
from autosbd.multifamily_artifacts import (
    MultifamilyArtifactError,
    build_multifamily_evaluation_package,
    sha256_path,
    write_multifamily_evaluation_artifacts,
)
from autosbd.multifamily_evaluation import (
    MULTIFAMILY_TREE_MAX_DEPTH,
    MULTIFAMILY_TREE_MIN_SAMPLES_LEAF,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = {
    "stage4_protocol": "reports/stage4_protocol.json",
    "stage4_completion": "reports/stage4_completion.json",
    "stage4_aggregate": "results/processed/stage4_final.json",
    "fe4s4_family_registry": "reports/stage4_fe4s4_family_registry.json",
    "phaseb_protocol": "reports/phaseb_final_protocol.json",
    "phaseb_completion": "reports/phaseb_final_completion.json",
    "phaseb_aggregate": "results/processed/phaseb_n2_h2o_grid_final.json",
}


def _file_claim(relative: str) -> dict[str, object]:
    path = ROOT / relative
    return {
        "path": relative,
        "sha256": sha256_path(path),
    }


def _config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "stage5-amd-multifamily-selector-v1",
        "sources": {
            **{key: _file_claim(value) for key, value in SOURCE_PATHS.items()},
            "raw_directory": "results/raw",
        },
        "dataset": {
            "stage4_source_view": "balanced_broad_sensitivity",
            "phaseb_source_view": "balanced_broad",
            "family_order": ["fe4s4", "n2", "h2o"],
            "phase": "measured",
            "purpose": "final",
            "repetitions": [0, 1, 2],
            "expected_measurements": 90,
            "expected_candidate_rows": 30,
            "expected_problem_instances": 15,
            "expected_instances_per_family": 5,
            "expected_candidates_per_instance": 2,
            "pilot_records_allowed": False,
            "post_execution_selection_features_allowed": False,
        },
        "splits": {
            "primary_type": "leave_one_chemistry_family_out",
            "folds": 3,
            "group_key": "family_id_and_instance_id",
            "all_candidates_and_repetitions_stay_together": True,
        },
        "model": {
            "implementation": "sklearn.tree.DecisionTreeRegressor",
            "sklearn_version": REQUIRED_SKLEARN_VERSION,
            "max_depth": MULTIFAMILY_TREE_MAX_DEPTH,
            "min_samples_leaf": MULTIFAMILY_TREE_MIN_SAMPLES_LEAF,
            "random_state": TREE_RANDOM_STATE,
            "heldout_hyperparameter_tuning": False,
            "full_features": list(FULL_FEATURE_NAMES),
            "size_only_ablation_features": list(SIZE_ONLY_FEATURE_NAMES),
        },
        "policies": list(POLICY_ORDER),
        "policy_aliases": {"upstream_default": "fixed_gpu"},
        "claim_boundary": {
            "universal_generalization_claim_allowed": False,
            "multi_node_claim_allowed": False,
        },
    }


class MultifamilyArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        cls.directory = Path(cls.temporary.name)
        cls.counter = 0
        cls.config = _config()
        cls.config_path = cls._write_config(cls.config)
        cls.package = build_multifamily_evaluation_package(
            cls.config_path, repository_root=ROOT
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @classmethod
    def _write_config(cls, config: object) -> Path:
        cls.counter += 1
        path = cls.directory / f"config-{cls.counter:02d}.yaml"
        path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        return path

    @classmethod
    def _write_json(cls, name: str, value: object) -> str:
        path = cls.directory / name
        path.write_text(
            json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path.relative_to(ROOT).as_posix()

    def test_real_package_has_exact_geometry_and_provenance(self) -> None:
        self.assertEqual(
            self.package["dataset"]["record_counts"],
            {
                "selected_measurements": 90,
                "candidate_rows": 30,
                "problem_instances": 15,
                "candidates_per_instance": 2,
                "repetitions_per_candidate": 3,
            },
        )
        self.assertEqual(len(self.package["evaluation"]["folds"]), 3)
        manifest = self.package["source_manifest"]
        self.assertEqual(len(manifest["selected_raw_records"]), 90)
        self.assertEqual(
            {row["family_id"] for row in manifest["selected_raw_records"]},
            {"fe4s4", "n2", "h2o"},
        )
        self.assertTrue(
            all(
                key not in self.package["dataset"]["feature_names"]["full"]
                for key in ("family_id", "molecule", "basis", "instance_id")
            )
        )

    def test_outputs_are_deterministic_complete_and_changed_only(self) -> None:
        output = self.directory / "outputs"
        first = write_multifamily_evaluation_artifacts(self.package, output)
        second = write_multifamily_evaluation_artifacts(self.package, output)
        self.assertEqual(len(first["files"]), 9)
        self.assertTrue(all(first["changed"].values()))
        self.assertFalse(any(second["changed"].values()))
        self.assertEqual(first["balanced_measurements"], 90)
        self.assertEqual(first["candidate_rows"], 30)
        self.assertEqual(first["problem_instances"], 15)
        self.assertEqual(first["family_folds"], 3)
        self.assertEqual(
            set(first["files"]),
            {
                "source_manifest.json",
                "balanced_dataset.json",
                "split_manifest.json",
                "models.json",
                "evaluation.json",
                "policy_predictions.csv",
                "policy_summary.json",
                "policy_summary.csv",
                "selector_ablation.csv",
            },
        )
        models = json.loads((output / "models.json").read_text(encoding="utf-8"))
        self.assertEqual(
            models["deployment_model_scope"],
            {
                "fit_scope": "all_balanced_instances_after_heldout_evaluation",
                "purpose": "deployment_selection_and_inference_overhead_only",
                "used_for_heldout_metrics": False,
                "training_instance_count": 15,
                "training_source_record_count": 90,
            },
        )
        deployment = models["deployment_models"][POLICY_FULL_TREE]
        self.assertEqual(
            deployment["training_instance_ids"],
            sorted(
                item["instance_id"] for item in self.package["dataset"]["instances"]
            ),
        )
        self.assertEqual(len(deployment["training_source_record_ids"]), 90)
        self.assertEqual(
            deployment["training_source_record_ids"],
            sorted(self.package["dataset"]["source_record_ids"]),
        )
        self.assertTrue(
            all(
                len(fold["models"][POLICY_FULL_TREE]["training_instance_ids"])
                == 10
                and len(fold["training_source_record_ids"]) == 60
                for fold in models["folds"]
            )
        )
        evaluation = json.loads(
            (output / "evaluation.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("deployment_models", evaluation["evaluation"])
        self.assertNotIn("deployment_model_scope", evaluation["evaluation"])

    def test_source_hash_and_symlink_fail_closed(self) -> None:
        bad_hash = deepcopy(self.config)
        bad_hash["sources"]["stage4_protocol"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(MultifamilyArtifactError, "SHA mismatch"):
            build_multifamily_evaluation_package(
                self._write_config(bad_hash), repository_root=ROOT
            )

        link = self.directory / "protocol-link.json"
        link.symlink_to(ROOT / SOURCE_PATHS["stage4_protocol"])
        bad_link = deepcopy(self.config)
        bad_link["sources"]["stage4_protocol"] = {
            "path": link.relative_to(ROOT).as_posix(),
            "sha256": sha256_path(ROOT / SOURCE_PATHS["stage4_protocol"]),
        }
        with self.assertRaisesRegex(MultifamilyArtifactError, "symlinks"):
            build_multifamily_evaluation_package(
                self._write_config(bad_link), repository_root=ROOT
            )

    def test_completion_view_and_registry_provenance_fail_closed(self) -> None:
        completion = json.loads(
            (ROOT / SOURCE_PATHS["phaseb_completion"]).read_text(encoding="utf-8")
        )
        completion["analysis_views"]["balanced_broad"]["record_ids"].pop()
        relative = self._write_json("bad-completion.json", completion)
        bad_view = deepcopy(self.config)
        bad_view["sources"]["phaseb_completion"] = _file_claim(relative)
        with self.assertRaisesRegex(MultifamilyArtifactError, "balanced view count"):
            build_multifamily_evaluation_package(
                self._write_config(bad_view), repository_root=ROOT
            )

        registry = json.loads(
            (ROOT / SOURCE_PATHS["fe4s4_family_registry"]).read_text(encoding="utf-8")
        )
        registry["family"]["molecule"] = "fabricated"
        relative = self._write_json("bad-registry.json", registry)
        bad_registry = deepcopy(self.config)
        bad_registry["sources"]["fe4s4_family_registry"] = _file_claim(relative)
        with self.assertRaisesRegex(MultifamilyArtifactError, "registry family"):
            build_multifamily_evaluation_package(
                self._write_config(bad_registry), repository_root=ROOT
            )

    def test_writer_revalidates_split_leakage(self) -> None:
        malformed = deepcopy(self.package)
        split = malformed["evaluation"]["folds"][0]["split"]
        split["test_source_record_ids"].append(split["train_source_record_ids"][0])
        with self.assertRaisesRegex(
            MultifamilyArtifactError, "deterministic recomputation"
        ):
            write_multifamily_evaluation_artifacts(
                malformed, self.directory / "bad-output"
            )

    def test_writer_rejects_heldout_source_in_fold_model_before_writing(self) -> None:
        malformed = deepcopy(self.package)
        fold = malformed["evaluation"]["folds"][0]
        heldout_source_id = fold["test_source_record_ids"][0]
        fold["models"]["autosbd_full_tree"]["training_source_record_ids"][0] = (
            heldout_source_id
        )
        output = self.directory / "tampered-model-output"
        with self.assertRaisesRegex(
            MultifamilyArtifactError, "deterministic recomputation"
        ):
            write_multifamily_evaluation_artifacts(malformed, output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
