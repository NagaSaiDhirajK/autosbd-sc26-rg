"""Measure and record AutoSBD deployment-selector inference overhead.

The hot path measures the deployed full-tree selector with an already loaded
model.  The cold diagnostic additionally reads and strictly deserializes the
saved ``models.json`` artifact for every selection.  Candidate projections
contain only pre-execution fields; measured runtimes are used solely to define
the shortest-SBD comparison denominator outside the timed regions.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
import time
from typing import Any

from .analysis import linear_percentile
from .evaluation import (
    EXPECTED_CANDIDATES,
    FULL_FEATURE_NAMES,
    POLICY_FULL_TREE,
    EvaluationError,
    select_with_tree,
)
from .multifamily_evaluation import (
    EXPECTED_CANDIDATE_ROW_COUNT as MULTIFAMILY_CANDIDATE_ROW_COUNT,
    EXPECTED_INSTANCE_COUNT as MULTIFAMILY_INSTANCE_COUNT,
    EXPECTED_MEASUREMENT_COUNT as MULTIFAMILY_MEASUREMENT_COUNT,
    MULTIFAMILY_DATASET_TYPE,
    validate_multifamily_dataset,
)
from .records import make_trial_id


SCHEMA_VERSION = 1
LEGACY_DATASET_TYPE = "autosbd_balanced_candidate_medians"
HOT_WARMUP_ITERATIONS = 1_000
HOT_MEASURED_ITERATIONS = 10_000
COLD_WARMUP_ITERATIONS = 10
COLD_MEASURED_ITERATIONS = 100


class InferenceOverheadError(ValueError):
    """Raised when overhead inputs, measurements, or artifacts are invalid."""


def validate_measurement_protocol(
    *,
    hot_warmup_iterations: int = HOT_WARMUP_ITERATIONS,
    hot_measured_iterations: int = HOT_MEASURED_ITERATIONS,
    cold_warmup_iterations: int = COLD_WARMUP_ITERATIONS,
    cold_measured_iterations: int = COLD_MEASURED_ITERATIONS,
    cold_includes_file_io: bool = True,
) -> dict[str, Any]:
    """Validate and return the fixed Phase-A inference timing protocol."""

    hot_warmup = _nonnegative_int(hot_warmup_iterations, "hot warmup iterations")
    hot_measured = _positive_int(hot_measured_iterations, "hot measured iterations")
    cold_warmup = _nonnegative_int(
        cold_warmup_iterations, "cold warmup iterations"
    )
    cold_measured = _positive_int(
        cold_measured_iterations, "cold measured iterations"
    )
    if hot_warmup == 0 or cold_warmup == 0:
        raise InferenceOverheadError("both timing paths require warmup iterations")
    if hot_measured < HOT_MEASURED_ITERATIONS:
        raise InferenceOverheadError(
            f"hot path requires at least {HOT_MEASURED_ITERATIONS} measured iterations"
        )
    if cold_includes_file_io and cold_measured < COLD_MEASURED_ITERATIONS:
        raise InferenceOverheadError(
            "cold path with file I/O requires at least "
            f"{COLD_MEASURED_ITERATIONS} measured iterations"
        )
    if not isinstance(cold_includes_file_io, bool):
        raise InferenceOverheadError("cold_includes_file_io must be boolean")
    return {
        "clock": "time.perf_counter_ns",
        "percentile_method": (
            "linear interpolation at zero-based position (n - 1) * p"
        ),
        "candidate_schedule": (
            "all problem instances in ascending size/name order, round-robin"
        ),
        "hot_selection": {
            "definition": (
                "pre-execution feature mapping to model vector, memory-feasibility "
                "filter, candidate tree predictions, and deterministic argmin with "
                "an already loaded deployment model"
            ),
            "warmup_iterations": hot_warmup,
            "measured_iterations": hot_measured,
            "includes_model_file_io": False,
            "primary_overhead_measurement": True,
        },
        "cold_load_plus_selection": {
            "definition": (
                "read and strictly deserialize the complete saved models artifact, "
                "retrieve the deployment full tree, then perform the hot selection path"
            ),
            "warmup_iterations": cold_warmup,
            "measured_iterations": cold_measured,
            "includes_model_file_io": cold_includes_file_io,
            "os_page_cache_controlled": False,
            "primary_overhead_measurement": False,
            "interpretation": (
                "model-object-cold diagnostic; not a storage-cache-cold measurement"
            ),
        },
    }


def load_deployment_model(models_path: Path) -> Mapping[str, Any]:
    """Strictly load the registered deployment full-tree model."""

    models, _ = _load_strict_json_file(Path(models_path), "models artifact")
    return _deployment_model(models)


def load_inference_inputs(
    models_path: Path,
    dataset_path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Load, validate, and project the saved model and candidate workloads."""

    root = Path(repository_root).resolve(strict=True)
    models_file = Path(models_path)
    dataset_file = Path(dataset_path)
    models, models_payload = _load_strict_json_file(models_file, "models artifact")
    dataset, dataset_payload = _load_strict_json_file(
        dataset_file, "balanced dataset"
    )
    model = _deployment_model(models)

    if dataset.get("schema_version") != SCHEMA_VERSION:
        raise InferenceOverheadError("unexpected balanced-dataset schema version")
    dataset_type = dataset.get("dataset_type")
    if dataset_type not in {LEGACY_DATASET_TYPE, MULTIFAMILY_DATASET_TYPE}:
        raise InferenceOverheadError("unexpected balanced-dataset type")
    multifamily = dataset_type == MULTIFAMILY_DATASET_TYPE
    if multifamily:
        try:
            validate_multifamily_dataset(dataset)
        except EvaluationError as error:
            raise InferenceOverheadError(
                f"invalid multifamily balanced dataset: {error}"
            ) from error
    rows = dataset.get("rows")
    if not isinstance(rows, list) or not rows:
        raise InferenceOverheadError("balanced dataset lacks candidate rows")

    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for index, raw_row in enumerate(rows):
        if not isinstance(raw_row, Mapping):
            raise InferenceOverheadError(f"dataset row {index} is not an object")
        instance = _required_text(
            raw_row.get("problem_instance"), f"dataset row {index} problem_instance"
        )
        group_id = (
            _required_text(
                raw_row.get("instance_id"), f"dataset row {index} instance_id"
            )
            if multifamily
            else instance
        )
        grouped[group_id].append(raw_row)

    candidate_groups: list[dict[str, Any]] = []
    shortest: dict[str, Any] | None = None
    for group_id, instance_rows in grouped.items():
        problem_instances = {
            _required_text(row.get("problem_instance"), "problem_instance")
            for row in instance_rows
        }
        if len(problem_instances) != 1:
            raise InferenceOverheadError(
                f"candidate problem-instance mismatch for {group_id}"
            )
        instance = next(iter(problem_instances))
        family_id: str | None = None
        if multifamily:
            family_ids = {
                _required_text(row.get("family_id"), "family_id")
                for row in instance_rows
            }
            if len(family_ids) != 1:
                raise InferenceOverheadError(
                    f"candidate family mismatch for {group_id}"
                )
            family_id = next(iter(family_ids))
        names = {
            _required_text(row.get("candidate_name"), "candidate name")
            for row in instance_rows
        }
        if names != set(EXPECTED_CANDIDATES):
            raise InferenceOverheadError(
                f"{instance} must contain exactly the registered CPU and GPU candidates"
            )
        sizes = {
            _positive_int(row.get("n_configurations"), "n_configurations")
            for row in instance_rows
        }
        if len(sizes) != 1:
            raise InferenceOverheadError(f"candidate size mismatch for {instance}")
        caps = [row.get("memory_caps") for row in instance_rows]
        if not all(isinstance(value, Mapping) for value in caps):
            raise InferenceOverheadError(f"candidate memory caps missing for {instance}")
        if any(dict(value) != dict(caps[0]) for value in caps[1:]):
            raise InferenceOverheadError(f"candidate memory caps differ for {instance}")

        projected: list[dict[str, Any]] = []
        for row in sorted(instance_rows, key=lambda value: str(value["candidate_name"])):
            candidate_name = str(row["candidate_name"])
            expected_backend, _ = EXPECTED_CANDIDATES[candidate_name]
            if row.get("backend") != expected_backend:
                raise InferenceOverheadError(
                    f"candidate backend mismatch for {instance}/{candidate_name}"
                )
            feature_values = row.get("feature_values")
            memory_guard = row.get("memory_guard")
            memory_caps = row.get("memory_caps")
            if not all(
                isinstance(value, Mapping)
                for value in (feature_values, memory_guard, memory_caps)
            ):
                raise InferenceOverheadError(
                    f"pre-execution selector fields missing for {instance}/{candidate_name}"
                )
            projected_feature_values = dict(feature_values)
            if multifamily:
                if not set(FULL_FEATURE_NAMES).issubset(projected_feature_values):
                    raise InferenceOverheadError(
                        "multifamily selector feature mapping lacks a registered "
                        f"full feature for {group_id}/{candidate_name}"
                    )
                projected_feature_values = {
                    name: projected_feature_values[name] for name in FULL_FEATURE_NAMES
                }
            projected.append(
                {
                    "candidate_name": candidate_name,
                    "backend": expected_backend,
                    "feature_values": projected_feature_values,
                    "memory_guard": dict(memory_guard),
                    "memory_caps": dict(memory_caps),
                }
            )

            median_wall = _positive_float(
                row.get("median_wall_time_s"), "median_wall_time_s"
            )
            source_ids = _string_list(
                row.get("source_record_ids"), "source_record_ids"
            )
            item = {
                "problem_instance": instance,
                "candidate_name": candidate_name,
                "n_configurations": next(iter(sizes)),
                "median_wall_time_s": median_wall,
                "source_record_ids": source_ids,
            }
            if multifamily:
                item.update({"instance_id": group_id, "family_id": family_id})
            if shortest is None or (
                median_wall,
                instance,
                candidate_name,
            ) < (
                shortest["median_wall_time_s"],
                shortest["problem_instance"],
                shortest["candidate_name"],
            ):
                shortest = item

        group = {
            "problem_instance": instance,
            "n_configurations": next(iter(sizes)),
            "candidate_rows": projected,
        }
        if multifamily:
            group.update({"instance_id": group_id, "family_id": family_id})
        candidate_groups.append(group)

    candidate_groups.sort(
        key=lambda value: (
            value["n_configurations"],
            value.get("instance_id", value["problem_instance"]),
        )
    )
    if shortest is None:
        raise InferenceOverheadError("could not identify shortest measured SBD runtime")

    counts = dataset.get("record_counts")
    if not isinstance(counts, Mapping):
        raise InferenceOverheadError("balanced dataset lacks record counts")
    expected_count_values = {
        "candidate_rows": len(rows),
        "problem_instances": len(candidate_groups),
        "candidates_per_instance": len(EXPECTED_CANDIDATES),
    }
    for key, expected in expected_count_values.items():
        if counts.get(key) != expected:
            raise InferenceOverheadError(f"balanced dataset count mismatch: {key}")
    if multifamily:
        expected_geometry = {
            "candidate_rows": MULTIFAMILY_CANDIDATE_ROW_COUNT,
            "problem_instances": MULTIFAMILY_INSTANCE_COUNT,
            "selected_measurements": MULTIFAMILY_MEASUREMENT_COUNT,
        }
        for key, expected in expected_geometry.items():
            if counts.get(key) != expected:
                raise InferenceOverheadError(
                    f"multifamily balanced dataset count mismatch: {key}"
                )

        model_instance_ids = _string_list(
            model.get("training_instance_ids"),
            "deployment model training_instance_ids",
        )
        expected_instance_ids = sorted(
            str(group["instance_id"]) for group in candidate_groups
        )
        if model_instance_ids != expected_instance_ids:
            raise InferenceOverheadError(
                "deployment model training instances differ from multifamily dataset"
            )
        model_source_ids = _string_list(
            model.get("training_source_record_ids"),
            "deployment model training_source_record_ids",
        )
        expected_source_ids = sorted(
            _string_list(
                dataset.get("source_record_ids"), "dataset source_record_ids"
            )
        )
        if model_source_ids != expected_source_ids:
            raise InferenceOverheadError(
                "deployment model source records differ from multifamily dataset"
            )
        expected_scope = {
            "fit_scope": "all_balanced_instances_after_heldout_evaluation",
            "purpose": "deployment_selection_and_inference_overhead_only",
            "used_for_heldout_metrics": False,
            "training_instance_count": MULTIFAMILY_INSTANCE_COUNT,
            "training_source_record_count": MULTIFAMILY_MEASUREMENT_COUNT,
        }
        if models.get("deployment_model_scope") != expected_scope:
            raise InferenceOverheadError(
                "multifamily deployment model scope differs from registered contract"
            )

    # Validate the exported model against every deployment candidate group before
    # any timing begins. This is outside both measured regions.
    for group in candidate_groups:
        _select_candidate(model, group["candidate_rows"])

    config = models.get("config")
    if not isinstance(config, Mapping):
        raise InferenceOverheadError("models artifact lacks config provenance")
    _required_text(config.get("name"), "models config name")
    _required_digest(config.get("sha256"), "models config SHA-256")

    source_claims = {
        "models": _file_claim(models_file, models_payload, root),
        "balanced_dataset": _file_claim(dataset_file, dataset_payload, root),
    }
    workload_instances = []
    for group in candidate_groups:
        item = {
            "problem_instance": group["problem_instance"],
            "n_configurations": group["n_configurations"],
        }
        if multifamily:
            item.update(
                {
                    "instance_id": group["instance_id"],
                    "family_id": group["family_id"],
                }
            )
        workload_instances.append(item)
    workload = {
        "problem_instance_count": len(candidate_groups),
        "candidates_per_selection": len(EXPECTED_CANDIDATES),
        "problem_instances": workload_instances,
        "shortest_measured_sbd_candidate_median": shortest,
        "comparison_denominator": (
            "minimum candidate median end-to-end wall time in the balanced dataset"
        ),
    }
    return {
        "model": model,
        "candidate_groups": candidate_groups,
        "sources": source_claims,
        "config": dict(config),
        "workload": workload,
    }


