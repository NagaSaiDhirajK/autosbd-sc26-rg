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
COLORBLIND_SKY = "#56B4E9"
COLORBLIND_YELLOW = "#F0E442"
COLORBLIND_PURPLE = "#CC79A7"

MULTIFAMILY_POLICIES = (
    "fixed_cpu16",
    "fixed_gpu",
    "static_size_threshold",
    "size_only_tree_ablation",
    "autosbd_full_tree",
    "measured_feasible_oracle",
)
MULTIFAMILY_DECISION_POLICIES = (
    "measured_feasible_oracle",
    "static_size_threshold",
    "size_only_tree_ablation",
    "autosbd_full_tree",
)
MULTIFAMILY_FAMILIES = ("fe4s4", "n2", "h2o")
MULTIFAMILY_POLICY_LABELS = {
    "fixed_cpu16": "Fixed CPU16",
    "fixed_gpu": "Fixed GPU",
    "static_size_threshold": "Static size\nthreshold",
    "size_only_tree_ablation": "Size-only\ntree",
    "autosbd_full_tree": "AutoSBD\nfull tree",
    "measured_feasible_oracle": "Measured\noracle",
}


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


def build_cpu_thread_scaling_figure_data(raw_dir: Path) -> dict[str, Any]:
    """Build CPU thread-scaling plot data from eligible raw CPU records."""

    raw_directory = Path(raw_dir)
    instances: dict[str, list[Mapping[str, Any]]] = {}
    for raw_path in sorted(raw_directory.glob("*.json")):
        raw = _load_mapping(raw_path, f"raw record {raw_path.name}")
        if raw.get("backend") != "cpu":
            continue
        if not (
            raw.get("status") == "success"
            and raw.get("correct") is True
            and raw.get("timing_eligible") is True
            and raw.get("warmup_or_measured") == "measured"
            and raw.get("timeout") is False
            and raw.get("oom") is False
            and raw.get("skip_reason") is None
        ):
            continue
        cpu_threads = raw.get("cpu_threads")
        if not isinstance(cpu_threads, int) or cpu_threads <= 0:
            continue
        instance = _require_text(raw.get("problem_instance"), "problem_instance")
        instances.setdefault(instance, []).append(raw)

    rows: list[dict[str, Any]] = []
    for instance, records in sorted(instances.items()):
        thread_levels = sorted({
            _require_positive_int(record.get("cpu_threads"), "cpu_threads")
            for record in records
        })
        if len(thread_levels) < 2:
            continue
        family_id = records[0].get("family_id")
        n_configurations = _require_positive_int(
            records[0].get("n_configurations"), "n_configurations"
        )
        for threads in thread_levels:
            group = [
                record
                for record in records
                if _require_positive_int(record.get("cpu_threads"), "cpu_threads")
                == threads
            ]
            wall_times = [
                _require_positive_number(record.get("wall_time_s"), "wall_time_s")
                for record in group
            ]
            solver_times = [
                _require_positive_number(record.get("solver_time_s"), "solver_time_s")
                for record in group
            ]
            wall_summary = summarize_values(wall_times)
            solver_summary = summarize_values(solver_times)
            rows.append(
                {
                    "problem_instance": instance,
                    "family_id": family_id,
                    "n_configurations": n_configurations,
                    "cpu_threads": threads,
                    "count": wall_summary["count"],
                    "wall_minimum_s": wall_summary["minimum"],
                    "wall_q1_s": wall_summary["q1"],
                    "wall_median_s": wall_summary["median"],
                    "wall_q3_s": wall_summary["q3"],
                    "wall_iqr_s": wall_summary["iqr"],
                    "wall_maximum_s": wall_summary["maximum"],
                    "solver_median_s": solver_summary["median"],
                }
            )
    if not rows:
        raise FigureError("no eligible CPU thread-scaling records")

    return {
        "schema_version": 1,
        "source": {
            "raw_directory": str(raw_directory),
            "primary_metric": "end_to_end_wall_time_s",
        },
        "rows": sorted(rows, key=lambda item: (item["problem_instance"], item["cpu_threads"])),
    }


def generate_cpu_thread_scaling_figures(
    raw_dir: Path, output_dir: Path, table_dir: Path
) -> dict[str, Any]:
    data = build_cpu_thread_scaling_figure_data(raw_dir)
    output_directory = Path(output_dir)
    table_directory = Path(table_dir)
    output_directory.mkdir(parents=True, exist_ok=True)
    table_directory.mkdir(parents=True, exist_ok=True)

    statuses: dict[str, bool] = {}
    trace_json = table_directory / "cpu_thread_scaling_figure_trace.json"
    statuses[str(trace_json)] = _write_text_if_changed(
        trace_json, json.dumps(data, indent=2, sort_keys=True) + "\n"
    )
    scaling_csv = table_directory / "cpu_thread_scaling.csv"
    statuses[str(scaling_csv)] = _write_csv_if_changed(
        scaling_csv,
        data["rows"],
        (
            "problem_instance",
            "family_id",
            "n_configurations",
            "cpu_threads",
            "count",
            "wall_minimum_s",
            "wall_q1_s",
            "wall_median_s",
            "wall_q3_s",
            "wall_iqr_s",
            "wall_maximum_s",
            "solver_median_s",
        ),
    )
    scaling_svg = output_directory / "cpu_thread_scaling.svg"
    statuses[str(scaling_svg)] = _render_cpu_thread_scaling_svg(data, scaling_svg)
    return {
        "status": "ok",
        "changed": statuses,
        "instance_count": len({row["problem_instance"] for row in data["rows"]}),
        "thread_variants": len({row["cpu_threads"] for row in data["rows"]}),
    }


def _render_cpu_thread_scaling_svg(
    data: Mapping[str, Any], output_path: Path
) -> bool:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    rows = data["rows"]
    instances = sorted({row["problem_instance"] for row in rows})
    colors = (
        COLORBLIND_BLUE,
        COLORBLIND_ORANGE,
        COLORBLIND_GREEN,
        COLORBLIND_SKY,
        COLORBLIND_PURPLE,
    )
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
        for color, instance in zip(colors, instances):
            instance_rows = [row for row in rows if row["problem_instance"] == instance]
            x = [row["cpu_threads"] for row in instance_rows]
            y = [row["wall_median_s"] for row in instance_rows]
            yerr = [
                [row["wall_median_s"] - row["wall_q1_s"] for row in instance_rows],
                [row["wall_q3_s"] - row["wall_median_s"] for row in instance_rows],
            ]
            axis.errorbar(
                x,
                y,
                yerr=yerr,
                label=instance,
                color=color,
                marker="o",
                linewidth=1.8,
                capsize=3,
            )
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.set_xticks([1, 4, 8, 16])
        axis.set_xticklabels(["1", "4", "8", "16"])
        axis.set_xlim(0.8, 18)
        axis.set_xlabel("CPU threads")
        axis.set_ylabel("Median end-to-end wall time (s)")
        axis.set_title("CPU thread-scaling pilot")
        axis.legend(frameon=False, fontsize=8)
        figure.text(
            0.5,
            0.015,
            "Source: eligible measured CPU raw records from results/raw.",
            ha="center",
            va="bottom",
            fontsize=6,
            family="DejaVu Sans Mono",
        )
        description = (
            "Internal CPU thread-scaling pilot for eligible measured raw CPU records. "
            "Only instances with multiple thread counts are shown."
        )
        return _save_figure_if_changed(
            figure, output_path, description=description
        )


