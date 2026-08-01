"""Deterministic aggregation of explicitly selected AutoSBD trial records.

Percentiles use linear interpolation on ascending values at zero-based position
``(n - 1) * p``.  Thus a one-value sample has identical minimum, quartiles,
median, and maximum.  The module intentionally discovers no input files; every
record path must be supplied by the caller.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from itertools import combinations
from pathlib import Path
from typing import Any

from .records import RecordError, canonical_json, load_record


ANALYSIS_SCHEMA_VERSION = 1
PERCENTILE_METHOD = (
    "linear interpolation on ascending values at zero-based position "
    "(n - 1) * p"
)
_TIMING_PHASES = frozenset({"warmup", "measured"})
_TIMING_BACKENDS = frozenset({"cpu", "gpu"})
_CSV_FIELDS = (
    "trial_id",
    "logical_trial_id",
    "attempt_index",
    "timestamp_utc",
    "finished_timestamp_utc",
    "included",
    "exclusion_reasons",
    "phase",
    "repetition",
    "problem_instance",
    "input_sha256",
    "candidate_name",
    "backend",
    "cpu_threads",
    "wall_time_s",
    "solver_time_s",
    "initialization_time_s",
    "matvec_time_s",
    "transfer_time_s",
    "n_orbitals",
    "n_alpha_strings",
    "n_beta_strings",
    "n_configurations",
    "estimated_work",
    "peak_host_rss_mb",
    "peak_gpu_memory_mb",
    "input_features_json",
)


class AnalysisError(ValueError):
    """Raised when selected records cannot be analyzed safely."""


def linear_percentile(values: Sequence[float], probability: float) -> float:
    """Return a deterministic linear percentile for finite numeric values."""

    if not values:
        raise AnalysisError("percentile requires at least one value")
    if isinstance(probability, bool) or not isinstance(probability, (int, float)):
        raise AnalysisError("percentile probability must be numeric")
    probability = float(probability)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise AnalysisError("percentile probability must be between zero and one")

    ordered: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AnalysisError("percentile values must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise AnalysisError("percentile values must be finite")
        ordered.append(numeric)
    ordered.sort()

    position = (len(ordered) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return ordered[lower_index] + (
        ordered[upper_index] - ordered[lower_index]
    ) * fraction


def summarize_values(values: Sequence[float]) -> dict[str, float | int]:
    """Summarize a nonempty sequence with the documented percentile method."""

    if not values:
        raise AnalysisError("summary requires at least one value")
    ordered: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AnalysisError("summary values must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise AnalysisError("summary values must be finite")
        ordered.append(numeric)
    ordered.sort()
    q1 = linear_percentile(ordered, 0.25)
    median = linear_percentile(ordered, 0.5)
    q3 = linear_percentile(ordered, 0.75)
    return {
        "count": len(ordered),
        "minimum": ordered[0],
        "q1": q1,
        "median": median,
        "q3": q3,
        "iqr": q3 - q1,
        "maximum": ordered[-1],
    }


def aggregate_records(record_paths: Sequence[str | os.PathLike[str]]) -> dict[str, Any]:
    """Load and aggregate only the explicitly supplied immutable records."""

    if isinstance(record_paths, (str, bytes, os.PathLike)):
        raise AnalysisError("record_paths must be a sequence of explicit file paths")
    paths = tuple(Path(path) for path in record_paths)
    if not paths:
        raise AnalysisError("at least one explicit record path is required")

    resolved_paths: list[Path] = []
    seen_paths: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen_paths:
            raise AnalysisError(f"duplicate record path: {path}")
        seen_paths.add(resolved)
        resolved_paths.append(resolved)

    loaded: list[dict[str, Any]] = []
    seen_trial_ids: set[str] = set()
    for path in sorted(resolved_paths, key=lambda item: item.as_posix()):
        try:
            record = load_record(path)
        except (OSError, UnicodeError, json.JSONDecodeError, RecordError) as error:
            raise AnalysisError(f"cannot load record {path}: {error}") from error
        trial_id = record["trial_id"]
        if trial_id in seen_trial_ids:
            raise AnalysisError(f"duplicate trial_id across record paths: {trial_id}")
        seen_trial_ids.add(trial_id)
        _validate_timing_shape(record)
        loaded.append(record)

    classified: list[tuple[dict[str, Any], dict[str, Any]]] = []
    reason_counts: Counter[str] = Counter()
    for record in loaded:
        reasons = tuple(sorted(_exclusion_reasons(record)))
        reason_counts.update(reasons)
        row = _record_row(record, reasons)
        classified.append((record, row))
    classified.sort(key=lambda item: (item[1]["timestamp_utc"], item[1]["trial_id"]))

    included = [(record, row) for record, row in classified if row["included"]]
    groups = _candidate_groups(included)
    workloads = _workload_comparisons(groups)
    rows = [row for _, row in classified]

    result = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis_type": "autosbd_timing_aggregation",
        "statistics": {
            "percentile_method": PERCENTILE_METHOD,
            "quartile_probabilities": [0.25, 0.75],
        },
        "record_counts": {
            "input": len(rows),
            "included": len(included),
            "excluded": len(rows) - len(included),
        },
        "exclusion_reason_counting": (
            "Each excluded record contributes once to every applicable reason."
        ),
        "exclusion_reason_counts": dict(sorted(reason_counts.items())),
        "input_record_ids": sorted(seen_trial_ids),
        "rows": rows,
        "candidate_groups": groups,
        "workloads": workloads,
    }
    # This also rejects any accidental non-finite derived value.
    canonical_json(result)
    return result


def write_analysis_outputs(
    analysis: Mapping[str, Any],
    output_json: str | os.PathLike[str],
    output_csv: str | os.PathLike[str],
) -> dict[str, Any]:
    """Atomically write deterministic JSON and CSV, replacing only on change."""

    json_path = Path(output_json)
    csv_path = Path(output_csv)
    if json_path.resolve() == csv_path.resolve():
        raise AnalysisError("JSON and CSV output paths must be different")
    _validate_analysis_for_output(analysis)
    json_payload = (
        json.dumps(
            analysis,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    csv_payload = _render_csv(analysis).encode("utf-8")
    json_changed = _atomic_write_changed(json_path, json_payload)
    csv_changed = _atomic_write_changed(csv_path, csv_payload)
    counts = analysis["record_counts"]
    return {
        "json_changed": json_changed,
        "csv_changed": csv_changed,
        "input_records": counts["input"],
        "included_records": counts["included"],
        "excluded_records": counts["excluded"],
    }


def aggregate_and_write(
    record_paths: Sequence[str | os.PathLike[str]],
    output_json: str | os.PathLike[str],
    output_csv: str | os.PathLike[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Aggregate explicit records and write both deterministic outputs."""

    analysis = aggregate_records(record_paths)
    status = write_analysis_outputs(analysis, output_json, output_csv)
    return analysis, status


