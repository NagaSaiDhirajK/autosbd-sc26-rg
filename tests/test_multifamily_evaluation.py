"""Tests for pure leakage-safe leave-one-family-out evaluation."""

from __future__ import annotations

from copy import deepcopy
import math
import unittest

from autosbd.evaluation import (
    CPU_CANDIDATE,
    FULL_FEATURE_NAMES,
    GPU_CANDIDATE,
    POLICY_FULL_TREE,
    POLICY_ORACLE,
    POLICY_ORDER,
    POLICY_SIZE_TREE,
    POLICY_THRESHOLD,
    TREE_MAX_DEPTH,
    TREE_MIN_SAMPLES_LEAF,
    EvaluationError,
)
from autosbd.multifamily_evaluation import (
    EXPECTED_FAMILY_ORDER,
    MULTIFAMILY_TREE_MAX_DEPTH,
    MULTIFAMILY_TREE_MIN_SAMPLES_LEAF,
    PROVENANCE_ONLY_FIELDS,
    build_multifamily_balanced_dataset,
    evaluate_multifamily_fold,
    evaluate_multifamily_selector,
    fit_multifamily_deployment_tree,
    make_leave_one_family_out_splits,
    validate_leave_one_family_out_split,
    validate_multifamily_dataset,
)


CONFIGURATION_COUNTS = (1024, 3025, 10000, 30276, 57121)
FAMILIES = (
    ("fe4s4", "Fe4S4", None, "upstream_not_reported"),
    ("n2", "N2", "6-31G", "reported"),
    ("h2o", "H2O", "cc-pVDZ", "reported"),
)
CANDIDATES = (
    (CPU_CANDIDATE, "cpu", 16),
    (GPU_CANDIDATE, "gpu", 1),
)