def build_multifamily_holdout_figure_data(policy_summary_path: Path) -> dict[str, Any]:
    summary_file = Path(policy_summary_path)
    rows = _load_csv_rows(
        summary_file,
        "multifamily policy summary",
        {
            "scope",
            "heldout_family_id",
            "policy",
            "selection_accuracy",
            "geometric_mean_selected_over_oracle_valid_only",
            "median_normalized_regret_valid_only",
            "p90_normalized_regret_valid_only",
        },
    )
    heldout_rows = [row for row in rows if row["scope"] == "heldout_family"]
    if len(heldout_rows) != 18:
        raise FigureError(
            f"multifamily heldout summary must contain 18 rows, found {len(heldout_rows)}"
        )
    data_rows: list[dict[str, Any]] = []
    for row in heldout_rows:
        policy = row["policy"]
        if policy not in MULTIFAMILY_POLICIES:
            raise FigureError(f"unexpected multifamily summary policy: {policy}")
        family_id = _require_text(row["heldout_family_id"], "heldout_family_id")
        data_rows.append(
            {
                "family_id": family_id,
                "policy": policy,
                "selection_accuracy": _parse_fraction(row["selection_accuracy"], "selection_accuracy"),
                "geometric_mean_overhead_percent": (
                    _parse_positive_number(
                        row["geometric_mean_selected_over_oracle_valid_only"],
                        "geometric_mean_selected_over_oracle_valid_only",
                    )
                    - 1.0
                )
                * 100.0,
                "median_normalized_regret_percent": _parse_nonnegative_number(
                    row["median_normalized_regret_valid_only"],
                    "median_normalized_regret_valid_only",
                )
                * 100.0,
                "p90_normalized_regret_percent": _parse_nonnegative_number(
                    row["p90_normalized_regret_valid_only"],
                    "p90_normalized_regret_valid_only",
                )
                * 100.0,
            }
        )
    families = sorted({row["family_id"] for row in data_rows})
    return {
        "schema_version": 1,
        "source": {
            "policy_summary_path": str(summary_file),
            "policy_summary_sha256": sha256_path(summary_file),
            "primary_metric": "selection_accuracy",
        },
        "rows": data_rows,
        "families": families,
    }


def generate_multifamily_holdout_figures(
    policy_summary_path: Path, output_dir: Path, table_dir: Path
) -> dict[str, Any]:
    data = build_multifamily_holdout_figure_data(policy_summary_path)
    output_directory = Path(output_dir)
    table_directory = Path(table_dir)
    output_directory.mkdir(parents=True, exist_ok=True)
    table_directory.mkdir(parents=True, exist_ok=True)
    statuses: dict[str, bool] = {}
    trace_path = table_directory / "multifamily_holdout_figure_trace.json"
    statuses[str(trace_path)] = _write_text_if_changed(
        trace_path, json.dumps(data, indent=2, sort_keys=True) + "\n"
    )
    holdout_csv = table_directory / "multifamily_holdout_generalization.csv"
    statuses[str(holdout_csv)] = _write_csv_if_changed(
        holdout_csv,
        data["rows"],
        (
            "family_id",
            "policy",
            "selection_accuracy",
            "geometric_mean_overhead_percent",
            "median_normalized_regret_percent",
            "p90_normalized_regret_percent",
        ),
    )
    holdout_svg = output_directory / "multifamily_holdout_generalization.svg"
    statuses[str(holdout_svg)] = _render_multifamily_holdout_svg(data, holdout_svg)
    return {
        "status": "ok",
        "changed": statuses,
        "families": len(data["families"]),
        "policies": len({row["policy"] for row in data["rows"]}),
    }


def _render_multifamily_holdout_svg(
    data: Mapping[str, Any], output_path: Path
) -> bool:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    rows = data["rows"]
    families = data["families"]
    policies = MULTIFAMILY_POLICIES
    colors = (
        COLORBLIND_BLUE,
        COLORBLIND_ORANGE,
        COLORBLIND_GREEN,
        COLORBLIND_SKY,
        COLORBLIND_YELLOW,
        COLORBLIND_PURPLE,
    )
    family_order = {family: index for index, family in enumerate(families)}
    grouped: dict[str, list[dict[str, Any]]] = {policy: [] for policy in policies}
    for row in rows:
        grouped[row["policy"]].append(row)
    with mpl.rc_context(
        {
            "svg.hashsalt": "autosbd-multifamily-figures-v1",
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.grid": True,
            "grid.alpha": 0.25,
        }
    ):
        figure, axes = plt.subplots(ncols=2, figsize=(12.8, 4.6), constrained_layout=True)
        width = 0.12
        x = list(range(len(families)))
        for index, policy in enumerate(policies):
            policy_rows = sorted(
                grouped[policy], key=lambda row: family_order[row["family_id"]]
            )
            offsets = [position + (index - 2.5) * width for position in x]
            axes[0].bar(
                offsets,
                [row["selection_accuracy"] for row in policy_rows],
                width=width,
                label=MULTIFAMILY_POLICY_LABELS[policy],
                color=colors[index],
                edgecolor="#333333",
                linewidth=0.8,
            )
            axes[1].bar(
                offsets,
                [row["geometric_mean_overhead_percent"] for row in policy_rows],
                width=width,
                label=MULTIFAMILY_POLICY_LABELS[policy],
                color=colors[index],
                edgecolor="#333333",
                linewidth=0.8,
            )
        axes[0].set_xticks(x, families)
        axes[0].set_ylim(0.0, 1.0)
        axes[0].set_ylabel("Selection accuracy")
        axes[0].set_title("Held-out selection accuracy by family")
        axes[1].set_xticks(x, families)
        axes[1].set_ylabel("Geometric mean overhead (%)")
        axes[1].set_title("Held-out runtime overhead vs oracle")
        axes[1].set_ylim(0.0, max(row["geometric_mean_overhead_percent"] for row in rows) * 1.12)
        axes[1].axhline(0.0, color="#333333", linewidth=0.8)
        axes[0].legend(frameon=False, fontsize=8, ncol=2)
        figure.text(
            0.5,
            0.01,
            "Source: held-out family summary from policy_summary.csv.",
            ha="center",
            va="bottom",
            fontsize=6,
            family="DejaVu Sans Mono",
        )
        description = (
            "Internal multifamily held-out generalization figure showing accuracy "
            "and runtime overhead for each held-out family and policy."
        )
        return _save_figure_if_changed(figure, output_path, description=description)