def measure_latency_path(
    operation: Callable[[int], str],
    *,
    warmup_iterations: int,
    measured_iterations: int,
    allowed_candidates: Sequence[str] = tuple(EXPECTED_CANDIDATES),
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> dict[str, Any]:
    """Warm up and time an operation while consuming every selected candidate."""

    warmups = _nonnegative_int(warmup_iterations, "warmup_iterations")
    iterations = _positive_int(measured_iterations, "measured_iterations")
    allowed = set(allowed_candidates)
    if not allowed or not all(isinstance(value, str) and value for value in allowed):
        raise InferenceOverheadError("allowed_candidates must contain nonempty names")

    for index in range(warmups):
        _validate_selected_candidate(operation(index), allowed)

    samples_ns: list[int] = []
    selected_counts: Counter[str] = Counter()
    selection_digest = hashlib.sha256()
    for index in range(iterations):
        started = _clock_value(clock_ns(), "start clock")
        selected = operation(index)
        finished = _clock_value(clock_ns(), "finish clock")
        if finished < started:
            raise InferenceOverheadError("perf counter moved backwards")
        selected = _validate_selected_candidate(selected, allowed)
        samples_ns.append(finished - started)
        selected_counts[selected] += 1
        selection_digest.update(f"{index}\0{selected}\n".encode("utf-8"))

    if sum(selected_counts.values()) != iterations:
        raise InferenceOverheadError("selected-candidate consumption count mismatch")
    return {
        "samples_ns": samples_ns,
        "selected_candidate_counts": dict(sorted(selected_counts.items())),
        "selection_checksum_sha256": selection_digest.hexdigest(),
    }


def summarize_latency_samples(samples_ns: Sequence[int]) -> dict[str, Any]:
    """Return the required finite latency statistics in microseconds."""

    samples = list(samples_ns)
    if not samples:
        raise InferenceOverheadError("latency summary requires samples")
    microseconds: list[float] = []
    for value in samples:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise InferenceOverheadError(
                "latency samples must be nonnegative integer nanoseconds"
            )
        microseconds.append(value / 1_000.0)
    return {
        "unit": "microseconds",
        "iteration_count": len(microseconds),
        "minimum_us": min(microseconds),
        "median_us": linear_percentile(microseconds, 0.5),
        "p90_us": linear_percentile(microseconds, 0.9),
        "p95_us": linear_percentile(microseconds, 0.95),
        "maximum_us": max(microseconds),
    }


def run_inference_overhead(
    *,
    models_path: Path,
    dataset_path: Path,
    raw_directory: Path,
    output_directory: Path,
    repository_root: Path,
    hot_warmup_iterations: int = HOT_WARMUP_ITERATIONS,
    hot_measured_iterations: int = HOT_MEASURED_ITERATIONS,
    cold_warmup_iterations: int = COLD_WARMUP_ITERATIONS,
    cold_measured_iterations: int = COLD_MEASURED_ITERATIONS,
) -> dict[str, Any]:
    """Execute the fixed protocol and write immutable raw plus processed outputs."""

    protocol = validate_measurement_protocol(
        hot_warmup_iterations=hot_warmup_iterations,
        hot_measured_iterations=hot_measured_iterations,
        cold_warmup_iterations=cold_warmup_iterations,
        cold_measured_iterations=cold_measured_iterations,
        cold_includes_file_io=True,
    )
    root = Path(repository_root).resolve(strict=True)
    inputs = load_inference_inputs(
        models_path, dataset_path, repository_root=root
    )
    groups = inputs["candidate_groups"]
    loaded_model = inputs["model"]

    def hot_operation(index: int) -> str:
        group = groups[index % len(groups)]
        return _select_candidate(loaded_model, group["candidate_rows"])

    def cold_operation(index: int) -> str:
        group = groups[index % len(groups)]
        model = load_deployment_model(models_path)
        return _select_candidate(model, group["candidate_rows"])

    hot = measure_latency_path(
        hot_operation,
        warmup_iterations=hot_warmup_iterations,
        measured_iterations=hot_measured_iterations,
    )
    cold = measure_latency_path(
        cold_operation,
        warmup_iterations=cold_warmup_iterations,
        measured_iterations=cold_measured_iterations,
    )

    # Fail closed if either source changed during measurement.
    for label, source_path in (
        ("models", Path(models_path)),
        ("balanced_dataset", Path(dataset_path)),
    ):
        if _sha256_path(source_path) != inputs["sources"][label]["sha256"]:
            raise InferenceOverheadError(f"{label} source changed during measurement")

    timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    run_id = make_trial_id(
        {
            "artifact_type": "autosbd_inference_overhead_raw",
            "timestamp_utc": timestamp,
            "nonce": secrets.token_hex(32),
            "source_sha256": {
                key: value["sha256"] for key, value in inputs["sources"].items()
            },
            "protocol": protocol,
        }
    )
    raw_record = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "autosbd_inference_overhead_raw",
        "status": "complete",
        "run_id": run_id,
        "timestamp_utc": timestamp,
        "config": inputs["config"],
        "sources": inputs["sources"],
        "protocol": protocol,
        "workload": inputs["workload"],
        "measurements": {
            "hot_selection": hot,
            "cold_load_plus_selection": cold,
        },
    }
    raw_path = write_immutable_raw_record(raw_record, raw_directory)
    raw_claim = _file_claim(raw_path, raw_path.read_bytes(), root)
    processed = write_processed_artifacts(
        raw_record,
        raw_claim=raw_claim,
        output_directory=output_directory,
    )
    return {
        "status": "complete",
        "run_id": run_id,
        "raw_record": raw_claim,
        "processed_files": processed["files"],
        "hot_iterations": hot_measured_iterations,
        "cold_iterations": cold_measured_iterations,
    }


