"""Deterministic internal figures and trace tables for AutoSBD evidence."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

from .analysis import summarize_values


MIB = 1 << 20
CPU_CANDIDATE = "amd-cpu-16"
GPU_CANDIDATE = "amd-l4-default"
COLORBLIND_BLUE = "#0072B2"
COLORBLIND_ORANGE = "#D55E00"
COLORBLIND_GREEN = "#009E73"
NEUTRAL_GRAY = "#666666"


class FigureError(ValueError):
    """Raised when figure source evidence is incomplete or inconsistent."""


def sha256_path(path: Path) -> str:
    """Return a lowercase SHA-256 digest for one file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_stage4_figure_data(
    aggregate_path: Path,
    raw_dir: Path,
) -> dict[str, Any]:
    """Build plot-ready Stage 4 data with raw-record traceability.

    Only timing-eligible measured rows from the explicit final aggregate are
    accepted.  Runtime summaries come from the aggregate; memory summaries are
    independently reconstructed from the referenced immutable raw records.
    """

    aggregate_file = Path(aggregate_path)
    raw_directory = Path(raw_dir)
    aggregate = _load_mapping(aggregate_file, "aggregate")
    if aggregate.get("record_counts") != {
        "input": 48,
        "included": 38,
        "excluded": 10,
    }:
        raise FigureError("Stage 4 aggregate must contain 48/38/10 records")
    if len(aggregate.get("workloads", [])) != 5:
        raise FigureError("Stage 4 aggregate must contain five workloads")

    included_rows = [
        row
        for row in aggregate.get("rows", [])
        if row.get("included") is True
    ]
    if len(included_rows) != 38:
        raise FigureError("Stage 4 aggregate must contain 38 included rows")
    row_by_trial_id: dict[str, Mapping[str, Any]] = {}
    rows_by_instance: dict[str, list[Mapping[str, Any]]] = {}
    for row in included_rows:
        trial_id = _require_digest(row.get("trial_id"), "row trial_id")
        if trial_id in row_by_trial_id:
            raise FigureError(f"duplicate included trial ID: {trial_id}")
        if row.get("phase") != "measured":
            raise FigureError(f"included non-measured row: {trial_id}")
        row_by_trial_id[trial_id] = row
        instance = _require_text(row.get("problem_instance"), "problem_instance")
        rows_by_instance.setdefault(instance, []).append(row)

    crossover_rows: list[dict[str, Any]] = []
    instance_summaries: list[dict[str, Any]] = []
    for workload in aggregate["workloads"]:
        instance = _require_text(workload.get("problem_instance"), "workload instance")
        representative_rows = rows_by_instance.get(instance, [])
        if not representative_rows:
            raise FigureError(f"no included rows for {instance}")
        features = representative_rows[0].get("features")
        if not isinstance(features, Mapping):
            raise FigureError(f"missing features for {instance}")
        n_configurations = _require_positive_int(
            features.get("n_configurations"), "n_configurations"
        )
        n_alpha = _require_positive_int(
            _nested(features, "alpha", "count"), "n_alpha"
        )
        n_beta = _require_positive_int(
            _nested(features, "beta", "count"), "n_beta"
        )
        groups = workload.get("candidate_groups")
        if not isinstance(groups, list) or len(groups) != 2:
            raise FigureError(f"expected two candidate groups for {instance}")
        group_by_name = {
            _require_text(_nested(group, "candidate", "name"), "candidate name"): group
            for group in groups
        }
        if set(group_by_name) != {CPU_CANDIDATE, GPU_CANDIDATE}:
            raise FigureError(f"unexpected candidates for {instance}")
        oracle_names = sorted(
            _require_text(candidate.get("name"), "oracle candidate")
            for candidate in _nested(workload, "oracle", "candidates")
        )
        if len(oracle_names) != 1:
            raise FigureError(f"expected one oracle candidate for {instance}")
        comparison = workload.get("candidate_comparisons")
        if not isinstance(comparison, list) or len(comparison) != 1:
            raise FigureError(f"expected one candidate comparison for {instance}")
        cpu_over_gpu = _require_positive_number(
            comparison[0].get("median_wall_ratio_left_over_right"),
            "CPU/GPU wall ratio",
        )
        for candidate_name in (CPU_CANDIDATE, GPU_CANDIDATE):
            group = group_by_name[candidate_name]
            wall = _require_summary(group.get("wall_time_s"), instance, candidate_name)
            solver = _require_summary(
                group.get("solver_time_s"), instance, candidate_name
            )
            record_ids = [
                _require_digest(value, "candidate-group record ID")
                for value in group.get("record_ids", [])
            ]
            if len(record_ids) != wall["count"]:
                raise FigureError(f"record count mismatch for {instance}/{candidate_name}")
            crossover_rows.append(
                {
                    "problem_instance": instance,
                    "input_sha256": _require_digest(
                        workload.get("input_sha256"), "workload input_sha256"
                    ),
                    "n_configurations": n_configurations,
                    "n_alpha_strings": n_alpha,
                    "n_beta_strings": n_beta,
                    "candidate": candidate_name,
                    "backend": _require_text(
                        _nested(group, "candidate", "backend"), "candidate backend"
                    ),
                    "count": wall["count"],
                    "wall_minimum_s": wall["minimum"],
                    "wall_q1_s": wall["q1"],
                    "wall_median_s": wall["median"],
                    "wall_q3_s": wall["q3"],
                    "wall_iqr_s": wall["iqr"],
                    "wall_maximum_s": wall["maximum"],
                    "solver_median_s": solver["median"],
                    "oracle_candidate": oracle_names[0],
                    "median_cpu_over_gpu": cpu_over_gpu,
                    "record_ids": record_ids,
                }
            )
        instance_summaries.append(
            {
                "problem_instance": instance,
                "n_configurations": n_configurations,
                "oracle_candidate": oracle_names[0],
                "median_cpu_over_gpu": cpu_over_gpu,
            }
        )

    instance_summaries.sort(key=lambda item: item["n_configurations"])
    flips = [
        (left, right)
        for left, right in zip(instance_summaries, instance_summaries[1:])
        if left["oracle_candidate"] != right["oracle_candidate"]
    ]
    if len(flips) != 1:
        raise FigureError(f"expected one sampled winner flip, found {len(flips)}")
    bracket_left, bracket_right = flips[0]

    memory_records: list[dict[str, Any]] = []
    for trial_id, row in sorted(row_by_trial_id.items()):
        if _nested(row, "candidate", "name") != GPU_CANDIDATE:
            continue
        raw_path = raw_directory / f"{trial_id}.json"
        raw = _load_mapping(raw_path, f"raw record {trial_id}")
        if raw.get("trial_id") != trial_id:
            raise FigureError(f"raw filename/trial ID mismatch: {raw_path}")
        if not (
            raw.get("status") == "success"
            and raw.get("correct") is True
            and raw.get("timing_eligible") is True
            and raw.get("warmup_or_measured") == "measured"
            and raw.get("backend") == "gpu"
            and raw.get("timeout") is False
            and raw.get("oom") is False
            and raw.get("skip_reason") is None
        ):
            raise FigureError(f"ineligible GPU memory record: {trial_id}")
        estimate = raw.get("source_memory_estimate")
        preflight = raw.get("preflight")
        if not isinstance(estimate, Mapping) or not isinstance(preflight, Mapping):
            raise FigureError(f"missing memory/preflight evidence: {trial_id}")
        peak_mib = _require_positive_number(
            raw.get("peak_gpu_memory_mb"), "peak_gpu_memory_mb"
        )
        guard_bytes = _require_positive_int(
            estimate.get("gpu_guard_bytes"), "gpu_guard_bytes"
        )
        known_bytes = _require_positive_int(
            estimate.get("gpu_known_bytes"), "gpu_known_bytes"
        )
        cap_bytes = _require_positive_int(
            preflight.get("gpu_memory_cap_bytes"), "gpu_memory_cap_bytes"
        )
        if guard_bytes > cap_bytes:
            raise FigureError(f"GPU guard exceeds cap for admitted record: {trial_id}")
        features = row["features"]
        memory_records.append(
            {
                "problem_instance": row["problem_instance"],
                "input_sha256": row["input_sha256"],
                "n_configurations": _require_positive_int(
                    features.get("n_configurations"), "n_configurations"
                ),
                "repetition": _require_nonnegative_int(
                    row.get("repetition"), "repetition"
                ),
                "trial_id": trial_id,
                "raw_sha256": sha256_path(raw_path),
                "peak_gpu_memory_mib": peak_mib,
                "estimated_gpu_known_mib": known_bytes / MIB,
                "estimated_gpu_guard_mib": guard_bytes / MIB,
                "gpu_admission_cap_mib": cap_bytes / MIB,
                "status": "success",
                "correct": True,
                "timeout": False,
                "oom": False,
                "skip_reason": None,
            }
        )
    if len(memory_records) != 19:
        raise FigureError(f"expected 19 measured GPU records, found {len(memory_records)}")

    memory_summaries: list[dict[str, Any]] = []
    for instance in sorted(
        {row["problem_instance"] for row in memory_records},
        key=lambda name: next(
            row["n_configurations"]
            for row in memory_records
            if row["problem_instance"] == name
        ),
    ):
        records = [row for row in memory_records if row["problem_instance"] == instance]
        peaks = summarize_values([row["peak_gpu_memory_mib"] for row in records])
        guard_values = {row["estimated_gpu_guard_mib"] for row in records}
        known_values = {row["estimated_gpu_known_mib"] for row in records}
        if len(guard_values) != 1 or len(known_values) != 1:
            raise FigureError(f"inconsistent source memory estimate for {instance}")
        memory_summaries.append(
            {
                "problem_instance": instance,
                "n_configurations": records[0]["n_configurations"],
                "count": peaks["count"],
                "peak_gpu_memory_mib": peaks,
                "estimated_gpu_known_mib": next(iter(known_values)),
                "estimated_gpu_guard_mib": next(iter(guard_values)),
                "minimum_gpu_admission_cap_mib": min(
                    row["gpu_admission_cap_mib"] for row in records
                ),
                "record_ids": sorted(row["trial_id"] for row in records),
            }
        )

    return {
        "schema_version": 1,
        "source": {
            "aggregate_path": str(aggregate_file),
            "aggregate_sha256": sha256_path(aggregate_file),
            "raw_directory": str(raw_directory),
            "primary_metric": "end_to_end_wall_time_s",
        },
        "crossover": {
            "rows": sorted(
                crossover_rows,
                key=lambda item: (item["n_configurations"], item["candidate"]),
            ),
            "observed_winner_flip_bracket": {
                "lower_n_configurations": bracket_left["n_configurations"],
                "upper_n_configurations": bracket_right["n_configurations"],
                "lower_winner": bracket_left["oracle_candidate"],
                "upper_winner": bracket_right["oracle_candidate"],
                "interpretation": "observed bracket only; no fitted crossover",
            },
            "smoothing": "none",
        },
        "gpu_memory": {
            "records": memory_records,
            "summaries": memory_summaries,
            "boundary_reached": False,
            "estimate_definition": (
                "Pinned AMD method-0 source-array device estimate and padded "
                "gpu_guard_bytes from each immutable raw record"
            ),
            "admission_policy": "min(20 GiB, 80% of preflight free VRAM)",
            "smoothing": "none",
        },
    }