def build_inference_overhead_figure_data(inference_overhead_path: Path) -> dict[str, Any]:
    path = Path(inference_overhead_path)
    rows = _load_csv_rows(
        path,
        "inference overhead",
        {
            "measurement",
            "median_us",
            "p90_us",
            "p95_us",
            "maximum_us",
            "selected_candidate_counts",
            "hot_median_percent_of_shortest_sbd_runtime",
            "raw_record_path",
            "raw_record_sha256",
        },
    )
    if not rows:
        raise FigureError("inference overhead file is empty")
    data_rows: list[dict[str, Any]] = []
    for row in rows:
        label = row["measurement"]
        data_rows.append(
            {
                "measurement": label,
                "median_us": _parse_positive_number(row["median_us"], f"median_us for {label}"),
                "p90_us": _parse_nonnegative_number(row["p90_us"], f"p90_us for {label}"),
                "p95_us": _parse_nonnegative_number(row["p95_us"], f"p95_us for {label}"),
                "maximum_us": _parse_nonnegative_number(row["maximum_us"], f"maximum_us for {label}"),
                "selected_candidate_counts": row["selected_candidate_counts"],
                "hot_median_percent_of_shortest_sbd_runtime": row["hot_median_percent_of_shortest_sbd_runtime"],
                "raw_record_path": row["raw_record_path"],
                "raw_record_sha256": row["raw_record_sha256"],
            }
        )
    return {
        "schema_version": 1,
        "source": {
            "inference_overhead_path": str(path),
            "inference_overhead_sha256": sha256_path(path),
            "primary_metric": "median_us",
        },
        "rows": data_rows,
    }


def generate_inference_overhead_figures(
    inference_overhead_path: Path, output_dir: Path, table_dir: Path
) -> dict[str, Any]:
    data = build_inference_overhead_figure_data(inference_overhead_path)
    output_directory = Path(output_dir)
    table_directory = Path(table_dir)
    output_directory.mkdir(parents=True, exist_ok=True)
    table_directory.mkdir(parents=True, exist_ok=True)
    statuses: dict[str, bool] = {}
    trace_path = table_directory / "inference_overhead_figure_trace.json"
    statuses[str(trace_path)] = _write_text_if_changed(
        trace_path, json.dumps(data, indent=2, sort_keys=True) + "\n"
    )
    overhead_csv = table_directory / "inference_overhead.csv"
    statuses[str(overhead_csv)] = _write_csv_if_changed(
        overhead_csv,
        data["rows"],
        (
            "measurement",
            "median_us",
            "p90_us",
            "p95_us",
            "maximum_us",
            "selected_candidate_counts",
            "hot_median_percent_of_shortest_sbd_runtime",
            "raw_record_path",
            "raw_record_sha256",
        ),
    )
    overhead_svg = output_directory / "inference_overhead.svg"
    statuses[str(overhead_svg)] = _render_inference_overhead_svg(data, overhead_svg)
    return {
        "status": "ok",
        "changed": statuses,
        "measurements": len(data["rows"]),
    }


def _render_inference_overhead_svg(
    data: Mapping[str, Any], output_path: Path
) -> bool:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    rows = data["rows"]
    measurements = [row["measurement"] for row in rows]
    medians = [row["median_us"] for row in rows]
    colors = (COLORBLIND_BLUE, COLORBLIND_ORANGE, COLORBLIND_GREEN, COLORBLIND_PURPLE)
    with mpl.rc_context(
        {
            "svg.hashsalt": "autosbd-multifamily-figures-v1",
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.grid": True,
            "grid.alpha": 0.25,
        }
    ):
        figure, axis = plt.subplots(figsize=(7.2, 4.6), constrained_layout=True)
        bars = axis.bar(
            measurements,
            medians,
            color=colors[: len(measurements)],
            edgecolor="#333333",
            linewidth=0.8,
        )
        axis.set_ylabel("Median selection overhead (µs)")
        axis.set_title("Inference overhead for AutoSBD selection")
        for bar, row in zip(bars, rows):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(medians) * 0.02,
                f"{row['median_us']:.1f}µs",
                ha="center",
                va="bottom",
                fontsize=8,
            )
        figure.text(
            0.5,
            0.015,
            "Source: inference_overhead.csv generated from evaluation overhead measurements.",
            ha="center",
            va="bottom",
            fontsize=6,
            family="DejaVu Sans Mono",
        )
        description = (
            "Measured AutoSBD inference overhead for hot selection and cold load-plus-selection."
        )
        return _save_figure_if_changed(figure, output_path, description=description)


def build_numerical_parity_figure_data(raw_dir: Path) -> dict[str, Any]:
    raw_directory = Path(raw_dir)
    rows: list[dict[str, Any]] = []
    for raw_path in sorted(raw_directory.glob("*.json")):
        raw = _load_mapping(raw_path, f"raw record {raw_path.name}")
        if raw.get("status") != "success" or raw.get("correct") is not True:
            continue
        energy = raw.get("energy_or_eigenvalue")
        reference = raw.get("reference_value")
        relative_error = raw.get("relative_error")
        if energy is None or reference is None or relative_error is None:
            continue
        rows.append(
            {
                "problem_instance": _require_text(raw.get("problem_instance"), "problem_instance"),
                "backend": _require_text(raw.get("backend"), "backend"),
                "family_id": raw.get("family_id"),
                "energy_or_eigenvalue": _require_number(energy, "energy_or_eigenvalue"),
                "reference_value": _require_number(reference, "reference_value"),
                "relative_error": _require_number(relative_error, "relative_error"),
            }
        )
    if not rows:
        raise FigureError("no eligible energy parity records")
    return {
        "schema_version": 1,
        "source": {
            "raw_directory": str(raw_directory),
            "primary_metric": "energy_or_eigenvalue",
        },
        "rows": rows,
    }