def write_immutable_raw_record(
    record: Mapping[str, Any], raw_directory: Path
) -> Path:
    """Atomically create a uniquely named raw measurement without replacement."""

    _validate_raw_record(record)
    run_id = str(record["run_id"])
    payload = _strict_json_bytes(record)
    directory = Path(raw_directory)
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise InferenceOverheadError("raw output directory must be a real directory")
    path = directory / f"{run_id}.json"
    if path.exists() or path.is_symlink():
        raise InferenceOverheadError(f"refusing to overwrite raw measurement: {path}")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=directory
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, 0o644)
        try:
            os.link(temporary_path, path)
        except FileExistsError as error:
            raise InferenceOverheadError(
                f"refusing to overwrite raw measurement: {path}"
            ) from error
        _fsync_directory(directory)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def write_processed_artifacts(
    raw_record: Mapping[str, Any],
    *,
    raw_claim: Mapping[str, Any],
    output_directory: Path,
) -> dict[str, Any]:
    """Write the requested processed inference-overhead JSON and CSV."""

    _validate_raw_record(raw_record)
    for key in ("path", "sha256", "size_bytes"):
        if key not in raw_claim:
            raise InferenceOverheadError(f"raw record claim lacks {key}")
    _required_digest(raw_claim.get("sha256"), "raw record SHA-256")
    if _positive_int(raw_claim.get("size_bytes"), "raw record size") <= 0:
        raise AssertionError("unreachable")

    protocol = _mapping(raw_record.get("protocol"), "protocol")
    measurements = _mapping(raw_record.get("measurements"), "measurements")
    processed_measurements: dict[str, dict[str, Any]] = {}
    for name in ("hot_selection", "cold_load_plus_selection"):
        raw_measurement = _mapping(measurements.get(name), name)
        protocol_path = _mapping(protocol.get(name), f"protocol {name}")
        samples = raw_measurement.get("samples_ns")
        if not isinstance(samples, list):
            raise InferenceOverheadError(f"{name} lacks samples_ns")
        summary = summarize_latency_samples(samples)
        if summary["iteration_count"] != protocol_path.get("measured_iterations"):
            raise InferenceOverheadError(f"{name} sample count disagrees with protocol")
        counts = _mapping(
            raw_measurement.get("selected_candidate_counts"),
            f"{name} selected_candidate_counts",
        )
        if any(
            candidate not in EXPECTED_CANDIDATES
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            for candidate, count in counts.items()
        ):
            raise InferenceOverheadError(f"{name} has invalid selection counts")
        if sum(counts.values()) != summary["iteration_count"]:
            raise InferenceOverheadError(f"{name} selection counts do not sum")
        checksum = _required_digest(
            raw_measurement.get("selection_checksum_sha256"),
            f"{name} selection checksum",
        )
        processed_measurements[name] = {
            "definition": protocol_path.get("definition"),
            "primary_overhead_measurement": protocol_path.get(
                "primary_overhead_measurement"
            ),
            "includes_model_file_io": protocol_path.get("includes_model_file_io"),
            "os_page_cache_controlled": protocol_path.get(
                "os_page_cache_controlled"
            ),
            "warmup_iterations": protocol_path.get("warmup_iterations"),
            **summary,
            "selected_candidate_counts": dict(sorted(counts.items())),
            "selection_checksum_sha256": checksum,
        }

    workload = _mapping(raw_record.get("workload"), "workload")
    shortest = _mapping(
        workload.get("shortest_measured_sbd_candidate_median"),
        "shortest measured SBD candidate median",
    )
    shortest_s = _positive_float(
        shortest.get("median_wall_time_s"), "shortest SBD median wall time"
    )
    hot_median_us = processed_measurements["hot_selection"]["median_us"]
    hot_percentage = hot_median_us / (shortest_s * 1_000_000.0) * 100.0
    if not math.isfinite(hot_percentage) or hot_percentage < 0.0:
        raise InferenceOverheadError("invalid hot-overhead percentage")

    summary_artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "autosbd_inference_overhead_summary",
        "status": "complete",
        "run_id": raw_record["run_id"],
        "timestamp_utc": raw_record.get("timestamp_utc"),
        "source_raw_record": dict(raw_claim),
        "config": raw_record.get("config"),
        "sources": raw_record.get("sources"),
        "protocol": protocol,
        "workload": workload,
        "measurements": processed_measurements,
        "comparison": {
            "shortest_measured_sbd_median_wall_time_s": shortest_s,
            "shortest_problem_instance": shortest.get("problem_instance"),
            "shortest_candidate_name": shortest.get("candidate_name"),
            "formula": (
                "hot median microseconds / (shortest measured SBD median seconds "
                "* 1e6) * 100"
            ),
            "hot_median_percent_of_shortest_sbd_runtime": hot_percentage,
        },
    }
    json_payload = _strict_json_bytes(summary_artifact)
    csv_payload = _summary_csv_bytes(summary_artifact)
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    payloads = {
        "inference_overhead.json": json_payload,
        "inference_overhead.csv": csv_payload,
    }
    changed: dict[str, bool] = {}
    files: dict[str, dict[str, Any]] = {}
    for name, payload in payloads.items():
        path = output / name
        changed[name] = _atomic_write_changed(path, payload)
        files[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }
    return {"status": "complete", "changed": changed, "files": files}


