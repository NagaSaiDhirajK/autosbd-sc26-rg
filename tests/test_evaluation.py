"""Tests for leakage-safe AutoSBD selector training and evaluation."""

from __future__ import annotations

from copy import deepcopy
import math
import unittest

from autosbd.evaluation import (
    CPU_CANDIDATE,
    FULL_FEATURE_NAMES,
    GPU_CANDIDATE,
    POLICY_FULL_TREE,
    SIZE_ONLY_FEATURE_NAMES,
    EvaluationError,
    build_balanced_dataset,
    evaluate_fold,
    evaluate_selector,
    fit_runtime_tree,
    fit_static_threshold,
    make_leave_one_instance_out_splits,
    make_primary_split,
    normalized_regret,
    select_with_static_threshold,
    select_with_tree,
    summarize_policy_predictions,
    tree_model_json,
    validate_split,
)


SIZES = (16, 32, 64, 128, 256)
CPU_TIMES = (1.0, 2.0, 4.0, 8.0, 16.0)
GPU_TIMES = (2.0, 1.5, 2.5, 3.0, 4.0)


def make_fixture() -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Return a Stage-4-shaped 48-record aggregate and raw metadata map."""

    rows: list[dict[str, object]] = []
    metadata: dict[str, dict[str, object]] = {}
    candidate_specs = (
        (GPU_CANDIDATE, "gpu", 1, GPU_TIMES),
        (CPU_CANDIDATE, "cpu", 16, CPU_TIMES),
    )
    for size_index, size in enumerate(SIZES):
        instance = f"fixture-{size:04d}"
        input_sha256 = f"{size_index + 1:064x}"
        work = size * size * 11
        features = {
            "n_configurations": size,
            "log1p_n_configurations": math.log1p(size),
            "method0_work_proxy": work,
            "log1p_method0_work_proxy": math.log1p(work),
            "connectivity": {
                "alpha": {
                    "single_edge_density": 0.20 + 0.01 * size_index,
                    "double_edge_density": 0.10 + 0.01 * size_index,
                },
                "beta": {
                    "single_edge_density": 0.21 + 0.01 * size_index,
                    "double_edge_density": 0.11 + 0.01 * size_index,
                },
            },
        }
        for candidate_name, backend, threads, base_times in candidate_specs:
            warmup_id = f"warmup-{size}-{candidate_name}"
            rows.append(
                {
                    "trial_id": warmup_id,
                    "included": False,
                    "phase": "warmup",
                    "repetition": 0,
                    "problem_instance": instance,
                    "input_sha256": input_sha256,
                    "candidate": {
                        "name": candidate_name,
                        "backend": backend,
                        "cpu_threads": threads,
                    },
                    "times_s": {"wall": base_times[size_index]},
                    "features": deepcopy(features),
                }
            )
            repetitions = 5 if size_index < 2 else 3
            for repetition in range(repetitions):
                trial_id = f"measured-{size}-{candidate_name}-{repetition}"
                factor = (1.0, 0.98, 1.02, 1.50, 0.50)[repetition]
                rows.append(
                    {
                        "trial_id": trial_id,
                        "included": True,
                        "phase": "measured",
                        "repetition": repetition,
                        "problem_instance": instance,
                        "input_sha256": input_sha256,
                        "candidate": {
                            "name": candidate_name,
                            "backend": backend,
                            "cpu_threads": threads,
                        },
                        "times_s": {"wall": base_times[size_index] * factor},
                        "features": deepcopy(features),
                    }
                )
                metadata[trial_id] = {
                    "trial_id": trial_id,
                    "problem_instance": instance,
                    "input_sha256": input_sha256,
                    "estimated_cache_bytes": size * 64,
                    "source_memory_estimate": {
                        "determinant_cache_bytes": size * 64,
                        "host_guard_bytes": 1_000 + size,
                        "gpu_host_guard_bytes": 1_200 + size,
                        "gpu_guard_bytes": 800 + size,
                    },
                    "preflight": {
                        "host_memory_cap_bytes": 10_000 - repetition,
                        "gpu_memory_cap_bytes": 9_000 - repetition,
                    },
                }
    return {
        "schema_version": 1,
        "rows": rows,
        "record_counts": {"input": 48, "included": 38, "excluded": 10},
    }, metadata


class BalancedDatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aggregate, self.metadata = make_fixture()
        self.dataset = build_balanced_dataset(
            self.aggregate, metadata_by_record_id=self.metadata
        )

    def test_exact_balanced_counts_and_median_targets(self) -> None:
        self.assertEqual(len(self.aggregate["rows"]), 48)
        self.assertEqual(
            self.dataset["record_counts"],
            {
                "selected_measurements": 30,
                "candidate_rows": 10,
                "problem_instances": 5,
                "candidates_per_instance": 2,
                "repetitions_per_candidate": 3,
            },
        )
        self.assertEqual(len(self.dataset["source_record_ids"]), 30)
        for row in self.dataset["rows"]:
            self.assertEqual(row["repetitions"], [0, 1, 2])
            self.assertEqual(len(row["source_record_ids"]), 3)
            self.assertAlmostEqual(
                row["target_log1p_median_wall_time_s"],
                math.log1p(row["median_wall_time_s"]),
            )
            self.assertEqual(
                list(self.dataset["feature_names"]["size_only"]),
                list(SIZE_ONLY_FEATURE_NAMES),
            )

    def test_missing_or_nonfinite_preexecution_feature_fails_closed(self) -> None:
        missing = dict(self.metadata)
        missing.pop("measured-16-amd-cpu-16-0")
        with self.assertRaisesRegex(EvaluationError, "source_memory_estimate"):
            build_balanced_dataset(
                self.aggregate, metadata_by_record_id=missing
            )

        malformed = deepcopy(self.aggregate)
        selected = next(
            row
            for row in malformed["rows"]
            if row["trial_id"] == "measured-16-amd-cpu-16-0"
        )
        selected["features"]["connectivity"]["alpha"][
            "single_edge_density"
        ] = float("nan")
        with self.assertRaisesRegex(EvaluationError, "must be finite"):
            build_balanced_dataset(
                malformed, metadata_by_record_id=self.metadata
            )

    def test_primary_and_leave_one_out_splits_have_no_leakage(self) -> None:
        primary = make_primary_split(self.dataset)
        self.assertEqual(primary["test_instance_ids"], ["fixture-0256"])
        self.assertEqual(len(primary["train_instance_ids"]), 4)
        self.assertEqual(len(primary["train_source_record_ids"]), 24)
        self.assertEqual(len(primary["test_source_record_ids"]), 6)
        self.assertFalse(
            set(primary["train_source_record_ids"]).intersection(
                primary["test_source_record_ids"]
            )
        )

        folds = make_leave_one_instance_out_splits(self.dataset)
        self.assertEqual(len(folds), 5)
        self.assertEqual(
            {fold["test_instance_ids"][0] for fold in folds},
            {f"fixture-{size:04d}" for size in SIZES},
        )
        for fold in folds:
            self.assertEqual(len(fold["train_instance_ids"]), 4)
            self.assertEqual(len(fold["test_instance_ids"]), 1)
            validate_split(self.dataset, fold)

        leaked = deepcopy(primary)
        leaked["test_instance_ids"].append(primary["train_instance_ids"][0])
        with self.assertRaisesRegex(EvaluationError, "leakage"):
            validate_split(self.dataset, leaked)


class ModelAndPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        aggregate, metadata = make_fixture()
        self.dataset = build_balanced_dataset(
            aggregate, metadata_by_record_id=metadata
        )
        self.primary = make_primary_split(self.dataset)
        train_ids = set(self.primary["train_instance_ids"])
        test_ids = set(self.primary["test_instance_ids"])
        self.train_rows = [
            row
            for row in self.dataset["rows"]
            if row["problem_instance"] in train_ids
        ]
        self.test_rows = [
            row
            for row in self.dataset["rows"]
            if row["problem_instance"] in test_ids
        ]

    def test_static_threshold_is_train_only_with_deterministic_tie_break(self) -> None:
        fitted = fit_static_threshold(self.train_rows)
        self.assertEqual(fitted["kind"], "geometric_midpoint")
        self.assertAlmostEqual(
            fitted["threshold_n_configurations"], math.sqrt(16 * 32)
        )
        candidates = fitted["candidate_objectives"]
        self.assertEqual(
            [candidate["kind"] for candidate in candidates],
            [
                "always_gpu",
                "geometric_midpoint",
                "geometric_midpoint",
                "geometric_midpoint",
                "always_cpu",
            ],
        )
        self.assertEqual(
            [candidate["threshold_n_configurations"] for candidate in candidates],
            [
                None,
                math.sqrt(16 * 32),
                math.sqrt(32 * 64),
                math.sqrt(64 * 128),
                None,
            ],
        )
        self.assertEqual(
            fitted["training_instance_ids"], sorted(self.primary["train_instance_ids"])
        )
        self.assertEqual(select_with_static_threshold(fitted, 22), CPU_CANDIDATE)
        self.assertEqual(select_with_static_threshold(fitted, 23), GPU_CANDIDATE)

        changed_test = deepcopy(self.test_rows)
        for row in changed_test:
            row["median_wall_time_s"] *= 1_000_000
            row["target_log1p_median_wall_time_s"] = math.log1p(
                row["median_wall_time_s"]
            )
        changed_dataset = deepcopy(self.dataset)
        changed_by_candidate = {
            row["candidate_name"]: row for row in changed_test
        }
        for row in changed_dataset["rows"]:
            if row["problem_instance"] in self.primary["test_instance_ids"]:
                changed = changed_by_candidate[row["candidate_name"]]
                row["median_wall_time_s"] = changed["median_wall_time_s"]
                row["target_log1p_median_wall_time_s"] = changed[
                    "target_log1p_median_wall_time_s"
                ]
        changed_evaluation = evaluate_fold(changed_dataset, self.primary)
        self.assertEqual(
            (fitted["kind"], fitted["threshold_n_configurations"]),
            (
                changed_evaluation["models"]["static_size_threshold"]["kind"],
                changed_evaluation["models"]["static_size_threshold"][
                    "threshold_n_configurations"
                ],
            ),
        )

        tied = deepcopy(self.train_rows)
        for row in tied:
            row["median_wall_time_s"] = 1.0
            row["target_log1p_median_wall_time_s"] = math.log1p(1.0)
        tied_model = fit_static_threshold(tied)
        self.assertEqual(tied_model["kind"], "always_gpu")
        self.assertIsNone(tied_model["threshold_n_configurations"])
        self.assertIn("registered candidate order", tied_model["tie_break"])
        self.assertEqual(select_with_static_threshold(tied_model, 1_000), GPU_CANDIDATE)
        self.assertEqual(
            select_with_static_threshold(
                {"kind": "always_cpu", "threshold_n_configurations": None}, 1
            ),
            CPU_CANDIDATE,
        )

    def test_tree_export_is_deterministic_and_uses_fixed_depth_two(self) -> None:
        first = fit_runtime_tree(self.train_rows, feature_names=FULL_FEATURE_NAMES)
        second = fit_runtime_tree(
            list(reversed(self.train_rows)), feature_names=FULL_FEATURE_NAMES
        )
        self.assertEqual(tree_model_json(first), tree_model_json(second))
        self.assertEqual(first["hyperparameters"]["max_depth"], 2)
        self.assertEqual(first["hyperparameters"]["min_samples_leaf"], 1)
        self.assertEqual(first["hyperparameters"]["random_state"], 1729)
        self.assertLessEqual(first["tree"]["actual_depth"], 2)
        self.assertEqual(len(first["training_source_record_ids"]), 24)

    def test_feasibility_filter_runs_before_feature_prediction(self) -> None:
        constant_model = {
            "feature_names": list(FULL_FEATURE_NAMES),
            "tree": {
                "nodes": [
                    {
                        "node_id": 0,
                        "type": "leaf",
                        "value_log1p_median_wall_time_s": 1.0,
                    }
                ]
            },
        }
        rows = deepcopy(self.test_rows)
        gpu = next(row for row in rows if row["candidate_name"] == GPU_CANDIDATE)
        gpu["feature_values"].pop("log1p_method0_work_proxy")
        gpu["memory_guard"]["gpu_guard_bytes"] = (
            gpu["memory_caps"]["gpu_cap_bytes"] + 1
        )
        selection = select_with_tree(constant_model, rows)
        self.assertEqual(selection["selected_candidate_name"], CPU_CANDIDATE)
        self.assertEqual(len(selection["predictions"]), 1)

        gpu["memory_guard"]["gpu_guard_bytes"] = 1
        with self.assertRaisesRegex(EvaluationError, "must be numeric"):
            select_with_tree(constant_model, rows)

    def test_equal_tree_predictions_use_documented_candidate_tie_break(self) -> None:
        constant_model = {
            "feature_names": list(SIZE_ONLY_FEATURE_NAMES),
            "tree": {
                "nodes": [
                    {
                        "node_id": 0,
                        "type": "leaf",
                        "value_log1p_median_wall_time_s": 1.0,
                    }
                ]
            },
        }
        selection = select_with_tree(constant_model, self.test_rows)
        self.assertEqual(selection["selected_candidate_name"], CPU_CANDIDATE)
        self.assertIn("lexicographically", selection["tie_break"])

    def test_complete_evaluation_serializes_folds_models_and_policies(self) -> None:
        result = evaluate_selector(self.dataset)
        primary = result["primary"]
        self.assertEqual(len(primary["split"]["train_instance_ids"]), 4)
        self.assertEqual(len(primary["predictions"]), 6)
        self.assertEqual(
            primary["policy_aliases"]["upstream_default"], "fixed_gpu"
        )
        self.assertEqual(
            [row["policy"] for row in primary["predictions"]],
            [
                "fixed_cpu16",
                "fixed_gpu",
                "static_size_threshold",
                "size_only_tree_ablation",
                "autosbd_full_tree",
                "measured_feasible_oracle",
            ],
        )
        self.assertNotIn("upstream_default", primary["metrics"])
        self.assertTrue(primary["models"][POLICY_FULL_TREE]["tree"]["nodes"])
        self.assertEqual(len(primary["training_source_record_ids"]), 24)
        secondary = result["secondary_leave_one_instance_out"]
        self.assertEqual(len(secondary["folds"]), 5)
        self.assertEqual(len(secondary["predictions"]), 30)
        self.assertNotIn("upstream_default", secondary["metrics"])


class MetricTests(unittest.TestCase):
    def test_metric_math_including_invalid_and_failure_denominators(self) -> None:
        predictions = [
            {
                "policy": "fixture-policy",
                "valid": True,
                "failure": False,
                "selection_correct": True,
                "within_5pct_oracle": True,
                "normalized_runtime": 1.0,
                "normalized_regret": 0.0,
                "speedup_vs_fixed_cpu": 1.0,
                "speedup_vs_fixed_gpu": 2.0,
            },
            {
                "policy": "fixture-policy",
                "valid": True,
                "failure": False,
                "selection_correct": False,
                "within_5pct_oracle": False,
                "normalized_runtime": 2.0,
                "normalized_regret": 1.0,
                "speedup_vs_fixed_cpu": 0.5,
                "speedup_vs_fixed_gpu": 1.0,
            },
            {
                "policy": "fixture-policy",
                "valid": False,
                "failure": True,
                "selection_correct": False,
                "within_5pct_oracle": False,
                "normalized_runtime": None,
                "normalized_regret": None,
                "speedup_vs_fixed_cpu": None,
                "speedup_vs_fixed_gpu": None,
            },
        ]
        metrics = summarize_policy_predictions(predictions)
        self.assertAlmostEqual(
            metrics["geometric_mean_selected_over_oracle_valid_only"],
            math.sqrt(2.0),
        )
        self.assertAlmostEqual(metrics["median_normalized_regret_valid_only"], 0.5)
        self.assertAlmostEqual(metrics["p90_normalized_regret_valid_only"], 0.9)
        self.assertAlmostEqual(metrics["selection_accuracy"], 1.0 / 3.0)
        self.assertAlmostEqual(metrics["invalid_rate"], 1.0 / 3.0)
        self.assertAlmostEqual(metrics["failure_rate"], 1.0 / 3.0)
        self.assertEqual(normalized_regret(4.0, 2.0), 1.0)


if __name__ == "__main__":
    unittest.main()