def generate_numerical_parity_figures(
    raw_dir: Path, output_dir: Path, table_dir: Path
) -> dict[str, Any]:
    data = build_numerical_parity_figure_data(raw_dir)
    output_directory = Path(output_dir)
    table_directory = Path(table_dir)
    output_directory.mkdir(parents=True, exist_ok=True)
    table_directory.mkdir(parents=True, exist_ok=True)
    statuses: dict[str, bool] = {}
    trace_path = table_directory / "numerical_parity_figure_trace.json"
    statuses[str(trace_path)] = _write_text_if_changed(
        trace_path, json.dumps(data, indent=2, sort_keys=True) + "\n"
    )
    parity_csv = table_directory / "numerical_parity.csv"
    statuses[str(parity_csv)] = _write_csv_if_changed(
        parity_csv,
        data["rows"],
        (
            "problem_instance",
            "family_id",
            "backend",
            "energy_or_eigenvalue",
            "reference_value",
            "relative_error",
        ),
    )
    parity_svg = output_directory / "numerical_parity.svg"
    statuses[str(parity_svg)] = _render_numerical_parity_svg(data, parity_svg)
    return {
        "status": "ok",
        "changed": statuses,
        "records": len(data["rows"]),
    }


def _render_numerical_parity_svg(
    data: Mapping[str, Any], output_path: Path
) -> bool:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    rows = data["rows"]
    backends = sorted({row["backend"] for row in rows})
    backend_colors = {"cpu": COLORBLIND_BLUE, "gpu": COLORBLIND_ORANGE}
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
        x = [row["reference_value"] for row in rows]
        y = [row["energy_or_eigenvalue"] for row in rows]
        colors = [backend_colors.get(row["backend"], NEUTRAL_GRAY) for row in rows]
        axis.scatter(x, y, c=colors, alpha=0.8, edgecolor="#333333", linewidth=0.4)
        min_val = min(min(x), min(y))
        max_val = max(max(x), max(y))
        axis.plot([min_val, max_val], [min_val, max_val], color="#333333", linewidth=1.0, linestyle="--")
        axis.set_xlabel("Reference energy")
        axis.set_ylabel("Measured energy")
        axis.set_title("Numerical parity of final energy across raw records")
        axis.set_aspect("equal", adjustable="box")
        axis.legend(
            handles=(
                mpl.lines.Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORBLIND_BLUE, label="CPU", markersize=6),
                mpl.lines.Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORBLIND_ORANGE, label="GPU", markersize=6),
            ),
            loc="upper left",
            frameon=False,
        )
        max_error = max(abs(row["relative_error"]) for row in rows) * 100.0
        axis.text(
            0.98,
            0.03,
            f"max relative error: {max_error:.2g}%",
            transform=axis.transAxes,
            ha="right",
            va="bottom",
            fontsize=8,
            color=NEUTRAL_GRAY,
        )
        figure.text(
            0.5,
            0.01,
            "Source: raw energy/eigenvalue records from results/raw.",
            ha="center",
            va="bottom",
            fontsize=6,
            family="DejaVu Sans Mono",
        )
        description = (
            "Internal numerical parity figure comparing measured and reference energies in raw records."
        )
        return _save_figure_if_changed(figure, output_path, description=description)


def build_run_eligibility_figure_data(
    aggregate_path: Path, raw_dir: Path
) -> dict[str, Any]:
    aggregate_file = Path(aggregate_path)
    raw_directory = Path(raw_dir)
    aggregate = _load_mapping(aggregate_file, "aggregate")
    record_counts = aggregate.get("record_counts")
    if not isinstance(record_counts, Mapping):
        raise FigureError("aggregate record_counts missing or invalid")
    total_raw = 0
    success_correct = 0
    measured_eligible = 0
    for raw_path in sorted(raw_directory.glob("*.json")):
        total_raw += 1
        raw = _load_mapping(raw_path, f"raw record {raw_path.name}")
        if raw.get("status") == "success" and raw.get("correct") is True:
            success_correct += 1
            if (
                raw.get("timing_eligible") is True
                and raw.get("warmup_or_measured") == "measured"
                and raw.get("timeout") is False
                and raw.get("oom") is False
                and raw.get("skip_reason") is None
            ):
                measured_eligible += 1
    return {
        "schema_version": 1,
        "source": {
            "aggregate_path": str(aggregate_file),
            "aggregate_sha256": sha256_path(aggregate_file),
            "raw_directory": str(raw_directory),
            "primary_metric": "count",
        },
        "counts": {
            "total_raw_attempts": total_raw,
            "success_and_correct": success_correct,
            "measured_and_eligible": measured_eligible,
            "stage4_input": _require_positive_int(record_counts.get("input"), "record_counts.input"),
            "stage4_included": _require_positive_int(record_counts.get("included"), "record_counts.included"),
            "stage4_excluded": _require_nonnegative_int(record_counts.get("excluded"), "record_counts.excluded"),
        },
    }


def generate_run_eligibility_figures(
    aggregate_path: Path, raw_dir: Path, output_dir: Path, table_dir: Path
) -> dict[str, Any]:
    data = build_run_eligibility_figure_data(aggregate_path, raw_dir)
    output_directory = Path(output_dir)
    table_directory = Path(table_dir)
    output_directory.mkdir(parents=True, exist_ok=True)
    table_directory.mkdir(parents=True, exist_ok=True)
    statuses: dict[str, bool] = {}
    trace_json = table_directory / "run_eligibility_figure_trace.json"
    statuses[str(trace_json)] = _write_text_if_changed(
        trace_json, json.dumps(data, indent=2, sort_keys=True) + "\n"
    )
    eligibility_csv = table_directory / "run_eligibility_counts.csv"
    statuses[str(eligibility_csv)] = _write_csv_if_changed(
        eligibility_csv,
        [data["counts"]],
        (
            "total_raw_attempts",
            "success_and_correct",
            "measured_and_eligible",
            "stage4_input",
            "stage4_included",
            "stage4_excluded",
        ),
    )
    eligibility_svg = output_directory / "run_eligibility_flow.svg"
    statuses[str(eligibility_svg)] = _render_run_eligibility_svg(data, eligibility_svg)
    return {
        "status": "ok",
        "changed": statuses,
        "total_raw_attempts": data["counts"]["total_raw_attempts"],
    }