def _deployment_model(models: Mapping[str, Any]) -> Mapping[str, Any]:
    if models.get("schema_version") != SCHEMA_VERSION:
        raise InferenceOverheadError("unexpected models-artifact schema version")
    deployment = models.get("deployment_models")
    if not isinstance(deployment, Mapping):
        raise InferenceOverheadError("models artifact lacks deployment_models")
    model = deployment.get(POLICY_FULL_TREE)
    if not isinstance(model, Mapping):
        raise InferenceOverheadError("models artifact lacks deployment full tree")
    if model.get("model_type") != "sklearn.tree.DecisionTreeRegressor":
        raise InferenceOverheadError("unexpected deployment model type")
    if model.get("feature_set") != "full":
        raise InferenceOverheadError("deployment model is not the full feature model")
    if model.get("feature_names") != list(FULL_FEATURE_NAMES):
        raise InferenceOverheadError("deployment model feature order mismatch")
    tree = model.get("tree")
    if not isinstance(tree, Mapping) or not isinstance(tree.get("nodes"), list):
        raise InferenceOverheadError("deployment model lacks exported tree nodes")
    return model


def _select_candidate(
    model: Mapping[str, Any], candidate_rows: Sequence[Mapping[str, Any]]
) -> str:
    try:
        result = select_with_tree(model, candidate_rows)
    except EvaluationError as error:
        raise InferenceOverheadError(f"deployment selection failed: {error}") from error
    selected = result.get("selected_candidate_name")
    return _validate_selected_candidate(selected, set(EXPECTED_CANDIDATES))