def _validate_timing_shape(record: Mapping[str, Any]) -> None:
    if record.get("schema_version") != 2:
        raise AnalysisError(
            "timing aggregation requires schema_version 2 records"
        )
    if record.get("warmup_or_measured") not in _TIMING_PHASES:
        return
    trial_id = record.get("trial_id", "<unknown>")

    problem_instance = record.get("problem_instance")
    if not isinstance(problem_instance, str) or not problem_instance:
        raise AnalysisError(f"record {trial_id} has invalid problem_instance")
    input_sha256 = record.get("input_sha256")
    if not _is_sha256(input_sha256):
        raise AnalysisError(f"record {trial_id} has invalid input_sha256")
    for field in ("timestamp_utc", "finished_timestamp_utc"):
        value = record.get(field)
        if not isinstance(value, str) or not value:
            raise AnalysisError(f"record {trial_id} has invalid {field}")

    logical_identity = record.get("logical_identity")
    candidate = (
        logical_identity.get("candidate")
        if isinstance(logical_identity, Mapping)
        else None
    )
    if not isinstance(candidate, Mapping):
        raise AnalysisError(f"record {trial_id} lacks candidate identity")
    name = candidate.get("name")
    if not isinstance(name, str) or not name:
        raise AnalysisError(f"record {trial_id} has invalid candidate name")
    if candidate.get("backend") != record.get("backend"):
        raise AnalysisError(f"record {trial_id} candidate backend mismatch")
    if candidate.get("threads") != record.get("cpu_threads"):
        raise AnalysisError(f"record {trial_id} candidate thread mismatch")

    features = record.get("input_features")
    if not isinstance(features, Mapping):
        raise AnalysisError(f"record {trial_id} lacks input_features")
    if features.get("combined_input_sha256") != input_sha256:
        raise AnalysisError(f"record {trial_id} input feature hash mismatch")
    if features.get("n_configurations") != record.get("n_configurations"):
        raise AnalysisError(f"record {trial_id} configuration feature mismatch")
    if features.get("method0_work_proxy") != record.get("estimated_work"):
        raise AnalysisError(f"record {trial_id} work feature mismatch")

    for field in (
        "input_integrity",
        "validation_evidence",
        "resource_monitoring",
        "protocol",
    ):
        if not isinstance(record.get(field), Mapping):
            raise AnalysisError(f"record {trial_id} has invalid {field}")

    if record.get("status") == "success":
        for field in ("wall_time_s", "solver_time_s"):
            value = record.get(field)
            if not _is_finite_number(value) or float(value) < 0.0:
                raise AnalysisError(f"record {trial_id} has invalid {field}")