def generate_stage4_figures(
    aggregate_path: Path,
    raw_dir: Path,
    output_dir: Path,
    table_dir: Path,
) -> dict[str, Any]:
    """Generate two deterministic SVGs and their companion tables."""

    data = build_stage4_figure_data(aggregate_path, raw_dir)
    output_directory = Path(output_dir)
    table_directory = Path(table_dir)
    output_directory.mkdir(parents=True, exist_ok=True)
    table_directory.mkdir(parents=True, exist_ok=True)

    statuses: dict[str, bool] = {}
    trace_json = table_directory / "stage4_figure_trace.json"
    statuses[str(trace_json)] = _write_text_if_changed(
        trace_json, json.dumps(data, indent=2, sort_keys=True) + "\n"
    )
    crossover_csv = table_directory / "cpu_gpu_crossover.csv"
    statuses[str(crossover_csv)] = _write_csv_if_changed(
        crossover_csv,
        data["crossover"]["rows"],
        (
            "problem_instance",
            "input_sha256",
            "n_configurations",
            "n_alpha_strings",
            "n_beta_strings",
            "candidate",
            "backend",
            "count",
            "wall_minimum_s",
            "wall_q1_s",
            "wall_median_s",
            "wall_q3_s",
            "wall_iqr_s",
            "wall_maximum_s",
            "solver_median_s",
            "oracle_candidate",
            "median_cpu_over_gpu",
            "record_ids",
        ),
    )
    memory_csv = table_directory / "gpu_memory_guard.csv"
    statuses[str(memory_csv)] = _write_csv_if_changed(
        memory_csv,
        data["gpu_memory"]["records"],
        (
            "problem_instance",
            "input_sha256",
            "n_configurations",
            "repetition",
            "trial_id",
            "raw_sha256",
            "peak_gpu_memory_mib",
            "estimated_gpu_known_mib",
            "estimated_gpu_guard_mib",
            "gpu_admission_cap_mib",
            "status",
            "correct",
            "timeout",
            "oom",
            "skip_reason",
        ),
    )

    crossover_svg = output_directory / "cpu_gpu_crossover.svg"
    memory_svg = output_directory / "gpu_memory_guard.svg"
    statuses[str(crossover_svg)] = _render_crossover_svg(
        data["crossover"], crossover_svg
    )
    statuses[str(memory_svg)] = _render_memory_svg(
        data["gpu_memory"], memory_svg
    )
    return {
        "status": "ok",
        "changed": statuses,
        "source_aggregate_sha256": data["source"]["aggregate_sha256"],
        "crossover_rows": len(data["crossover"]["rows"]),
        "gpu_memory_records": len(data["gpu_memory"]["records"]),
    }


