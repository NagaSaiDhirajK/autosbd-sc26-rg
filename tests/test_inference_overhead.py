"""Invariant tests for Stage 5 inference-overhead measurement."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from autosbd.evaluation import (
    CPU_CANDIDATE,
    EXPECTED_CANDIDATES,
    FULL_FEATURE_NAMES,
    GPU_CANDIDATE,
    POLICY_FULL_TREE,
)
from autosbd.inference_overhead import (
    COLD_MEASURED_ITERATIONS,
    HOT_MEASURED_ITERATIONS,
    InferenceOverheadError,
    load_deployment_model,
    load_inference_inputs,
    measure_latency_path,
    summarize_latency_samples,
    validate_measurement_protocol,
    write_immutable_raw_record,
    write_processed_artifacts,
)


class InferenceOverheadTests(unittest.TestCase):
    def _model_artifact(self) -> dict[str, object]:
        model = {
            "schema_version": 1,
            "model_type": "sklearn.tree.DecisionTreeRegressor",
            "feature_set": "full",
            "feature_names": list(FULL_FEATURE_NAMES),
            "tree": {
                "node_count": 1,
                "actual_depth": 0,
                "leaf_count": 1,
                "nodes": [
                    {
                        "node_id": 0,
                        "type": "leaf",
                        "value_log1p_median_wall_time_s": 1.0,
                    }
                ],
            },
        }
        return {
            "schema_version": 1,
            "config": {
                "name": "fixture-stage5",
                "path": "configs/fixture.yaml",
                "sha256": "a" * 64,
            },
            "deployment_models": {POLICY_FULL_TREE: model},
        }

    def _dataset(self) -> dict[str, object]:
        rows: list[dict[str, object]] = []
        sizes = (4, 9, 16, 25, 36)
        for instance_index, size in enumerate(sizes):
            instance = f"fixture-{instance_index}"
            for candidate_name, (backend, threads) in EXPECTED_CANDIDATES.items():
                features = {name: 0.25 for name in FULL_FEATURE_NAMES}
                features["log1p_n_configurations"] = math.log1p(size)
                features["backend_gpu"] = 1.0 if backend == "gpu" else 0.0
                features["cpu_threads"] = float(threads)
                rows.append(
                    {
                        "problem_instance": instance,
                        "candidate_name": candidate_name,
                        "backend": backend,
                        "n_configurations": size,
                        "median_wall_time_s": float(instance_index + 1)
                        + (0.25 if backend == "gpu" else 0.0),
                        "feature_values": features,
                        "memory_guard": {
                            "host_guard_bytes": 10,
                            "gpu_host_guard_bytes": 10,
                            "gpu_guard_bytes": 10,
                        },
                        "memory_caps": {
                            "host_cap_bytes": 100,
                            "gpu_cap_bytes": 100,
                        },
                        "source_record_ids": [
                            f"{instance}-{candidate_name}-{repetition}"
                            for repetition in range(3)
                        ],
                    }
                )
        return {
            "schema_version": 1,
            "dataset_type": "autosbd_balanced_candidate_medians",
            "record_counts": {
                "selected_measurements": 30,
                "candidate_rows": 10,
                "problem_instances": 5,
                "candidates_per_instance": 2,
                "repetitions_per_candidate": 3,
            },
            "rows": rows,
        }

    def test_inputs_are_strict_and_project_only_preexecution_selection_fields(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            models = root / "models.json"
            dataset = root / "balanced_dataset.json"
            models.write_text(json.dumps(self._model_artifact()), encoding="utf-8")
            dataset.write_text(json.dumps(self._dataset()), encoding="utf-8")

            inputs = load_inference_inputs(
                models, dataset, repository_root=root
            )
            self.assertEqual(len(inputs["candidate_groups"]), 5)
            self.assertEqual(
                inputs["workload"]["shortest_measured_sbd_candidate_median"][
                    "median_wall_time_s"
                ],
                1.0,
            )
            for group in inputs["candidate_groups"]:
                self.assertEqual(len(group["candidate_rows"]), 2)
                for row in group["candidate_rows"]:
                    self.assertEqual(
                        set(row),
                        {
                            "candidate_name",
                            "backend",
                            "feature_values",
                            "memory_guard",
                            "memory_caps",
                        },
                    )
                    self.assertNotIn("median_wall_time_s", row)

            loaded = load_deployment_model(models)
            self.assertEqual(loaded["feature_names"], list(FULL_FEATURE_NAMES))

    def test_strict_loader_rejects_duplicate_and_nonfinite_json(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "models.json"
            path.write_text(
                '{"schema_version":1,"schema_version":1}', encoding="utf-8"
            )
            with self.assertRaisesRegex(InferenceOverheadError, "duplicate JSON key"):
                load_deployment_model(path)
            path.write_text('{"schema_version":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(InferenceOverheadError, "non-finite"):
                load_deployment_model(path)

    def test_fake_clock_measurement_consumes_choices_and_summary_is_ordered(self) -> None:
        ticks = iter((0, 1_000, 2_000, 4_000, 5_000, 8_000))
        calls: list[int] = []

        def operation(index: int) -> str:
            calls.append(index)
            return CPU_CANDIDATE if index % 2 == 0 else GPU_CANDIDATE

        measurement = measure_latency_path(
            operation,
            warmup_iterations=2,
            measured_iterations=3,
            clock_ns=lambda: next(ticks),
        )
        self.assertEqual(calls, [0, 1, 0, 1, 2])
        self.assertEqual(measurement["samples_ns"], [1_000, 2_000, 3_000])
        self.assertEqual(
            measurement["selected_candidate_counts"],
            {CPU_CANDIDATE: 2, GPU_CANDIDATE: 1},
        )
        self.assertRegex(measurement["selection_checksum_sha256"], r"^[0-9a-f]{64}$")
        summary = summarize_latency_samples(measurement["samples_ns"])
        self.assertEqual(summary["iteration_count"], 3)
        ordered = [
            summary["minimum_us"],
            summary["median_us"],
            summary["p90_us"],
            summary["p95_us"],
            summary["maximum_us"],
        ]
        self.assertTrue(all(math.isfinite(value) for value in ordered))
        self.assertEqual(ordered, sorted(ordered))

    def test_production_protocol_enforces_iteration_minima(self) -> None:
        protocol = validate_measurement_protocol()
        self.assertEqual(
            protocol["hot_selection"]["measured_iterations"],
            HOT_MEASURED_ITERATIONS,
        )
        self.assertEqual(
            protocol["cold_load_plus_selection"]["measured_iterations"],
            COLD_MEASURED_ITERATIONS,
        )
        with self.assertRaisesRegex(InferenceOverheadError, "hot path requires"):
            validate_measurement_protocol(hot_measured_iterations=9_999)
        with self.assertRaisesRegex(InferenceOverheadError, "cold path with file I/O"):
            validate_measurement_protocol(cold_measured_iterations=99)

    def test_raw_samples_are_immutable_and_processed_outputs_reference_them(self) -> None:
        protocol = validate_measurement_protocol()
        hot_samples = [1_000] * HOT_MEASURED_ITERATIONS
        cold_samples = [200_000] * COLD_MEASURED_ITERATIONS
        raw_record = {
            "schema_version": 1,
            "artifact_type": "autosbd_inference_overhead_raw",
            "status": "complete",
            "run_id": "b" * 64,
            "timestamp_utc": "2026-08-01T00:00:00.000000Z",
            "config": {"name": "fixture"},
            "sources": {
                "models": {"path": "models.json", "sha256": "c" * 64},
                "balanced_dataset": {
                    "path": "balanced_dataset.json",
                    "sha256": "d" * 64,
                },
            },
            "protocol": protocol,
            "workload": {
                "shortest_measured_sbd_candidate_median": {
                    "problem_instance": "fixture-0",
                    "candidate_name": CPU_CANDIDATE,
                    "median_wall_time_s": 1.0,
                }
            },
            "measurements": {
                "hot_selection": {
                    "samples_ns": hot_samples,
                    "selected_candidate_counts": {
                        CPU_CANDIDATE: HOT_MEASURED_ITERATIONS
                    },
                    "selection_checksum_sha256": "e" * 64,
                },
                "cold_load_plus_selection": {
                    "samples_ns": cold_samples,
                    "selected_candidate_counts": {
                        CPU_CANDIDATE: COLD_MEASURED_ITERATIONS
                    },
                    "selection_checksum_sha256": "f" * 64,
                },
            },
        }
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            raw_path = write_immutable_raw_record(raw_record, root / "raw")
            with self.assertRaisesRegex(InferenceOverheadError, "refusing to overwrite"):
                write_immutable_raw_record(raw_record, root / "raw")
            payload = raw_path.read_bytes()
            raw_claim = {
                "path": "raw/" + raw_path.name,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
            result = write_processed_artifacts(
                raw_record,
                raw_claim=raw_claim,
                output_directory=root / "processed",
            )
            self.assertTrue(all(result["changed"].values()))
            summary = json.loads(
                (root / "processed/inference_overhead.json").read_text()
            )
            self.assertEqual(summary["source_raw_record"], raw_claim)
            hot = summary["measurements"]["hot_selection"]
            cold = summary["measurements"]["cold_load_plus_selection"]
            self.assertEqual(hot["iteration_count"], HOT_MEASURED_ITERATIONS)
            self.assertEqual(cold["iteration_count"], COLD_MEASURED_ITERATIONS)
            self.assertLessEqual(hot["minimum_us"], hot["median_us"])
            self.assertLessEqual(hot["median_us"], hot["p90_us"])
            self.assertLessEqual(hot["p90_us"], hot["p95_us"])
            self.assertLessEqual(hot["p95_us"], hot["maximum_us"])
            self.assertAlmostEqual(
                summary["comparison"][
                    "hot_median_percent_of_shortest_sbd_runtime"
                ],
                0.0001,
            )
            with (root / "processed/inference_overhead.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["measurement"] for row in rows], [
                "hot_selection",
                "cold_load_plus_selection",
            ])
            self.assertEqual(rows[0]["raw_record_sha256"], raw_claim["sha256"])
            self.assertEqual(rows[1]["hot_median_percent_of_shortest_sbd_runtime"], "")


if __name__ == "__main__":
    unittest.main()