def _render_run_eligibility_svg(
    data: Mapping[str, Any], output_path: Path
) -> bool:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    counts = data["counts"]
    labels = [
        "Total raw attempts",
        "Success + correct",
        "Measured eligible",
        "Stage4 input",
        "Stage4 included",
        "Stage4 excluded",
    ]
    values = [
        counts["total_raw_attempts"],
        counts["success_and_correct"],
        counts["measured_and_eligible"],
        counts["stage4_input"],
        counts["stage4_included"],
        counts["stage4_excluded"],
    ]
    with mpl.rc_context(
        {
            "svg.hashsalt": "autosbd-stage4-figures-v1",
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.grid": True,
            "grid.alpha": 0.25,
        }
    ):
        figure, axis = plt.subplots(figsize=(8.4, 4.6), constrained_layout=True)
        bars = axis.bar(
            labels,
            values,
            color=(COLORBLIND_BLUE, COLORBLIND_ORANGE, COLORBLIND_GREEN, NEUTRAL_GRAY, COLORBLIND_SKY, COLORBLIND_PURPLE),
            edgecolor="#333333",
            linewidth=0.8,
        )
        axis.set_ylabel("Record counts")
        axis.set_title("Stage4 run eligibility and outcome flow")
        axis.set_xticklabels(labels, rotation=45, ha="right")
        for bar in bars:
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(values) * 0.02,
                f"{int(bar.get_height())}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
        figure.text(
            0.5,
            0.01,
            "Source: stage4 aggregate counts and eligible raw record counts.",
            ha="center",
            va="bottom",
            fontsize=6,
            family="DejaVu Sans Mono",
        )
        description = (
            "Internal run eligibility flow counts for raw records and Stage4 aggregate inclusion."
        )
        return _save_figure_if_changed(figure, output_path, description=description)