def _exclusion_reasons(record: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    schema_version = record.get("schema_version")
    if schema_version != 2:
        reasons.append("schema_version_not_2")

    phase = record.get("warmup_or_measured")
    if phase == "warmup":
        reasons.append("warmup")
    elif phase != "measured":
        reasons.append("phase_not_measured")
    if record.get("timing_eligible") is not True:
        reasons.append("timing_ineligible")
    if record.get("backend") not in _TIMING_BACKENDS:
        reasons.append("backend_not_cpu_or_gpu")
    if record.get("status") != "success":
        reasons.append("status_not_success")
    if record.get("process_success") is not True:
        reasons.append("process_not_successful")
    if record.get("scientific_success") is not True:
        reasons.append("scientific_not_successful")
    if record.get("correct") is not True:
        reasons.append("correct_not_true")
    if record.get("project_git_dirty") is not False:
        reasons.append("project_not_clean")

    protocol = record.get("protocol")
    if not isinstance(protocol, Mapping) or protocol.get("correctness_validated") is not True:
        reasons.append("correctness_not_validated")
    validation = record.get("validation_evidence")
    if (
        not isinstance(validation, Mapping)
        or validation.get("required") is not True
        or validation.get("valid") is not True
    ):
        reasons.append("validation_manifest_invalid")

    integrity = record.get("input_integrity")
    if not isinstance(integrity, Mapping):
        reasons.extend(
            ("input_changed_before_launch", "input_changed_after_run")
        )
    else:
        if integrity.get("unchanged_before_launch") is not True:
            reasons.append("input_changed_before_launch")
        if integrity.get("unchanged_after_run") is not True:
            reasons.append("input_changed_after_run")
        if integrity.get("rehash_error") is not None:
            reasons.append("input_rehash_error")

    monitoring = record.get("resource_monitoring")
    if not isinstance(monitoring, Mapping):
        reasons.append("host_monitor_incomplete")
        if record.get("backend") == "gpu":
            reasons.extend(("gpu_monitor_incomplete", "gpu_process_not_observed"))
    else:
        if monitoring.get("host_complete") is not True:
            reasons.append("host_monitor_incomplete")
        samples = monitoring.get("samples")
        if isinstance(samples, bool) or not isinstance(samples, int) or samples <= 0:
            reasons.append("resource_samples_missing")
        if record.get("backend") == "gpu":
            if monitoring.get("gpu_complete") is not True:
                reasons.append("gpu_monitor_incomplete")
            if monitoring.get("gpu_process_observed") is not True:
                reasons.append("gpu_process_not_observed")

    if not _is_finite_number(record.get("wall_time_s")) or float(
        record.get("wall_time_s") or 0.0
    ) <= 0.0:
        reasons.append("wall_time_invalid")
    if not _is_finite_number(record.get("solver_time_s")) or float(
        record.get("solver_time_s") or 0.0
    ) < 0.0:
        reasons.append("solver_time_invalid")
    if _candidate_name(record) is None:
        reasons.append("candidate_name_missing")
    if not isinstance(record.get("input_features"), Mapping):
        reasons.append("input_features_missing")
    return reasons


def _record_row(
    record: Mapping[str, Any], reasons: Sequence[str]
) -> dict[str, Any]:
    features = record.get("input_features")
    return {
        "trial_id": record["trial_id"],
        "logical_trial_id": record["logical_trial_id"],
        "attempt_index": record["attempt_index"],
        "timestamp_utc": record["timestamp_utc"],
        "finished_timestamp_utc": record["finished_timestamp_utc"],
        "included": not reasons,
        "exclusion_reasons": list(reasons),
        "phase": record["warmup_or_measured"],
        "repetition": record["repetition"],
        "problem_instance": record["problem_instance"],
        "input_sha256": record["input_sha256"],
        "candidate": {
            "name": _candidate_name(record),
            "backend": record["backend"],
            "cpu_threads": record["cpu_threads"],
        },
        "times_s": {
            "wall": record["wall_time_s"],
            "solver": record["solver_time_s"],
            "initialization": record["initialization_time_s"],
            "matvec": record["matvec_time_s"],
            "transfer": record["transfer_time_s"],
        },
        "iterations": record["iterations"],
        "energy_or_eigenvalue": record["energy_or_eigenvalue"],
        "peak_host_rss_mb": record["peak_host_rss_mb"],
        "peak_gpu_memory_mb": record["peak_gpu_memory_mb"],
        "features": features if isinstance(features, Mapping) else None,
    }


def _candidate_groups(
    included: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = (
        defaultdict(list)
    )
    for record, row in included:
        key = (
            record["problem_instance"],
            record["input_sha256"],
            _candidate_name(record),
            record["backend"],
            record["cpu_threads"],
        )
        grouped[key].append((record, row))

    summaries: list[dict[str, Any]] = []
    for key in sorted(grouped):
        problem_instance, input_sha256, name, backend, threads = key
        members = sorted(
            grouped[key], key=lambda item: (item[1]["timestamp_utc"], item[1]["trial_id"])
        )
        wall_values = [float(record["wall_time_s"]) for record, _ in members]
        solver_values = [float(record["solver_time_s"]) for record, _ in members]
        summaries.append(
            {
                "problem_instance": problem_instance,
                "input_sha256": input_sha256,
                "candidate": {
                    "name": name,
                    "backend": backend,
                    "cpu_threads": threads,
                },
                "record_ids": [row["trial_id"] for _, row in members],
                "wall_time_s": summarize_values(wall_values),
                "solver_time_s": summarize_values(solver_values),
            }
        )
    return summaries


def _workload_comparisons(
    groups: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_workload: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for group in groups:
        by_workload[(group["problem_instance"], group["input_sha256"])].append(group)

    workloads: list[dict[str, Any]] = []
    for workload_key in sorted(by_workload):
        problem_instance, input_sha256 = workload_key
        candidates = sorted(
            by_workload[workload_key], key=lambda item: _candidate_sort_key(item["candidate"])
        )
        minimum = min(
            candidate["wall_time_s"]["median"] for candidate in candidates
        )
        oracle_candidates = [
            candidate["candidate"]
            for candidate in candidates
            if candidate["wall_time_s"]["median"] == minimum
        ]
        comparisons: list[dict[str, Any]] = []
        for left, right in combinations(candidates, 2):
            comparisons.append(
                {
                    "left_candidate": left["candidate"],
                    "right_candidate": right["candidate"],
                    "median_wall_ratio_left_over_right": _safe_ratio(
                        left["wall_time_s"]["median"],
                        right["wall_time_s"]["median"],
                    ),
                    "median_solver_ratio_left_over_right": _safe_ratio(
                        left["solver_time_s"]["median"],
                        right["solver_time_s"]["median"],
                    ),
                }
            )
        workloads.append(
            {
                "problem_instance": problem_instance,
                "input_sha256": input_sha256,
                "candidate_groups": [
                    {
                        "candidate": candidate["candidate"],
                        "record_ids": candidate["record_ids"],
                        "wall_time_s": candidate["wall_time_s"],
                        "solver_time_s": candidate["solver_time_s"],
                    }
                    for candidate in candidates
                ],
                "oracle": {
                    "metric": "median_wall_time_s",
                    "minimum": minimum,
                    "candidates": oracle_candidates,
                },
                "candidate_comparisons": comparisons,
            }
        )
    return workloads


def _candidate_name(record: Mapping[str, Any]) -> str | None:
    logical_identity = record.get("logical_identity")
    if not isinstance(logical_identity, Mapping):
        return None
    candidate = logical_identity.get("candidate")
    if not isinstance(candidate, Mapping):
        return None
    name = candidate.get("name")
    return name if isinstance(name, str) and name else None


def _candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[str, str, int]:
    return (
        str(candidate["name"]),
        str(candidate["backend"]),
        int(candidate["cpu_threads"]),
    )


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0.0:
        return None
    return float(numerator) / float(denominator)


def _validate_analysis_for_output(analysis: Mapping[str, Any]) -> None:
    if not isinstance(analysis, Mapping):
        raise AnalysisError("analysis output must be an object")
    if analysis.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
        raise AnalysisError("unsupported analysis schema_version")
    rows = analysis.get("rows")
    counts = analysis.get("record_counts")
    if not isinstance(rows, list) or not isinstance(counts, Mapping):
        raise AnalysisError("analysis output lacks rows or record_counts")
    if counts.get("input") != len(rows):
        raise AnalysisError("analysis row count does not match record_counts")
    try:
        canonical_json(analysis)
    except (RecordError, TypeError, ValueError) as error:
        raise AnalysisError(f"analysis output is not canonical JSON: {error}") from error


def _render_csv(analysis: Mapping[str, Any]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=_CSV_FIELDS,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in analysis["rows"]:
        candidate = row["candidate"]
        times = row["times_s"]
        features = row["features"]
        writer.writerow(
            {
                "trial_id": row["trial_id"],
                "logical_trial_id": row["logical_trial_id"],
                "attempt_index": row["attempt_index"],
                "timestamp_utc": row["timestamp_utc"],
                "finished_timestamp_utc": row["finished_timestamp_utc"],
                "included": "true" if row["included"] else "false",
                "exclusion_reasons": ";".join(row["exclusion_reasons"]),
                "phase": row["phase"],
                "repetition": row["repetition"],
                "problem_instance": row["problem_instance"],
                "input_sha256": row["input_sha256"],
                "candidate_name": candidate["name"] or "",
                "backend": candidate["backend"],
                "cpu_threads": candidate["cpu_threads"],
                "wall_time_s": _csv_value(times["wall"]),
                "solver_time_s": _csv_value(times["solver"]),
                "initialization_time_s": _csv_value(times["initialization"]),
                "matvec_time_s": _csv_value(times["matvec"]),
                "transfer_time_s": _csv_value(times["transfer"]),
                "n_orbitals": _feature_value(features, "fcidump", "n_orbitals"),
                "n_alpha_strings": _feature_value(features, "alpha", "count"),
                "n_beta_strings": _feature_value(features, "beta", "count"),
                "n_configurations": _feature_value(features, "n_configurations"),
                "estimated_work": _feature_value(features, "method0_work_proxy"),
                "peak_host_rss_mb": _csv_value(row["peak_host_rss_mb"]),
                "peak_gpu_memory_mb": _csv_value(row["peak_gpu_memory_mb"]),
                "input_features_json": (
                    canonical_json(features) if isinstance(features, Mapping) else ""
                ),
            }
        )
    return stream.getvalue()


def _feature_value(features: Any, *path: str) -> Any:
    value = features
    for key in path:
        if not isinstance(value, Mapping):
            return ""
        value = value.get(key)
    return _csv_value(value)


def _csv_value(value: Any) -> Any:
    return "" if value is None else value


def _atomic_write_changed(path: Path, payload: bytes) -> bool:
    if path.is_symlink():
        raise AnalysisError(f"refusing symlink output path: {path}")
    if path.exists():
        if not path.is_file():
            raise AnalysisError(f"output path is not a regular file: {path}")
        try:
            if path.read_bytes() == payload:
                return False
        except OSError as error:
            raise AnalysisError(f"cannot read output {path}: {error}") from error
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
    except OSError as error:
        raise AnalysisError(f"cannot prepare output {path}: {error}") from error
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except OSError as error:
        raise AnalysisError(f"cannot write output {path}: {error}") from error
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