def make_fixture() -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Return final records plus warm-up, pilot, and extra-repetition distractors."""

    rows: list[dict[str, object]] = []
    metadata: dict[str, dict[str, object]] = {}
    for family_index, (family_id, molecule, basis, basis_status) in enumerate(FAMILIES):
        for size_index, n_configurations in enumerate(CONFIGURATION_COUNTS):
            # Labels intentionally collide across families.  Only family-aware
            # grouping can keep these as fifteen distinct instances.
            problem_instance = f"shared-prefix-{size_index:02d}"
            input_sha256 = f"{family_index * 10 + size_index + 1:064x}"
            work = n_configurations * (11 + family_index)
            features = {
                "n_configurations": n_configurations,
                "log1p_n_configurations": math.log1p(n_configurations),
                "method0_work_proxy": work,
                "log1p_method0_work_proxy": math.log1p(work),
                "connectivity": {
                    "alpha": {
                        "single_edge_density": 0.10 + 0.01 * family_index,
                        "double_edge_density": 0.20 + 0.01 * size_index,
                    },
                    "beta": {
                        "single_edge_density": 0.11 + 0.01 * family_index,
                        "double_edge_density": 0.21 + 0.01 * size_index,
                    },
                },
            }
            for candidate_index, (candidate_name, backend, threads) in enumerate(CANDIDATES):
                candidate = {
                    "name": candidate_name,
                    "backend": backend,
                    "cpu_threads": threads,
                }
                if backend == "cpu":
                    base_time = 0.7 + size_index * 1.1 + family_index * 0.25
                else:
                    base_time = 1.5 + size_index * 0.45 + family_index * 0.15

                warmup_id = f"warmup-{family_id}-{size_index}-{candidate_index}"
                warmup_row = _row(
                    trial_id=warmup_id,
                    family_id=family_id,
                    molecule=molecule,
                    basis=basis,
                    basis_status=basis_status,
                    problem_instance=problem_instance,
                    input_sha256=input_sha256,
                    candidate=candidate,
                    features=features,
                    phase="warmup",
                    repetition=0,
                    included=False,
                    wall_time_s=base_time,
                )
                rows.append(warmup_row)
                metadata[warmup_id] = _metadata(
                    warmup_row,
                    purpose="final",
                    timing_eligible=False,
                    family_id=family_id,
                )

                for repetition, factor in enumerate((0.98, 1.0, 1.02, 50.0, 0.01)):
                    trial_id = (
                        f"final-{family_id}-{size_index}-{candidate_index}-{repetition}"
                    )
                    final_row = _row(
                        trial_id=trial_id,
                        family_id=family_id,
                        molecule=molecule,
                        basis=basis,
                        basis_status=basis_status,
                        problem_instance=problem_instance,
                        input_sha256=input_sha256,
                        candidate=candidate,
                        features=features,
                        phase="measured",
                        repetition=repetition,
                        included=True,
                        wall_time_s=base_time * factor,
                    )
                    rows.append(final_row)
                    metadata[trial_id] = _metadata(
                        final_row,
                        purpose="final",
                        timing_eligible=True,
                        family_id=family_id,
                    )

                pilot_id = f"pilot-{family_id}-{size_index}-{candidate_index}"
                pilot_row = _row(
                    trial_id=pilot_id,
                    family_id=family_id,
                    molecule=molecule,
                    basis=basis,
                    basis_status=basis_status,
                    problem_instance=problem_instance,
                    input_sha256=input_sha256,
                    candidate=candidate,
                    features=features,
                    phase="measured",
                    repetition=0,
                    included=True,
                    wall_time_s=0.000001,
                )
                rows.append(pilot_row)
                metadata[pilot_id] = _metadata(
                    pilot_row,
                    purpose="pilot",
                    timing_eligible=True,
                    family_id=family_id,
                )
    return {"schema_version": 2, "rows": rows}, metadata


def _row(
    *,
    trial_id: str,
    family_id: str,
    molecule: str,
    basis: str | None,
    basis_status: str,
    problem_instance: str,
    input_sha256: str,
    candidate: dict[str, object],
    features: dict[str, object],
    phase: str,
    repetition: int,
    included: bool,
    wall_time_s: float,
) -> dict[str, object]:
    row: dict[str, object] = {
        "trial_id": trial_id,
        "included": included,
        "phase": phase,
        "repetition": repetition,
        "family_id": family_id,
        "molecule": molecule,
        "basis": basis,
        "problem_instance": problem_instance,
        "input_sha256": input_sha256,
        "candidate": dict(candidate),
        "times_s": {"wall": wall_time_s},
        "features": deepcopy(features),
    }
    # Schema-v3 families carry an explicit basis; Fe4S4's external registry
    # must retain the honest unknown-basis status.
    if basis is None:
        row["basis_status"] = basis_status
    return row


def _metadata(
    row: dict[str, object],
    *,
    purpose: str,
    timing_eligible: bool,
    family_id: str,
) -> dict[str, object]:
    candidate = row["candidate"]
    assert isinstance(candidate, dict)
    n_configurations = row["features"]["n_configurations"]  # type: ignore[index]
    repetition = row["repetition"]
    metadata: dict[str, object] = {
        "schema_version": 2 if family_id == "fe4s4" else 3,
        "trial_id": row["trial_id"],
        "problem_instance": row["problem_instance"],
        "input_sha256": row["input_sha256"],
        "repetition": repetition,
        "warmup_or_measured": row["phase"],
        "timing_eligible": timing_eligible,
        "status": "success",
        "correct": True,
        "protocol": {"purpose": purpose},
        "logical_identity": {"candidate": dict(candidate)},
        "estimated_cache_bytes": int(n_configurations) * 8,
        "source_memory_estimate": {
            "determinant_cache_bytes": int(n_configurations) * 8,
            "host_guard_bytes": 1_000_000 + int(n_configurations),
            "gpu_host_guard_bytes": 1_100_000 + int(n_configurations),
            "gpu_guard_bytes": 2_000_000 + int(n_configurations),
        },
        "preflight": {
            "host_memory_cap_bytes": 10_000_000 - int(repetition),
            "gpu_memory_cap_bytes": 9_000_000 - int(repetition),
        },
    }
    if family_id != "fe4s4":
        metadata.update(
            {
                "family_id": row["family_id"],
                "molecule": row["molecule"],
                "basis": row["basis"],
            }
        )
    return metadata


class MultifamilyDatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aggregate, self.metadata = make_fixture()
        self.dataset = build_multifamily_balanced_dataset(
            self.aggregate, metadata_by_record_id=self.metadata
        )

    def test_exact_geometry_exclusions_and_provenance_only_features(self) -> None:
        self.assertEqual(
            self.dataset["record_counts"],
            {
                "selected_measurements": 90,
                "candidate_rows": 30,
                "problem_instances": 15,
                "candidates_per_instance": 2,
                "repetitions_per_candidate": 3,
            },
        )
        self.assertEqual(len(self.dataset["families"]), 3)
        self.assertEqual(len(self.dataset["instances"]), 15)
        self.assertEqual(len(self.dataset["rows"]), 30)
        self.assertEqual(len(self.dataset["source_record_ids"]), 90)
        self.assertTrue(
            all(record_id.startswith("final-") for record_id in self.dataset["source_record_ids"])
        )
        self.assertTrue(
            all(record_id.rsplit("-", 1)[-1] in {"0", "1", "2"} for record_id in self.dataset["source_record_ids"])
        )
        self.assertEqual(
            {row["problem_instance"] for row in self.dataset["rows"]},
            {f"shared-prefix-{index:02d}" for index in range(5)},
        )
        self.assertEqual(
            len({row["instance_id"] for row in self.dataset["rows"]}), 15
        )
        for row in self.dataset["rows"]:
            self.assertEqual(row["repetitions"], [0, 1, 2])
            self.assertEqual(len(row["source_record_ids"]), 3)
            self.assertFalse(PROVENANCE_ONLY_FIELDS.intersection(row["feature_values"]))
            self.assertEqual(
                set(FULL_FEATURE_NAMES).intersection(row["feature_values"]),
                set(FULL_FEATURE_NAMES),
            )
        fe4s4 = next(
            family for family in self.dataset["families"] if family["family_id"] == "fe4s4"
        )
        self.assertIsNone(fe4s4["basis"])
        self.assertEqual(fe4s4["basis_status"], "upstream_not_reported")
        self.assertEqual(fe4s4["measurement_records"], 30)
        self.assertEqual(fe4s4["candidate_rows"], 10)

    def test_leave_one_family_out_has_zero_group_or_source_leakage(self) -> None:
        folds = make_leave_one_family_out_splits(self.dataset)
        self.assertEqual(
            [fold["heldout_family_id"] for fold in folds],
            list(EXPECTED_FAMILY_ORDER),
        )
        for fold in folds:
            self.assertEqual(len(fold["train_instance_ids"]), 10)
            self.assertEqual(len(fold["test_instance_ids"]), 5)
            self.assertEqual(len(fold["train_source_record_ids"]), 60)
            self.assertEqual(len(fold["test_source_record_ids"]), 30)
            self.assertFalse(
                set(fold["train_instance_ids"]).intersection(fold["test_instance_ids"])
            )
            self.assertFalse(
                set(fold["train_source_record_ids"]).intersection(
                    fold["test_source_record_ids"]
                )
            )
            validate_leave_one_family_out_split(self.dataset, fold)

        leaked = deepcopy(folds[0])
        leaked["train_instance_ids"].append(leaked["test_instance_ids"][0])
        with self.assertRaisesRegex(EvaluationError, "instance leakage"):
            validate_leave_one_family_out_split(self.dataset, leaked)

        source_leaked = deepcopy(folds[0])
        source_leaked["train_source_record_ids"].append(
            source_leaked["test_source_record_ids"][0]
        )
        with self.assertRaisesRegex(EvaluationError, "source-record leakage"):
            validate_leave_one_family_out_split(self.dataset, source_leaked)

    def test_fail_closed_geometry_and_provenance_feature_leakage(self) -> None:
        missing = deepcopy(self.aggregate)
        removed = next(
            row
            for row in missing["rows"]
            if row["trial_id"].startswith("final-")
            and row["trial_id"].endswith("-2")
        )
        missing["rows"].remove(removed)
        with self.assertRaisesRegex(EvaluationError, "requires 90 measurements"):
            build_multifamily_balanced_dataset(
                missing, metadata_by_record_id=self.metadata
            )

        admitted_pilots = deepcopy(self.metadata)
        for trial_id, metadata in admitted_pilots.items():
            if trial_id.startswith("pilot-"):
                metadata["protocol"] = {"purpose": "final"}
        with self.assertRaisesRegex(EvaluationError, "duplicate repetition 0"):
            build_multifamily_balanced_dataset(
                self.aggregate, metadata_by_record_id=admitted_pilots
            )

        leaked_features = deepcopy(self.dataset)
        leaked_features["rows"][0]["feature_values"]["family_id"] = 1.0
        with self.assertRaisesRegex(EvaluationError, "feature-value contract"):
            validate_multifamily_dataset(leaked_features)

        swapped_instances = deepcopy(self.dataset)
        fe4s4 = next(
            item
            for item in swapped_instances["instances"]
            if item["family_id"] == "fe4s4"
        )
        n2 = next(
            item
            for item in swapped_instances["instances"]
            if item["family_id"] == "n2"
        )
        fe4s4["family_id"], n2["family_id"] = n2["family_id"], fe4s4["family_id"]
        with self.assertRaisesRegex(EvaluationError, "instance summary differs"):
            validate_multifamily_dataset(swapped_instances)

        changed_family_summary = deepcopy(self.dataset)
        changed_family_summary["families"][0]["measurement_records"] = 29
        with self.assertRaisesRegex(EvaluationError, "family summary differs"):
            validate_multifamily_dataset(changed_family_summary)


class MultifamilyEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.aggregate, cls.metadata = make_fixture()
        cls.dataset = build_multifamily_balanced_dataset(
            cls.aggregate, metadata_by_record_id=cls.metadata
        )
        cls.evaluation = evaluate_multifamily_selector(cls.dataset)

    def test_all_policies_pooled_and_per_family_metrics_are_complete(self) -> None:
        evaluation = self.evaluation
        self.assertEqual(len(evaluation["folds"]), 3)
        self.assertEqual(len(evaluation["predictions"]), 90)
        self.assertEqual(set(evaluation["metrics"]), set(POLICY_ORDER))
        self.assertEqual(
            set(evaluation["per_heldout_family_metrics"]),
            set(EXPECTED_FAMILY_ORDER),
        )
        for policy in POLICY_ORDER:
            rows = [row for row in evaluation["predictions"] if row["policy"] == policy]
            self.assertEqual(len(rows), 15)
            self.assertEqual(evaluation["metrics"][policy]["instances_total"], 15)
        for family_id in EXPECTED_FAMILY_ORDER:
            for policy in POLICY_ORDER:
                self.assertEqual(
                    evaluation["per_heldout_family_metrics"][family_id][policy][
                        "instances_total"
                    ],
                    5,
                )
        oracle_rows = [
            row for row in evaluation["predictions"] if row["policy"] == POLICY_ORACLE
        ]
        self.assertTrue(all(row["valid"] for row in oracle_rows))
        self.assertTrue(all(row["normalized_regret"] == 0.0 for row in oracle_rows))
        self.assertEqual(
            evaluation["metrics"][POLICY_ORACLE][
                "geometric_mean_selected_over_oracle_valid_only"
            ],
            1.0,
        )

    def test_local_tree_contract_and_existing_evaluator_constants_are_untouched(self) -> None:
        self.assertEqual((TREE_MAX_DEPTH, TREE_MIN_SAMPLES_LEAF), (2, 1))
        self.assertEqual(
            (MULTIFAMILY_TREE_MAX_DEPTH, MULTIFAMILY_TREE_MIN_SAMPLES_LEAF),
            (3, 2),
        )
        for fold in self.evaluation["folds"]:
            for policy in (POLICY_SIZE_TREE, POLICY_FULL_TREE):
                model = fold["models"][policy]
                self.assertEqual(model["hyperparameters"]["max_depth"], 3)
                self.assertEqual(model["hyperparameters"]["min_samples_leaf"], 2)
                self.assertLessEqual(model["tree"]["actual_depth"], 3)
                self.assertFalse(
                    PROVENANCE_ONLY_FIELDS.intersection(model["feature_names"])
                )
                self.assertEqual(len(model["training_source_record_ids"]), 60)
                self.assertFalse(
                    set(model["training_source_record_ids"]).intersection(
                        fold["test_source_record_ids"]
                    )
                )
            threshold = fold["models"][POLICY_THRESHOLD]
            self.assertEqual(len(threshold["training_source_record_ids"]), 60)
            self.assertFalse(
                set(threshold["training_source_record_ids"]).intersection(
                    fold["test_source_record_ids"]
                )
            )

    def test_deployment_tree_is_deterministic_and_bound_to_all_balanced_data(
        self,
    ) -> None:
        model = fit_multifamily_deployment_tree(self.dataset)
        self.assertEqual(model, fit_multifamily_deployment_tree(self.dataset))
        self.assertEqual(model["feature_set"], "full")
        self.assertEqual(model["feature_names"], list(FULL_FEATURE_NAMES))
        self.assertFalse(
            PROVENANCE_ONLY_FIELDS.intersection(model["feature_names"])
        )
        self.assertEqual(
            model["training_instance_ids"],
            sorted(item["instance_id"] for item in self.dataset["instances"]),
        )
        self.assertEqual(len(model["training_instance_ids"]), 15)
        self.assertEqual(
            model["training_source_record_ids"],
            sorted(self.dataset["source_record_ids"]),
        )
        self.assertEqual(len(model["training_source_record_ids"]), 90)
        self.assertNotIn("deployment_models", self.evaluation)

    def test_heldout_mutation_cannot_change_fitted_training_models(self) -> None:
        split = make_leave_one_family_out_splits(self.dataset)[0]
        baseline = evaluate_multifamily_fold(self.dataset, split)
        changed = deepcopy(self.dataset)
        for row in changed["rows"]:
            if row["family_id"] == split["heldout_family_id"]:
                row["median_wall_time_s"] *= 1000.0
                row["target_log1p_median_wall_time_s"] = math.log1p(
                    row["median_wall_time_s"]
                )
        mutated = evaluate_multifamily_fold(changed, split)
        self.assertEqual(mutated["models"], baseline["models"])
        self.assertNotEqual(mutated["predictions"], baseline["predictions"])

    def test_dataset_and_evaluation_are_deterministic_under_input_reordering(self) -> None:
        reversed_aggregate = deepcopy(self.aggregate)
        reversed_aggregate["rows"] = list(reversed(reversed_aggregate["rows"]))
        reversed_metadata = dict(reversed(list(self.metadata.items())))
        second_dataset = build_multifamily_balanced_dataset(
            reversed_aggregate, metadata_by_record_id=reversed_metadata
        )
        self.assertEqual(second_dataset, self.dataset)
        self.assertEqual(
            evaluate_multifamily_selector(second_dataset), self.evaluation
        )


if __name__ == "__main__":
    unittest.main()