def build_multifamily_figure_data(
    policy_summary_path: Path,
    policy_predictions_path: Path,
) -> dict[str, Any]:
    """Build strict plot data from the sealed leave-one-family-out outputs."""

    summary_file = Path(policy_summary_path)
    predictions_file = Path(policy_predictions_path)
    summary_rows = _load_csv_rows(
        summary_file,
        "multifamily policy summary",
        {
            "scope",
            "heldout_family_id",
            "policy",
            "requested_instances",
            "valid_instances",
            "invalid_instances",
            "failure_instances",
            "selection_accuracy",
            "geometric_mean_selected_over_oracle_valid_only",
        },
    )
    prediction_rows = _load_csv_rows(
        predictions_file,
        "multifamily policy predictions",
        {
            "fold_id",
            "heldout_family_id",
            "policy",
            "family_id",
            "molecule",
            "instance_id",
            "problem_instance",
            "input_sha256",
            "n_configurations",
            "decision_candidate_name",
            "selected_candidate_name",
            "oracle_candidate_names",
            "selected_wall_time_s",
            "oracle_wall_time_s",
            "normalized_runtime",
            "normalized_regret",
            "selection_correct",
            "valid",
            "failure",
            "invalid_reason",
            "selected_source_record_ids",
            "oracle_source_record_ids",
        },
    )
    if len(summary_rows) != 24:
        raise FigureError(
            f"multifamily summary must contain 24 rows, found {len(summary_rows)}"
        )
    if len(prediction_rows) != 90:
        raise FigureError(
            f"multifamily predictions must contain 90 rows, found {len(prediction_rows)}"
        )

    pooled_by_policy: dict[str, Mapping[str, str]] = {}
    heldout_pairs: set[tuple[str, str]] = set()
    for row in summary_rows:
        scope = row["scope"]
        policy = row["policy"]
        if policy not in MULTIFAMILY_POLICIES:
            raise FigureError(f"unexpected multifamily summary policy: {policy}")
        if scope == "pooled":
            if row["heldout_family_id"]:
                raise FigureError(f"pooled summary names a held-out family: {policy}")
            if policy in pooled_by_policy:
                raise FigureError(f"duplicate pooled summary policy: {policy}")
            pooled_by_policy[policy] = row
        elif scope == "heldout_family":
            family = row["heldout_family_id"]
            if family not in MULTIFAMILY_FAMILIES:
                raise FigureError(f"unexpected held-out family: {family}")
            pair = (family, policy)
            if pair in heldout_pairs:
                raise FigureError(f"duplicate held-out summary row: {family}/{policy}")
            heldout_pairs.add(pair)
        else:
            raise FigureError(f"unexpected multifamily summary scope: {scope}")
    if set(pooled_by_policy) != set(MULTIFAMILY_POLICIES):
        raise FigureError("pooled multifamily summary does not contain all six policies")
    expected_heldout = {
        (family, policy)
        for family in MULTIFAMILY_FAMILIES
        for policy in MULTIFAMILY_POLICIES
    }
    if heldout_pairs != expected_heldout:
        raise FigureError("held-out multifamily summary is not a 3-family x 6-policy grid")

    rows_by_instance: dict[str, dict[str, dict[str, Any]]] = {}
    instance_identity: dict[str, dict[str, Any]] = {}
    runtimes_by_policy: dict[str, list[float]] = {
        policy: [] for policy in MULTIFAMILY_POLICIES
    }
    seen_fold_by_family: dict[str, str] = {}
    for row in prediction_rows:
        policy = row["policy"]
        if policy not in MULTIFAMILY_POLICIES:
            raise FigureError(f"unexpected multifamily prediction policy: {policy}")
        family = row["family_id"]
        if family not in MULTIFAMILY_FAMILIES:
            raise FigureError(f"unexpected prediction family: {family}")
        if row["heldout_family_id"] != family:
            raise FigureError(f"prediction is not from its family-held-out fold: {family}")
        fold_id = _require_text(row["fold_id"], "fold_id")
        previous_fold = seen_fold_by_family.setdefault(family, fold_id)
        if previous_fold != fold_id:
            raise FigureError(f"family appears in multiple prediction folds: {family}")
        instance_id = _require_text(row["instance_id"], "instance_id")
        n_configurations = _parse_positive_int(
            row["n_configurations"], "n_configurations"
        )
        input_sha256 = _require_digest(row["input_sha256"], "input_sha256")
        selected = row["selected_candidate_name"]
        decision = row["decision_candidate_name"]
        if selected not in {CPU_CANDIDATE, GPU_CANDIDATE} or decision != selected:
            raise FigureError(f"invalid selected decision for {instance_id}/{policy}")
        oracle_names = _parse_json_string_list(
            row["oracle_candidate_names"], "oracle_candidate_names"
        )
        if len(oracle_names) != 1 or oracle_names[0] not in {
            CPU_CANDIDATE,
            GPU_CANDIDATE,
        }:
            raise FigureError(f"expected one CPU/GPU oracle for {instance_id}")
        selected_time = _parse_positive_number(
            row["selected_wall_time_s"], "selected_wall_time_s"
        )
        oracle_time = _parse_positive_number(
            row["oracle_wall_time_s"], "oracle_wall_time_s"
        )
        normalized_runtime = _parse_positive_number(
            row["normalized_runtime"], "normalized_runtime"
        )
        normalized_regret = _parse_nonnegative_number(
            row["normalized_regret"], "normalized_regret"
        )
        if normalized_runtime < 1.0 - 1e-12:
            raise FigureError(f"normalized runtime below oracle for {instance_id}/{policy}")
        if not math.isclose(
            normalized_runtime, selected_time / oracle_time, rel_tol=1e-12, abs_tol=1e-12
        ) or not math.isclose(
            normalized_regret,
            normalized_runtime - 1.0,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise FigureError(f"inconsistent runtime/regret for {instance_id}/{policy}")
        selection_correct = _parse_bool(row["selection_correct"], "selection_correct")
        if selection_correct != (selected in oracle_names):
            raise FigureError(f"inconsistent selection correctness for {instance_id}/{policy}")
        if not _parse_bool(row["valid"], "valid"):
            raise FigureError(f"invalid row admitted to multifamily figure: {instance_id}/{policy}")
        if _parse_bool(row["failure"], "failure") or row["invalid_reason"]:
            raise FigureError(f"failed row admitted to multifamily figure: {instance_id}/{policy}")
        selected_record_ids = _parse_digest_list(
            row["selected_source_record_ids"], "selected_source_record_ids"
        )
        oracle_record_ids = _parse_digest_list(
            row["oracle_source_record_ids"], "oracle_source_record_ids"
        )
        if len(selected_record_ids) != 3 or len(oracle_record_ids) != 3:
            raise FigureError(f"expected three source records for {instance_id}/{policy}")

        identity = {
            "family_id": family,
            "molecule": _require_text(row["molecule"], "molecule"),
            "instance_id": instance_id,
            "problem_instance": _require_text(
                row["problem_instance"], "problem_instance"
            ),
            "input_sha256": input_sha256,
            "n_configurations": n_configurations,
            "fold_id": fold_id,
            "oracle_candidate": oracle_names[0],
            "oracle_wall_time_s": oracle_time,
            "oracle_source_record_ids": oracle_record_ids,
        }
        existing_identity = instance_identity.setdefault(instance_id, identity)
        if existing_identity != identity:
            raise FigureError(f"inconsistent identity across policies: {instance_id}")
        policy_rows = rows_by_instance.setdefault(instance_id, {})
        if policy in policy_rows:
            raise FigureError(f"duplicate prediction row: {instance_id}/{policy}")
        policy_rows[policy] = {
            "selected_candidate": selected,
            "selected_wall_time_s": selected_time,
            "normalized_runtime": normalized_runtime,
            "normalized_regret": normalized_regret,
            "selection_correct": selection_correct,
            "selected_source_record_ids": selected_record_ids,
        }
        runtimes_by_policy[policy].append(normalized_runtime)

    if len(rows_by_instance) != 15:
        raise FigureError(
            f"multifamily predictions must contain 15 instances, found {len(rows_by_instance)}"
        )
    family_counts = {family: 0 for family in MULTIFAMILY_FAMILIES}
    for instance_id, policy_rows in rows_by_instance.items():
        if set(policy_rows) != set(MULTIFAMILY_POLICIES):
            raise FigureError(f"instance does not contain all six policies: {instance_id}")
        family_counts[instance_identity[instance_id]["family_id"]] += 1
        oracle = policy_rows["measured_feasible_oracle"]
        if (
            oracle["selected_candidate"]
            != instance_identity[instance_id]["oracle_candidate"]
            or not math.isclose(oracle["normalized_runtime"], 1.0, abs_tol=1e-12)
        ):
            raise FigureError(f"invalid measured oracle row: {instance_id}")
    if any(count != 5 for count in family_counts.values()):
        raise FigureError(f"expected five instances per family, found {family_counts}")

    policy_summaries: list[dict[str, Any]] = []
    for policy in MULTIFAMILY_POLICIES:
        source = pooled_by_policy[policy]
        requested = _parse_positive_int(source["requested_instances"], "requested_instances")
        valid = _parse_positive_int(source["valid_instances"], "valid_instances")
        invalid = _parse_nonnegative_int(source["invalid_instances"], "invalid_instances")
        failures = _parse_nonnegative_int(source["failure_instances"], "failure_instances")
        if (requested, valid, invalid, failures) != (15, 15, 0, 0):
            raise FigureError(f"unexpected pooled validity counts for {policy}")
        reported = _parse_positive_number(
            source["geometric_mean_selected_over_oracle_valid_only"],
            "geometric_mean_selected_over_oracle_valid_only",
        )
        derived = math.exp(
            math.fsum(math.log(value) for value in runtimes_by_policy[policy]) / 15
        )
        if not math.isclose(reported, derived, rel_tol=1e-12, abs_tol=1e-12):
            raise FigureError(f"pooled geometric mean disagrees with predictions: {policy}")
        accuracy = _parse_fraction(source["selection_accuracy"], "selection_accuracy")
        derived_accuracy = sum(
            1
            for rows in rows_by_instance.values()
            if rows[policy]["selection_correct"]
        ) / 15
        if not math.isclose(accuracy, derived_accuracy, rel_tol=1e-12, abs_tol=1e-12):
            raise FigureError(f"pooled accuracy disagrees with predictions: {policy}")
        policy_summaries.append(
            {
                "policy": policy,
                "label": MULTIFAMILY_POLICY_LABELS[policy],
                "geometric_mean_selected_over_oracle": reported,
                "geometric_mean_overhead_percent": (reported - 1.0) * 100.0,
                "selection_accuracy": accuracy,
                "instances": 15,
            }
        )

    family_order = {family: index for index, family in enumerate(MULTIFAMILY_FAMILIES)}
    instances: list[dict[str, Any]] = []
    for instance_id, identity in instance_identity.items():
        instances.append(
            {
                **identity,
                "display_label": (
                    f"{identity['molecule']}  {identity['n_configurations']:,}"
                ),
                "decisions": {
                    policy: rows_by_instance[instance_id][policy]
                    for policy in MULTIFAMILY_DECISION_POLICIES
                },
            }
        )
    instances.sort(
        key=lambda row: (
            family_order[row["family_id"]],
            row["n_configurations"],
            row["instance_id"],
        )
    )

    return {
        "schema_version": 1,
        "source": {
            "policy_summary_path": str(summary_file),
            "policy_summary_sha256": sha256_path(summary_file),
            "policy_predictions_path": str(predictions_file),
            "policy_predictions_sha256": sha256_path(predictions_file),
            "evaluation": "leave-one-family-out; three folds; 15 held-out instances",
            "primary_metric": "end_to_end_wall_time_s",
        },
        "policy_summaries": policy_summaries,
        "instances": instances,
        "decision_policies": list(MULTIFAMILY_DECISION_POLICIES),
        "smoothing": "none",
    }


def generate_multifamily_figures(
    policy_summary_path: Path,
    policy_predictions_path: Path,
    output_dir: Path,
    table_dir: Path,
) -> dict[str, Any]:
    """Generate deterministic internal multifamily policy and decision SVGs."""

    data = build_multifamily_figure_data(
        policy_summary_path, policy_predictions_path
    )
    output_directory = Path(output_dir)
    table_directory = Path(table_dir)
    output_directory.mkdir(parents=True, exist_ok=True)
    table_directory.mkdir(parents=True, exist_ok=True)
    statuses: dict[str, bool] = {}
    trace_path = table_directory / "multifamily_figure_trace.json"
    statuses[str(trace_path)] = _write_text_if_changed(
        trace_path, json.dumps(data, indent=2, sort_keys=True) + "\n"
    )
    policy_path = output_directory / "multifamily_policy_regret.svg"
    decisions_path = output_directory / "multifamily_instance_decisions.svg"
    statuses[str(policy_path)] = _render_multifamily_policy_svg(data, policy_path)
    statuses[str(decisions_path)] = _render_multifamily_decisions_svg(
        data, decisions_path
    )
    return {
        "status": "ok",
        "changed": statuses,
        "policy_summary_sha256": data["source"]["policy_summary_sha256"],
        "policy_predictions_sha256": data["source"]["policy_predictions_sha256"],
        "policies": len(data["policy_summaries"]),
        "heldout_instances": len(data["instances"]),
    }


def _multifamily_source_caption(data: Mapping[str, Any]) -> str:
    source = data["source"]
    return (
        "policy_summary.csv SHA-256: "
        f"{source['policy_summary_sha256']}\n"
        "policy_predictions.csv SHA-256: "
        f"{source['policy_predictions_sha256']}"
    )


def _render_multifamily_policy_svg(
    data: Mapping[str, Any], output_path: Path
) -> bool:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    summaries = data["policy_summaries"]
    colors = (
        COLORBLIND_BLUE,
        COLORBLIND_ORANGE,
        COLORBLIND_GREEN,
        COLORBLIND_SKY,
        COLORBLIND_PURPLE,
        NEUTRAL_GRAY,
    )
    caption = _multifamily_source_caption(data)
    with mpl.rc_context(
        {
            "svg.hashsalt": "autosbd-multifamily-figures-v1",
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.grid": True,
            "grid.alpha": 0.25,
        }
    ):
        figure, axis = plt.subplots(figsize=(8.4, 4.9))
        figure.subplots_adjust(left=0.10, right=0.98, top=0.87, bottom=0.29)
        x = list(range(len(summaries)))
        heights = [row["geometric_mean_overhead_percent"] for row in summaries]
        bars = axis.bar(x, heights, width=0.68, color=colors, edgecolor="#333333")
        axis.axhline(0.0, color="#333333", linewidth=0.8)
        axis.set_xticks(x, [row["label"] for row in summaries])
        axis.set_ylabel("Geometric-mean selected/oracle overhead (%)")
        axis.set_title("Held-out policy runtime overhead vs measured oracle")
        upper = max(heights) * 1.14 if max(heights) > 0 else 1.0
        axis.set_ylim(0.0, upper)
        axis.grid(axis="x", visible=False)
        for bar, value in zip(bars, heights):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                value + upper * 0.018,
                f"{value:.1f}%",
                ha="center",
                va="bottom",
                fontsize=9,
            )
        figure.text(
            0.5,
            0.035,
            caption,
            ha="center",
            va="bottom",
            fontsize=5.5,
            family="DejaVu Sans Mono",
        )
        description = (
            "Internal held-out multifamily policy comparison. Sources: "
            + caption.replace("\n", "; ")
        )
        return _save_figure_if_changed(
            figure, output_path, description=description
        )