def _render_crossover_svg(data: Mapping[str, Any], output_path: Path) -> bool:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    rows = data["rows"]
    with mpl.rc_context(
        {
            "svg.hashsalt": "autosbd-stage4-figures-v1",
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.grid": True,
            "grid.alpha": 0.25,
        }
    ):
        figure, axis = plt.subplots(figsize=(7.2, 4.6), constrained_layout=True)
        for candidate, label, color, marker in (
            (CPU_CANDIDATE, "CPU (16 threads)", COLORBLIND_BLUE, "o"),
            (GPU_CANDIDATE, "GPU (L4 default)", COLORBLIND_ORANGE, "s"),
        ):
            candidate_rows = [row for row in rows if row["candidate"] == candidate]
            x = [row["n_configurations"] for row in candidate_rows]
            y = [row["wall_median_s"] for row in candidate_rows]
            yerr = [
                [row["wall_median_s"] - row["wall_q1_s"] for row in candidate_rows],
                [row["wall_q3_s"] - row["wall_median_s"] for row in candidate_rows],
            ]
            axis.errorbar(
                x,
                y,
                yerr=yerr,
                label=label,
                color=color,
                marker=marker,
                markersize=6,
                linewidth=1.8,
                capsize=3,
            )
        bracket = data["observed_winner_flip_bracket"]
        lower = bracket["lower_n_configurations"]
        upper = bracket["upper_n_configurations"]
        axis.axvspan(lower, upper, color=NEUTRAL_GRAY, alpha=0.10)
        axis.text(
            math.sqrt(lower * upper),
            0.97,
            "observed winner-flip bracket",
            transform=axis.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=9,
            color=NEUTRAL_GRAY,
        )
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.set_xlabel("Configurations")
        axis.set_ylabel("Median end-to-end wall time (s)")
        axis.set_title("Official AMD SBD CPU–GPU crossover")
        axis.legend(frameon=False)
        return _save_figure_if_changed(figure, output_path)