def _validate_selected_candidate(value: Any, allowed: set[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise InferenceOverheadError(f"selector returned invalid candidate: {value!r}")
    return value


def _summary_csv_bytes(summary: Mapping[str, Any]) -> bytes:
    fields = (
        "measurement",
        "primary_overhead_measurement",
        "includes_model_file_io",
        "os_page_cache_controlled",
        "warmup_iterations",
        "iteration_count",
        "minimum_us",
        "median_us",
        "p90_us",
        "p95_us",
        "maximum_us",
        "selected_candidate_counts",
        "selection_checksum_sha256",
        "hot_median_percent_of_shortest_sbd_runtime",
        "raw_record_path",
        "raw_record_sha256",
    )
    comparison = _mapping(summary.get("comparison"), "comparison")
    raw_claim = _mapping(summary.get("source_raw_record"), "source_raw_record")
    measurements = _mapping(summary.get("measurements"), "measurements")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for name in ("hot_selection", "cold_load_plus_selection"):
        value = _mapping(measurements.get(name), name)
        writer.writerow(
            {
                "measurement": name,
                **{
                    field: value.get(field)
                    for field in fields
                    if field
                    not in {
                        "measurement",
                        "selected_candidate_counts",
                        "hot_median_percent_of_shortest_sbd_runtime",
                        "raw_record_path",
                        "raw_record_sha256",
                    }
                },
                "selected_candidate_counts": json.dumps(
                    value.get("selected_candidate_counts"),
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "hot_median_percent_of_shortest_sbd_runtime": (
                    comparison.get("hot_median_percent_of_shortest_sbd_runtime")
                    if name == "hot_selection"
                    else ""
                ),
                "raw_record_path": raw_claim.get("path"),
                "raw_record_sha256": raw_claim.get("sha256"),
            }
        )
    return stream.getvalue().encode("utf-8")


def _validate_raw_record(record: Mapping[str, Any]) -> None:
    if not isinstance(record, Mapping):
        raise InferenceOverheadError("raw measurement must be an object")
    if record.get("schema_version") != SCHEMA_VERSION:
        raise InferenceOverheadError("unexpected raw measurement schema version")
    if record.get("artifact_type") != "autosbd_inference_overhead_raw":
        raise InferenceOverheadError("unexpected raw measurement artifact type")
    if record.get("status") != "complete":
        raise InferenceOverheadError("raw measurement is not complete")
    _required_digest(record.get("run_id"), "raw measurement run_id")
    _required_text(record.get("timestamp_utc"), "raw measurement timestamp")
    for key in ("sources", "protocol", "workload", "measurements"):
        _mapping(record.get(key), key)
    _strict_json_bytes(record)


def _load_strict_json_file(
    path: Path, label: str
) -> tuple[dict[str, Any], bytes]:
    path = Path(path)
    if path.is_symlink():
        raise InferenceOverheadError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise InferenceOverheadError(f"cannot resolve {label}: {error}") from error
    if not resolved.is_file():
        raise InferenceOverheadError(f"{label} is not a regular file")
    try:
        payload = resolved.read_bytes()
    except OSError as error:
        raise InferenceOverheadError(f"cannot read {label}: {error}") from error

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite constant {value}")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload,
            parse_constant=reject_constant,
            object_pairs_hook=unique,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise InferenceOverheadError(f"cannot parse {label}: {error}") from error
    if not isinstance(value, dict):
        raise InferenceOverheadError(f"{label} must be a JSON object")
    return value, payload


def _file_claim(path: Path, payload: bytes, root: Path) -> dict[str, Any]:
    resolved = Path(path).resolve(strict=True)
    try:
        display = resolved.relative_to(root).as_posix()
    except ValueError:
        display = str(resolved)
    return {
        "path": display,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as error:
        raise InferenceOverheadError(f"cannot hash source {path}: {error}") from error
    return digest.hexdigest()


def _strict_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise InferenceOverheadError(f"artifact is not strict JSON: {error}") from error


def _atomic_write_changed(path: Path, payload: bytes) -> bool:
    if path.is_symlink():
        raise InferenceOverheadError(f"processed output must not be a symlink: {path}")
    if path.exists():
        if not path.is_file() or path.is_symlink():
            raise InferenceOverheadError(f"processed output is not a file: {path}")
        if path.read_bytes() == payload:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)
    return True


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _clock_value(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InferenceOverheadError(f"{label} must be a nonnegative integer")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InferenceOverheadError(f"{label} must be an object")
    return value


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise InferenceOverheadError(f"{label} must be nonempty text")
    return value


def _required_digest(value: Any, label: str) -> str:
    text = _required_text(value, label)
    if len(text) != 64 or text.lower() != text:
        raise InferenceOverheadError(f"{label} must be lowercase SHA-256")
    try:
        int(text, 16)
    except ValueError as error:
        raise InferenceOverheadError(f"{label} must be lowercase SHA-256") from error
    return text


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise InferenceOverheadError(f"{label} must be a nonempty string list")
    if not all(isinstance(item, str) and item for item in value):
        raise InferenceOverheadError(f"{label} must contain nonempty strings")
    if len(value) != len(set(value)):
        raise InferenceOverheadError(f"{label} contains duplicates")
    return list(value)


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InferenceOverheadError(f"{label} must be a nonnegative integer")
    return value


def _positive_int(value: Any, label: str) -> int:
    result = _nonnegative_int(value, label)
    if result == 0:
        raise InferenceOverheadError(f"{label} must be positive")
    return result


def _positive_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InferenceOverheadError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise InferenceOverheadError(f"{label} must be positive and finite")
    return result


__all__ = [
    "COLD_MEASURED_ITERATIONS",
    "COLD_WARMUP_ITERATIONS",
    "HOT_MEASURED_ITERATIONS",
    "HOT_WARMUP_ITERATIONS",
    "InferenceOverheadError",
    "load_deployment_model",
    "load_inference_inputs",
    "measure_latency_path",
    "run_inference_overhead",
    "summarize_latency_samples",
    "validate_measurement_protocol",
    "write_immutable_raw_record",
    "write_processed_artifacts",
]