def _format_regret_percent(regret: float) -> str:
    percent = regret * 100.0
    if abs(percent) < 0.05:
        return "0%"
    if percent < 10.0:
        return f"{percent:.1f}%"
    return f"{percent:.0f}%"


def _render_multifamily_decisions_svg(
    data: Mapping[str, Any], output_path: Path
) -> bool:
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    instances = data["instances"]
    policies = data["decision_policies"]
    labels = {
        "measured_feasible_oracle": "Measured oracle",
        "static_size_threshold": "Static threshold",
        "size_only_tree_ablation": "Size-only tree",
        "autosbd_full_tree": "AutoSBD full tree",
    }
    candidate_colors = {
        CPU_CANDIDATE: COLORBLIND_BLUE,
        GPU_CANDIDATE: COLORBLIND_ORANGE,
    }
    caption = _multifamily_source_caption(data)
    with mpl.rc_context(
        {
            "svg.hashsalt": "autosbd-multifamily-figures-v1",
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.grid": False,
        }
    ):
        figure, axis = plt.subplots(figsize=(8.8, 7.4))
        figure.subplots_adjust(left=0.20, right=0.985, top=0.84, bottom=0.13)
        for row_index, instance in enumerate(instances):
            for column_index, policy in enumerate(policies):
                decision = instance["decisions"][policy]
                selected = decision["selected_candidate"]
                axis.add_patch(
                    Rectangle(
                        (column_index - 0.46, row_index - 0.43),
                        0.92,
                        0.86,
                        facecolor=candidate_colors[selected],
                        edgecolor="white",
                        linewidth=1.2,
                    )
                )
                candidate_label = "CPU" if selected == CPU_CANDIDATE else "GPU"
                if policy == "measured_feasible_oracle":
                    annotation = candidate_label
                else:
                    annotation = (
                        f"{candidate_label}\n"
                        f"{_format_regret_percent(decision['normalized_regret'])}"
                    )
                axis.text(
                    column_index,
                    row_index,
                    annotation,
                    color="white",
                    weight="bold",
                    fontsize=8,
                    ha="center",
                    va="center",
                )
        axis.set_xlim(-0.5, len(policies) - 0.5)
        axis.set_ylim(len(instances) - 0.5, -0.5)
        axis.set_xticks(range(len(policies)), [labels[policy] for policy in policies])
        axis.xaxis.tick_top()
        axis.tick_params(axis="x", length=0, pad=7)
        axis.set_yticks(
            range(len(instances)), [instance["display_label"] for instance in instances]
        )
        axis.tick_params(axis="y", length=0)
        for boundary in (4.5, 9.5):
            axis.axhline(boundary, color="#333333", linewidth=1.0)
        for spine in axis.spines.values():
            spine.set_visible(False)
        axis.set_title(
            "Held-out per-instance decisions and normalized regret",
            pad=42,
        )
        axis.text(
            0.5,
            1.035,
            "Cell color/label = selected device; percentage = runtime overhead vs oracle",
            transform=axis.transAxes,
            ha="center",
            va="bottom",
            color=NEUTRAL_GRAY,
            fontsize=8,
        )
        axis.legend(
            handles=(
                Patch(facecolor=COLORBLIND_BLUE, label="CPU (16 threads)"),
                Patch(facecolor=COLORBLIND_ORANGE, label="GPU (L4 default)"),
            ),
            loc="upper center",
            bbox_to_anchor=(0.5, 1.18),
            ncol=2,
            frameon=False,
        )
        figure.text(
            0.5,
            0.025,
            caption,
            ha="center",
            va="bottom",
            fontsize=5.5,
            family="DejaVu Sans Mono",
        )
        description = (
            "Internal held-out multifamily instance decision matrix. Sources: "
            + caption.replace("\n", "; ")
        )
        return _save_figure_if_changed(
            figure, output_path, description=description
        )


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