def _render_memory_svg(data: Mapping[str, Any], output_path: Path) -> bool:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    summaries = data["summaries"]
    with mpl.rc_context(
        {
            "svg.hashsalt": "autosbd-stage4-figures-v1",
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.grid": True,
            "grid.alpha": 0.25,
        }
    ):
        figure, axis = plt.subplots(figsize=(7.2, 4.6), constrained_layout=True)
        x = [row["n_configurations"] for row in summaries]
        peak = [row["peak_gpu_memory_mib"]["median"] for row in summaries]
        peak_error = [
            [
                row["peak_gpu_memory_mib"]["median"]
                - row["peak_gpu_memory_mib"]["q1"]
                for row in summaries
            ],
            [
                row["peak_gpu_memory_mib"]["q3"]
                - row["peak_gpu_memory_mib"]["median"]
                for row in summaries
            ],
        ]
        axis.errorbar(
            x,
            peak,
            yerr=peak_error,
            color=COLORBLIND_ORANGE,
            marker="s",
            linewidth=1.8,
            capsize=3,
            label="measured peak GPU memory",
        )
        axis.plot(
            x,
            [row["estimated_gpu_guard_mib"] for row in summaries],
            color=COLORBLIND_GREEN,
            marker="^",
            linewidth=1.8,
            label="pre-execution padded guard",
        )
        axis.plot(
            x,
            [row["minimum_gpu_admission_cap_mib"] for row in summaries],
            color=NEUTRAL_GRAY,
            linestyle="--",
            linewidth=1.5,
            label="minimum admission cap",
        )
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.set_xlabel("Configurations")
        axis.set_ylabel("GPU memory (MiB)")
        axis.set_title("GPU memory safety guard — boundary not reached")
        axis.legend(frameon=False)
        return _save_figure_if_changed(figure, output_path)