def _save_figure_if_changed(
    figure: Any, output_path: Path, *, description: str | None = None
) -> bool:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp.svg", dir=output.parent
        )
        os.close(descriptor)
        temporary = Path(name)
        metadata = {
            "Date": None,
            "Creator": "AutoSBD deterministic figure generator",
        }
        if description is not None:
            metadata["Description"] = description
        figure.savefig(
            temporary,
            format="svg",
            metadata=metadata,
        )
        svg_text = temporary.read_text(encoding="utf-8")
        payload = (
            "\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n"
        ).encode("utf-8")
    finally:
        import matplotlib.pyplot as plt

        plt.close(figure)
        if temporary is not None and temporary.exists():
            temporary.unlink()
    changed = _write_bytes_if_changed(output, payload)

    # Also write PDF and 300-DPI PNG previews next to the SVG when possible.
    try:
        # Save PDF
        pdf_path = output.with_suffix(".pdf")
        descriptor, pdf_tmp = tempfile.mkstemp(prefix=f".{pdf_path.name}.", suffix=".tmp.pdf", dir=output.parent)
        os.close(descriptor)
        pdf_tmp_path = Path(pdf_tmp)
        svg_bytes = payload
        try:
            # Use BytesIO SVG -> matplotlib.image for raster PNG; for PDF, matplotlib can save from SVG via figure conversion not trivial.
            # Simpler approach: write the SVG-based PDF using cairosvg if available.
            try:
                import cairosvg

                cairosvg.svg2pdf(bytestring=svg_bytes, write_to=str(pdf_tmp_path))
                pdf_payload = pdf_tmp_path.read_bytes()
                _write_bytes_if_changed(pdf_path, pdf_payload)
            except Exception:
                # If cairosvg not available, skip PDF generation.
                pass
        finally:
            if pdf_tmp_path.exists():
                pdf_tmp_path.unlink()

        # Save PNG at 300 DPI using cairosvg if available
        png_path = output.with_suffix(".png")
        descriptor, png_tmp = tempfile.mkstemp(prefix=f".{png_path.name}.", suffix=".tmp.png", dir=output.parent)
        os.close(descriptor)
        png_tmp_path = Path(png_tmp)
        try:
            try:
                import cairosvg

                cairosvg.svg2png(bytestring=svg_bytes, write_to=str(png_tmp_path), dpi=300)
                png_payload = png_tmp_path.read_bytes()
                _write_bytes_if_changed(png_path, png_payload)
            except Exception:
                # If cairosvg not available, skip PNG generation.
                pass
        finally:
            if png_tmp_path.exists():
                png_tmp_path.unlink()
    except Exception:
        # Non-fatal: do not fail figure generation if preview creation fails.
        pass

    return changed


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


def _load_csv_rows(
    path: Path,
    label: str,
    required_fields: set[str],
) -> list[dict[str, str]]:
    try:
        with Path(path).open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise FigureError(f"{label} has no CSV header: {path}")
            missing = required_fields.difference(reader.fieldnames)
            if missing:
                raise FigureError(
                    f"{label} is missing fields {sorted(missing)}: {path}"
                )
            rows = list(reader)
    except OSError as error:
        raise FigureError(f"cannot load {label}: {path}: {error}") from error
    if any(None in row for row in rows):
        raise FigureError(f"{label} contains rows wider than its header: {path}")
    return rows


def _parse_json_string_list(value: str, label: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise FigureError(f"{label} must be a JSON string list") from error
    if not isinstance(parsed, list) or any(
        not isinstance(item, str) or not item for item in parsed
    ):
        raise FigureError(f"{label} must be a JSON string list")
    return parsed


def _parse_digest_list(value: str, label: str) -> list[str]:
    parsed = _parse_json_string_list(value, label)
    result = [_require_digest(item, label) for item in parsed]
    if len(set(result)) != len(result):
        raise FigureError(f"{label} contains duplicate record IDs")
    return result


def _parse_bool(value: str, label: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise FigureError(f"{label} must be True or False")


def _parse_positive_int(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise FigureError(f"{label} must be a positive integer") from error
    return _require_positive_int(parsed, label)


def _parse_nonnegative_int(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise FigureError(f"{label} must be a nonnegative integer") from error
    return _require_nonnegative_int(parsed, label)


def _parse_positive_number(value: str, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise FigureError(f"{label} must be finite and positive") from error
    return _require_positive_number(parsed, label)


def _parse_nonnegative_number(value: str, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise FigureError(f"{label} must be finite and nonnegative") from error
    return _require_nonnegative_number(parsed, label)


def _parse_fraction(value: str, label: str) -> float:
    result = _parse_nonnegative_number(value, label)
    if result > 1.0:
        raise FigureError(f"{label} must be between zero and one")
    return result


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


def _require_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FigureError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise FigureError(f"{label} must be finite")
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
    "build_cpu_thread_scaling_figure_data",
    "build_inference_overhead_figure_data",
    "build_multifamily_holdout_figure_data",
    "build_multifamily_figure_data",
    "build_numerical_parity_figure_data",
    "build_run_eligibility_figure_data",
    "build_stage4_figure_data",
    "generate_cpu_thread_scaling_figures",
    "generate_inference_overhead_figures",
    "generate_multifamily_figures",
    "generate_multifamily_holdout_figures",
    "generate_numerical_parity_figures",
    "generate_run_eligibility_figures",
    "generate_stage4_figures",
    "sha256_path",
]