def _save_figure_if_changed(figure: Any, output_path: Path) -> bool:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp.svg", dir=output.parent
        )
        os.close(descriptor)
        temporary = Path(name)
        figure.savefig(
            temporary,
            format="svg",
            metadata={"Date": None, "Creator": "AutoSBD deterministic figure generator"},
        )
        payload = temporary.read_bytes()
    finally:
        import matplotlib.pyplot as plt

        plt.close(figure)
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return _write_bytes_if_changed(output, payload)


def _write_csv_if_changed(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    fieldnames: tuple[str, ...],
) -> bool:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        serialized = {
            field: json.dumps(row.get(field), sort_keys=True)
            if isinstance(row.get(field), (list, dict))
            else row.get(field)
            for field in fieldnames
        }
        writer.writerow(serialized)
    return _write_text_if_changed(path, stream.getvalue())


def _write_text_if_changed(path: Path, text: str) -> bool:
    return _write_bytes_if_changed(path, text.encode("utf-8"))


def _write_bytes_if_changed(path: Path, payload: bytes) -> bool:
    output = Path(path)
    if output.exists() and output.read_bytes() == payload:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True


def _load_mapping(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FigureError(f"cannot load {label}: {path}: {error}") from error
    if not isinstance(value, Mapping):
        raise FigureError(f"{label} must be a JSON object: {path}")
    return value


def _nested(mapping: Any, *keys: str) -> Any:
    value = mapping
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            raise FigureError(f"missing nested field: {'.'.join(keys)}")
        value = value[key]
    return value


def _require_summary(value: Any, instance: str, candidate: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FigureError(f"missing timing summary for {instance}/{candidate}")
    required = ("count", "minimum", "q1", "median", "q3", "iqr", "maximum")
    for key in required:
        if key == "count":
            _require_positive_int(value.get(key), f"{instance}/{candidate}/{key}")
        elif key == "iqr":
            _require_nonnegative_number(
                value.get(key), f"{instance}/{candidate}/{key}"
            )
        else:
            _require_positive_number(value.get(key), f"{instance}/{candidate}/{key}")
    if not (
        value["minimum"] <= value["q1"] <= value["median"] <= value["q3"] <= value["maximum"]
    ):
        raise FigureError(f"invalid quartile order for {instance}/{candidate}")
    return value


def _require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise FigureError(f"{label} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as error:
        raise FigureError(f"{label} must be a SHA-256 digest") from error
    if value.lower() != value:
        raise FigureError(f"{label} must be lowercase")
    return value


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise FigureError(f"{label} must be nonempty text")
    return value


def _require_positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FigureError(f"{label} must be a positive integer")
    return value


def _require_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FigureError(f"{label} must be a nonnegative integer")
    return value


def _require_positive_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FigureError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise FigureError(f"{label} must be finite and positive")
    return result


def _require_nonnegative_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FigureError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise FigureError(f"{label} must be finite and nonnegative")
    return result


__all__ = [
    "FigureError",
    "build_stage4_figure_data",
    "generate_stage4_figures",
    "sha256_path",
]
