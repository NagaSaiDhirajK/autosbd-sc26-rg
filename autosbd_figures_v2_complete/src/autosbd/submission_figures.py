"""Publication-grade, traceable figures for the AutoSBD SC26 submission.

This module renders only evidence that already exists in tracked AutoSBD
artifacts.  It does not fit models, recompute benchmark results, interpolate a
crossover, or infer missing scientific values.  Every statistical figure emits
its plot-ready CSV and every output is recorded in a SHA-256 manifest.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence


CPU_CANDIDATE = "amd-cpu-16"
GPU_CANDIDATE = "amd-l4-default"
MIB = 1 << 20

FAMILY_ORDER = ("fe4s4", "n2", "h2o")
FAMILY_LABELS = {
    "fe4s4": "Fe₄S₄",
    "n2": "N₂ / 6-31G",
    "h2o": "H₂O / cc-pVDZ",
}

POLICY_ORDER = (
    "fixed_cpu16",
    "fixed_gpu",
    "static_size_threshold",
    "size_only_tree_ablation",
    "autosbd_full_tree",
    "measured_feasible_oracle",
)
POLICY_LABELS = {
    "fixed_cpu16": "Fixed CPU16",
    "fixed_gpu": "Fixed GPU",
    "static_size_threshold": "Training-only threshold",
    "size_only_tree_ablation": "Size-only tree",
    "autosbd_full_tree": "AutoSBD full tree",
    "measured_feasible_oracle": "Measured oracle",
}
LEARNED_POLICY_ORDER = (
    "static_size_threshold",
    "size_only_tree_ablation",
    "autosbd_full_tree",
)

# Okabe-Ito-derived palette.  Backend colors are held constant throughout.
COLORS = {
    "cpu": "#0072B2",
    "gpu": "#D55E00",
    "fixed_cpu16": "#0072B2",
    "fixed_gpu": "#D55E00",
    "static_size_threshold": "#E69F00",
    "size_only_tree_ablation": "#CC79A7",
    "autosbd_full_tree": "#009E73",
    "measured_feasible_oracle": "#222222",
    "neutral": "#6B7280",
    "grid": "#D1D5DB",
    "error": "#B91C1C",
    "correct": "#166534",
    "background": "#FFFFFF",
}

REQUIRED_POLICY_SUMMARY_COLUMNS = {
    "scope",
    "heldout_family_id",
    "policy",
    "requested_instances",
    "valid_instances",
    "invalid_instances",
    "failure_instances",
    "selection_accuracy",
    "within_5pct_oracle_rate",
    "geometric_mean_selected_over_oracle_valid_only",
    "median_normalized_regret_valid_only",
    "p90_normalized_regret_valid_only",
    "maximum_normalized_regret_valid_only",
    "geometric_mean_speedup_vs_fixed_cpu_valid_only",
    "geometric_mean_speedup_vs_fixed_gpu_valid_only",
}

REQUIRED_PREDICTION_COLUMNS = {
    "fold_id",
    "heldout_family_id",
    "policy",
    "family_id",
    "molecule",
    "basis",
    "instance_id",
    "problem_instance",
    "n_configurations",
    "decision_candidate_name",
    "selected_candidate_name",
    "oracle_candidate_names",
    "selected_wall_time_s",
    "oracle_wall_time_s",
    "normalized_runtime",
    "normalized_regret",
    "selection_correct",
    "within_5pct_oracle",
    "valid",
    "failure",
    "invalid_reason",
}


class SubmissionFigureError(ValueError):
    """Raised when source evidence is absent, inconsistent, or ambiguous."""


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        raise SubmissionFigureError(f"{label} must be a regular file: {source}")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SubmissionFigureError(f"cannot read {label}: {source}: {error}") from error
    if not isinstance(value, Mapping):
        raise SubmissionFigureError(f"{label} root must be an object: {source}")
    return value


def _load_csv(path: Path, label: str, required: set[str]) -> list[dict[str, str]]:
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        raise SubmissionFigureError(f"{label} must be a regular file: {source}")
    try:
        with source.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise SubmissionFigureError(f"{label} has no header: {source}")
            missing = required.difference(reader.fieldnames)
            if missing:
                raise SubmissionFigureError(
                    f"{label} is missing required columns: {sorted(missing)}"
                )
            rows = [dict(row) for row in reader]
    except (OSError, UnicodeError, csv.Error) as error:
        raise SubmissionFigureError(f"cannot read {label}: {source}: {error}") from error
    if not rows:
        raise SubmissionFigureError(f"{label} is empty: {source}")
    return rows


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SubmissionFigureError(f"{name} must be a nonempty string")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise SubmissionFigureError(f"{name} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise SubmissionFigureError(f"{name} must be numeric") from error
    if not math.isfinite(result):
        raise SubmissionFigureError(f"{name} must be finite")
    return result


def _positive(value: Any, name: str) -> float:
    result = _number(value, name)
    if result <= 0:
        raise SubmissionFigureError(f"{name} must be positive")
    return result


def _nonnegative(value: Any, name: str) -> float:
    result = _number(value, name)
    if result < 0:
        raise SubmissionFigureError(f"{name} must be nonnegative")
    return result


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise SubmissionFigureError(f"{name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise SubmissionFigureError(f"{name} must be an integer") from error
    if str(result) != str(value).strip() and not isinstance(value, int):
        # Accept canonical floating strings such as 1024.0 only when integral.
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = math.nan
        if not math.isfinite(numeric) or not numeric.is_integer():
            raise SubmissionFigureError(f"{name} must be an integer")
        result = int(numeric)
    if result < minimum:
        raise SubmissionFigureError(f"{name} must be >= {minimum}")
    return result


def _bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise SubmissionFigureError(f"{name} must be true or false")


def _candidate_label(candidate: str) -> str:
    if candidate == CPU_CANDIDATE:
        return "CPU16"
    if candidate == GPU_CANDIDATE:
        return "L4 GPU"
    raise SubmissionFigureError(f"unexpected candidate: {candidate}")


def _candidate_backend(candidate: str) -> str:
    if candidate == CPU_CANDIDATE:
        return "cpu"
    if candidate == GPU_CANDIDATE:
        return "gpu"
    raise SubmissionFigureError(f"unexpected candidate: {candidate}")


def _family_label(family: str) -> str:
    try:
        return FAMILY_LABELS[family]
    except KeyError as error:
        raise SubmissionFigureError(f"unexpected family: {family}") from error


def _json_list(value: str, name: str) -> list[Any]:
    try:
        result = json.loads(value)
    except json.JSONDecodeError as error:
        raise SubmissionFigureError(f"{name} must contain JSON") from error
    if not isinstance(result, list):
        raise SubmissionFigureError(f"{name} must contain a JSON list")
    return result



def _style_context() -> dict[str, Any]:
    """Compact, poster-ready styling with no in-figure titles."""
    return {
        "font.family": "DejaVu Sans",
        "font.size": 11.0,
        "axes.titlesize": 12.0,
        "axes.titleweight": "semibold",
        "axes.labelsize": 11.0,
        "axes.labelcolor": "#111827",
        "axes.edgecolor": "#9CA3AF",
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": "#374151",
        "ytick.color": "#374151",
        "text.color": "#111827",
        "legend.frameon": False,
        "legend.fontsize": 9.5,
        "grid.color": COLORS["grid"],
        "grid.linewidth": 0.7,
        "grid.alpha": 0.45,
        "figure.facecolor": COLORS["background"],
        "axes.facecolor": COLORS["background"],
        "savefig.facecolor": COLORS["background"],
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "svg.hashsalt": "autosbd-sc26-submission-figures-v2",
    }

def _atomic_write(path: Path, payload: bytes) -> bool:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() == payload:
        return False
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    return True


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bool:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        payload: dict[str, Any] = {}
        for field in fields:
            value = row.get(field)
            if isinstance(value, (list, dict)):
                payload[field] = json.dumps(value, sort_keys=True, separators=(",", ":"))
            else:
                payload[field] = value
        writer.writerow(payload)
    return _atomic_write(path, buffer.getvalue().encode("utf-8"))


def _save_figure_bundle(figure: Any, stem: Path, *, description: str) -> dict[str, bool]:
    import matplotlib.pyplot as plt

    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, bool] = {}
    metadata = {
        "Title": description,
        "Author": "AutoSBD",
        "Subject": "SC26 ACM SRC evidence figure",
        "Creator": "AutoSBD deterministic submission figure generator",
        "CreationDate": None,
        "ModDate": None,
    }
    for suffix in ("svg", "pdf", "png"):
        buffer = io.BytesIO()
        kwargs: dict[str, Any] = {
            "format": suffix,
            "bbox_inches": "tight",
            "pad_inches": 0.08,
            "facecolor": COLORS["background"],
        }
        if suffix == "png":
            kwargs.update(dpi=320, metadata={"Software": metadata["Creator"]})
        elif suffix == "pdf":
            kwargs.update(metadata=metadata)
        elif suffix == "svg":
            kwargs.update(metadata={"Title": description, "Creator": metadata["Creator"]})
        figure.savefig(buffer, **kwargs)
        destination = stem.with_suffix(f".{suffix}")
        outputs[str(destination)] = _atomic_write(destination, buffer.getvalue())
    plt.close(figure)
    return outputs


def _size_map(aggregate: Mapping[str, Any], label: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in aggregate.get("rows", []):
        if not isinstance(row, Mapping):
            continue
        instance = row.get("problem_instance")
        features = row.get("features")
        if not isinstance(instance, str) or not isinstance(features, Mapping):
            continue
        size = features.get("n_configurations")
        if size is None:
            continue
        parsed = _integer(size, f"{label} n_configurations", minimum=1)
        previous = result.setdefault(instance, parsed)
        if previous != parsed:
            raise SubmissionFigureError(
                f"{label} has inconsistent n_configurations for {instance}"
            )
    return result


def extract_runtime_rows(
    aggregate_path: Path,
    *,
    fallback_family: str | None = None,
    fallback_molecule: str | None = None,
    fallback_basis: str | None = None,
) -> list[dict[str, Any]]:
    """Extract explicit candidate medians and IQRs from one final aggregate."""

    aggregate = _load_json(aggregate_path, "timing aggregate")
    if aggregate.get("analysis_type") != "autosbd_timing_aggregation":
        raise SubmissionFigureError(f"unexpected aggregate type: {aggregate_path}")
    groups = aggregate.get("candidate_groups")
    if not isinstance(groups, list) or not groups:
        raise SubmissionFigureError(f"aggregate lacks candidate_groups: {aggregate_path}")
    sizes = _size_map(aggregate, str(aggregate_path))
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for group in groups:
        if not isinstance(group, Mapping):
            raise SubmissionFigureError("candidate group must be an object")
        candidate = group.get("candidate")
        wall = group.get("wall_time_s")
        solver = group.get("solver_time_s")
        if not isinstance(candidate, Mapping) or not isinstance(wall, Mapping):
            raise SubmissionFigureError("candidate group lacks candidate/wall summary")
        if not isinstance(solver, Mapping):
            raise SubmissionFigureError("candidate group lacks solver summary")
        candidate_name = _text(candidate.get("name"), "candidate name")
        _candidate_backend(candidate_name)
        instance = _text(group.get("problem_instance"), "problem_instance")
        family = group.get("family_id", fallback_family)
        molecule = group.get("molecule", fallback_molecule)
        basis = group.get("basis", fallback_basis)
        family = _text(family, "family_id")
        _family_label(family)
        molecule = _text(molecule, "molecule")
        if basis is not None and not isinstance(basis, str):
            raise SubmissionFigureError("basis must be text or null")
        n_configurations = group.get("n_configurations", sizes.get(instance))
        if n_configurations is None:
            raise SubmissionFigureError(
                f"no explicit n_configurations found for {family}/{instance}"
            )
        n_configurations = _integer(
            n_configurations, f"n_configurations for {family}/{instance}", minimum=1
        )
        key = (family, instance, candidate_name)
        if key in seen:
            raise SubmissionFigureError(f"duplicate candidate group: {key}")
        seen.add(key)
        q1 = _positive(wall.get("q1"), "wall q1")
        median = _positive(wall.get("median"), "wall median")
        q3 = _positive(wall.get("q3"), "wall q3")
        if not q1 <= median <= q3:
            raise SubmissionFigureError(f"invalid wall quartiles for {key}")
        rows.append(
            {
                "family_id": family,
                "family_label": _family_label(family),
                "molecule": molecule,
                "basis": basis,
                "problem_instance": instance,
                "n_configurations": n_configurations,
                "candidate": candidate_name,
                "backend": _candidate_backend(candidate_name),
                "count": _integer(wall.get("count"), "wall count", minimum=1),
                "wall_q1_s": q1,
                "wall_median_s": median,
                "wall_q3_s": q3,
                "wall_iqr_s": _nonnegative(wall.get("iqr"), "wall iqr"),
                "solver_median_s": _positive(solver.get("median"), "solver median"),
                "record_ids": list(group.get("record_ids", [])),
            }
        )
    expected = {
        (family, instance, candidate)
        for family in {row["family_id"] for row in rows}
        for instance in {row["problem_instance"] for row in rows if row["family_id"] == family}
        for candidate in (CPU_CANDIDATE, GPU_CANDIDATE)
    }
    if seen != expected:
        raise SubmissionFigureError(
            f"aggregate is not a complete CPU/GPU matrix: {aggregate_path}"
        )
    return sorted(
        rows,
        key=lambda row: (
            FAMILY_ORDER.index(row["family_id"]),
            row["n_configurations"],
            row["candidate"],
        ),
    )


def load_policy_summary(path: Path) -> list[dict[str, Any]]:
    rows = _load_csv(path, "multifamily policy summary", REQUIRED_POLICY_SUMMARY_COLUMNS)
    parsed: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        scope = _text(row["scope"], "scope")
        family = row["heldout_family_id"].strip()
        policy = _text(row["policy"], "policy")
        if policy not in POLICY_ORDER:
            raise SubmissionFigureError(f"unexpected policy: {policy}")
        if scope == "pooled":
            if family:
                raise SubmissionFigureError("pooled policy row must not name a family")
        elif scope == "heldout_family":
            _family_label(family)
        else:
            raise SubmissionFigureError(f"unexpected policy-summary scope: {scope}")
        key = (scope, family, policy)
        if key in seen:
            raise SubmissionFigureError(f"duplicate policy-summary row: {key}")
        seen.add(key)
        parsed.append(
            {
                "scope": scope,
                "heldout_family_id": family,
                "policy": policy,
                "requested_instances": _integer(row["requested_instances"], "requested_instances", minimum=1),
                "valid_instances": _integer(row["valid_instances"], "valid_instances", minimum=0),
                "invalid_instances": _integer(row["invalid_instances"], "invalid_instances", minimum=0),
                "failure_instances": _integer(row["failure_instances"], "failure_instances", minimum=0),
                "selection_accuracy": _nonnegative(row["selection_accuracy"], "selection_accuracy"),
                "within_5pct_oracle_rate": _nonnegative(row["within_5pct_oracle_rate"], "within_5pct_oracle_rate"),
                "geometric_mean_selected_over_oracle": _positive(
                    row["geometric_mean_selected_over_oracle_valid_only"],
                    "geometric_mean_selected_over_oracle_valid_only",
                ),
                "median_regret": _nonnegative(
                    row["median_normalized_regret_valid_only"], "median regret"
                ),
                "p90_regret": _nonnegative(
                    row["p90_normalized_regret_valid_only"], "p90 regret"
                ),
                "maximum_regret": _nonnegative(
                    row["maximum_normalized_regret_valid_only"], "maximum regret"
                ),
                "speedup_vs_cpu": _positive(
                    row["geometric_mean_speedup_vs_fixed_cpu_valid_only"],
                    "speedup vs CPU",
                ),
                "speedup_vs_gpu": _positive(
                    row["geometric_mean_speedup_vs_fixed_gpu_valid_only"],
                    "speedup vs GPU",
                ),
            }
        )
    expected = 6 + 3 * 6
    if len(parsed) != expected:
        raise SubmissionFigureError(
            f"expected {expected} pooled/held-out policy rows, found {len(parsed)}"
        )
    return parsed


def load_predictions(path: Path) -> list[dict[str, Any]]:
    rows = _load_csv(path, "multifamily policy predictions", REQUIRED_PREDICTION_COLUMNS)
    parsed: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        family = _text(row["family_id"], "family_id")
        _family_label(family)
        heldout = _text(row["heldout_family_id"], "heldout_family_id")
        if family != heldout:
            raise SubmissionFigureError(
                f"prediction family {family} differs from held-out family {heldout}"
            )
        policy = _text(row["policy"], "policy")
        if policy not in POLICY_ORDER:
            raise SubmissionFigureError(f"unexpected prediction policy: {policy}")
        instance_id = _text(row["instance_id"], "instance_id")
        key = (family, instance_id, policy)
        if key in seen:
            raise SubmissionFigureError(f"duplicate prediction row: {key}")
        seen.add(key)
        selected = _text(row["selected_candidate_name"], "selected candidate")
        _candidate_backend(selected)
        oracle_names = _json_list(row["oracle_candidate_names"], "oracle_candidate_names")
        if not oracle_names or any(name not in (CPU_CANDIDATE, GPU_CANDIDATE) for name in oracle_names):
            raise SubmissionFigureError(f"invalid oracle candidates for {instance_id}")
        valid = _bool(row["valid"], "valid")
        failure = _bool(row["failure"], "failure")
        if not valid or failure:
            raise SubmissionFigureError(
                f"submission figure inputs require valid, non-failing predictions: {key}"
            )
        parsed.append(
            {
                "fold_id": _text(row["fold_id"], "fold_id"),
                "family_id": family,
                "family_label": _family_label(family),
                "policy": policy,
                "instance_id": instance_id,
                "problem_instance": _text(row["problem_instance"], "problem_instance"),
                "n_configurations": _integer(row["n_configurations"], "n_configurations", minimum=1),
                "selected_candidate": selected,
                "selected_backend": _candidate_backend(selected),
                "oracle_candidates": oracle_names,
                "oracle_backend": _candidate_backend(oracle_names[0]),
                "selected_wall_time_s": _positive(row["selected_wall_time_s"], "selected wall time"),
                "oracle_wall_time_s": _positive(row["oracle_wall_time_s"], "oracle wall time"),
                "normalized_runtime": _positive(row["normalized_runtime"], "normalized runtime"),
                "normalized_regret": _nonnegative(row["normalized_regret"], "normalized regret"),
                "selection_correct": _bool(row["selection_correct"], "selection_correct"),
                "within_5pct_oracle": _bool(row["within_5pct_oracle"], "within_5pct_oracle"),
            }
        )
    if len(parsed) != 90:
        raise SubmissionFigureError(f"expected 90 held-out predictions, found {len(parsed)}")
    return sorted(
        parsed,
        key=lambda row: (
            FAMILY_ORDER.index(row["family_id"]),
            row["n_configurations"],
            POLICY_ORDER.index(row["policy"]),
        ),
    )


def load_deployment_tree(path: Path) -> Mapping[str, Any]:
    models = _load_json(path, "multifamily models")
    scope = models.get("deployment_model_scope")
    if not isinstance(scope, Mapping):
        raise SubmissionFigureError("models artifact lacks deployment_model_scope")
    if scope.get("used_for_heldout_metrics") is not False:
        raise SubmissionFigureError("deployment model must be excluded from held-out metrics")
    deployment = models.get("deployment_models")
    if not isinstance(deployment, Mapping):
        raise SubmissionFigureError("models artifact lacks deployment_models")
    model = deployment.get("autosbd_full_tree")
    if not isinstance(model, Mapping):
        raise SubmissionFigureError("models artifact lacks AutoSBD deployment tree")
    tree = model.get("tree")
    nodes = tree.get("nodes") if isinstance(tree, Mapping) else None
    if not isinstance(nodes, list) or not nodes:
        raise SubmissionFigureError("deployment tree lacks nodes")
    node_ids: set[int] = set()
    for node in nodes:
        if not isinstance(node, Mapping):
            raise SubmissionFigureError("tree node must be an object")
        node_id = _integer(node.get("node_id"), "tree node_id", minimum=0)
        if node_id in node_ids:
            raise SubmissionFigureError(f"duplicate tree node_id: {node_id}")
        node_ids.add(node_id)
    if 0 not in node_ids:
        raise SubmissionFigureError("deployment tree lacks root node 0")
    return model


def load_inference_overhead(path: Path) -> list[dict[str, Any]]:
    required = {
        "measurement",
        "minimum_us",
        "median_us",
        "p90_us",
        "p95_us",
        "maximum_us",
        "iteration_count",
        "hot_median_percent_of_shortest_sbd_runtime",
    }
    rows = _load_csv(path, "multifamily inference overhead", required)
    parsed: list[dict[str, Any]] = []
    for row in rows:
        measurement = _text(row["measurement"], "measurement")
        parsed.append(
            {
                "measurement": measurement,
                "minimum_us": _positive(row["minimum_us"], "minimum_us"),
                "median_us": _positive(row["median_us"], "median_us"),
                "p90_us": _positive(row["p90_us"], "p90_us"),
                "p95_us": _positive(row["p95_us"], "p95_us"),
                "maximum_us": _positive(row["maximum_us"], "maximum_us"),
                "iteration_count": _integer(row["iteration_count"], "iteration_count", minimum=1),
                "hot_percent_of_shortest_sbd": (
                    _number(
                        row["hot_median_percent_of_shortest_sbd_runtime"],
                        "hot median percent of shortest SBD runtime",
                    )
                    if row["hot_median_percent_of_shortest_sbd_runtime"].strip()
                    else None
                ),
            }
        )
    expected = {"hot_selection", "cold_load_plus_selection"}
    if {row["measurement"] for row in parsed} != expected:
        raise SubmissionFigureError("inference overhead must contain hot and object-cold paths")
    return parsed


def extract_gpu_memory_rows(
    runtime_rows: Sequence[Mapping[str, Any]], raw_dir: Path
) -> list[dict[str, Any]]:
    """Load measured GPU memory evidence named by the final aggregates.

    The aggregate supplies the exact final record IDs and family/size mapping.
    Raw records supply measured peak allocation, source-derived guard, and the
    contemporaneous admission cap. No filesystem-wide record discovery is used.
    """

    raw_directory = Path(raw_dir)
    if not raw_directory.is_dir() or raw_directory.is_symlink():
        raise SubmissionFigureError(f"raw directory must be a regular directory: {raw_directory}")
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in runtime_rows:
        if group["candidate"] != GPU_CANDIDATE:
            continue
        family = _text(group["family_id"], "family_id")
        instance = _text(group["problem_instance"], "problem_instance")
        size = _integer(group["n_configurations"], "n_configurations", minimum=1)
        record_ids = group.get("record_ids")
        if not isinstance(record_ids, list) or not record_ids:
            raise SubmissionFigureError(f"GPU aggregate row lacks record IDs: {family}/{instance}")
        for trial_id_value in record_ids:
            trial_id = _text(trial_id_value, "trial_id")
            if trial_id in seen:
                raise SubmissionFigureError(f"GPU record reused across final groups: {trial_id}")
            seen.add(trial_id)
            raw_path = raw_directory / f"{trial_id}.json"
            raw = _load_json(raw_path, f"raw GPU record {trial_id}")
            if raw.get("trial_id") != trial_id:
                raise SubmissionFigureError(f"raw trial ID mismatch: {raw_path}")
            if not (
                raw.get("backend") == "gpu"
                and raw.get("status") == "success"
                and raw.get("correct") is True
                and raw.get("timing_eligible") is True
                and raw.get("warmup_or_measured") == "measured"
                and raw.get("timeout") is False
                and raw.get("oom") is False
                and raw.get("skip_reason") is None
            ):
                raise SubmissionFigureError(f"final GPU record is not eligible: {trial_id}")
            estimate = raw.get("source_memory_estimate")
            preflight = raw.get("preflight")
            if not isinstance(estimate, Mapping) or not isinstance(preflight, Mapping):
                raise SubmissionFigureError(f"GPU record lacks memory metadata: {trial_id}")
            peak = _positive(raw.get("peak_gpu_memory_mb"), "peak_gpu_memory_mb")
            guard_bytes = _integer(estimate.get("gpu_guard_bytes"), "gpu_guard_bytes", minimum=1)
            cap_bytes = _integer(preflight.get("gpu_memory_cap_bytes"), "gpu_memory_cap_bytes", minimum=1)
            parsed.append(
                {
                    "family_id": family,
                    "problem_instance": instance,
                    "n_configurations": size,
                    "trial_id": trial_id,
                    "raw_sha256": sha256_path(raw_path),
                    "peak_gpu_memory_mib": peak,
                    "estimated_gpu_guard_mib": guard_bytes / MIB,
                    "gpu_admission_cap_mib": cap_bytes / MIB,
                }
            )
    if not parsed:
        raise SubmissionFigureError("final aggregates contain no measured GPU records")
    return sorted(
        parsed,
        key=lambda row: (
            FAMILY_ORDER.index(row["family_id"]),
            row["n_configurations"],
            row["trial_id"],
        ),
    )


def load_memory_rows(path: Path) -> list[dict[str, Any]]:
    required = {
        "problem_instance",
        "n_configurations",
        "repetition",
        "peak_gpu_memory_mib",
        "estimated_gpu_guard_mib",
        "gpu_admission_cap_mib",
        "status",
        "correct",
        "timeout",
        "oom",
        "skip_reason",
    }
    rows = _load_csv(path, "GPU memory figure data", required)
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if row["status"] != "success" or not _bool(row["correct"], "correct"):
            raise SubmissionFigureError("memory figure data contains non-success record")
        if _bool(row["timeout"], "timeout") or _bool(row["oom"], "oom"):
            raise SubmissionFigureError("memory figure data contains timeout/OOM record")
        if row["skip_reason"].strip():
            raise SubmissionFigureError("memory figure data contains skipped record")
        parsed.append(
            {
                "problem_instance": _text(row["problem_instance"], "problem_instance"),
                "n_configurations": _integer(row["n_configurations"], "n_configurations", minimum=1),
                "repetition": _integer(row["repetition"], "repetition", minimum=0),
                "peak_gpu_memory_mib": _positive(row["peak_gpu_memory_mib"], "peak GPU memory"),
                "estimated_gpu_guard_mib": _positive(row["estimated_gpu_guard_mib"], "GPU guard"),
                "gpu_admission_cap_mib": _positive(row["gpu_admission_cap_mib"], "GPU cap"),
            }
        )
    return parsed


def load_energy_error_rows(path: Path) -> list[dict[str, Any]]:
    required = {
        "problem_instance",
        "family_id",
        "backend",
        "relative_error",
    }
    rows = _load_csv(path, "numerical parity data", required)
    parsed: list[dict[str, Any]] = []
    for row in rows:
        family = row["family_id"].strip()
        instance = _text(row["problem_instance"], "problem_instance")
        if not family:
            if instance.startswith("fe4s4-prefix-"):
                family = "fe4s4"
            else:
                continue
        if family not in FAMILY_ORDER:
            continue
        backend = _text(row["backend"], "backend")
        if backend not in ("cpu", "gpu"):
            continue
        parsed.append(
            {
                "family_id": family,
                "backend": backend,
                "relative_error": abs(_number(row["relative_error"], "relative_error")),
            }
        )
    if not parsed:
        raise SubmissionFigureError("numerical parity data contains no recognized rows")
    return parsed



def render_architecture(output_stem: Path) -> dict[str, bool]:
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    with mpl.rc_context(_style_context()):
        figure, axis = plt.subplots(figsize=(13.8, 3.7), constrained_layout=True)
        axis.set_xlim(0, 14.0)
        axis.set_ylim(0, 3.7)
        axis.axis("off")

        def stage(x: float, w: float, number: str, heading: str, detail: str, edge: str) -> None:
            patch = FancyBboxPatch(
                (x, 1.05), w, 1.75,
                boxstyle="round,pad=0.035,rounding_size=0.08",
                linewidth=1.25,
                edgecolor=edge,
                facecolor="#FFFFFF",
            )
            axis.add_patch(patch)
            axis.text(x + 0.16, 2.57, number, fontsize=16, fontweight="bold", color=edge, va="top")
            axis.text(x + 0.52, 2.52, heading, fontsize=11.2, fontweight="semibold", va="top")
            axis.text(x + 0.18, 2.02, detail, fontsize=9.2, color="#4B5563", va="top", linespacing=1.28)

        def arrow(x1: float, x2: float, y: float = 1.92) -> None:
            axis.add_patch(FancyArrowPatch(
                (x1, y), (x2, y), arrowstyle="-|>", mutation_scale=13,
                linewidth=1.15, color="#9CA3AF"
            ))

        stage(0.15, 2.05, "1", "Read workload", "FCIDUMP\nα/β determinants", "#4F46E5")
        stage(2.55, 2.25, "2", "Extract features", "size + work proxy\nconnectivity + cache", "#7C3AED")
        stage(5.15, 2.10, "3", "Check feasibility", "host/GPU memory\nfail-closed admission", "#B45309")
        stage(7.60, 2.25, "4", "Predict runtime", "CPU16 and L4\npre-execution only", COLORS["autosbd_full_tree"])
        stage(10.20, 3.55, "5", "Run selected backend", "same official AMD-HPC solver\nimmutable hash-linked record", "#374151")
        arrow(2.20, 2.55)
        arrow(4.80, 5.15)
        arrow(7.25, 7.60)
        arrow(9.85, 10.20)

        # Direct backend split inside the final stage.
        axis.text(11.00, 1.39, "CPU16", fontsize=10.4, fontweight="semibold", color=COLORS["cpu"])
        axis.text(12.32, 1.39, "or", fontsize=9.0, color="#6B7280", ha="center")
        axis.text(12.73, 1.39, "L4 GPU", fontsize=10.4, fontweight="semibold", color=COLORS["gpu"])
        axis.plot([10.98, 11.75], [1.27, 1.27], color=COLORS["cpu"], linewidth=3.0, solid_capstyle="round")
        axis.plot([12.72, 13.55], [1.27, 1.27], color=COLORS["gpu"], linewidth=3.0, solid_capstyle="round")
        axis.text(
            7.0, 0.42,
            "No circuit execution, solver modification, or post-execution feature is used in the decision.",
            ha="center", fontsize=9.0, color="#4B5563"
        )
        return _save_figure_bundle(
            figure,
            output_stem,
            description="AutoSBD end-to-end architecture using only implemented pipeline components",
        )


def render_runtime_scaling(runtime_rows: Sequence[Mapping[str, Any]], output_stem: Path) -> dict[str, bool]:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    with mpl.rc_context(_style_context()):
        figure, axes = plt.subplots(1, 3, figsize=(13.8, 4.15), sharey=True, constrained_layout=True)
        for axis, family in zip(axes, FAMILY_ORDER):
            family_rows = [row for row in runtime_rows if row["family_id"] == family]
            if len(family_rows) != 10:
                raise SubmissionFigureError(f"runtime figure requires 10 rows for {family}")
            by_candidate = {
                candidate: sorted(
                    [row for row in family_rows if row["candidate"] == candidate],
                    key=lambda row: row["n_configurations"],
                )
                for candidate in (CPU_CANDIDATE, GPU_CANDIDATE)
            }
            for candidate, marker in ((CPU_CANDIDATE, "o"), (GPU_CANDIDATE, "s")):
                rows = by_candidate[candidate]
                x = [row["n_configurations"] for row in rows]
                median = [row["wall_median_s"] for row in rows]
                q1 = [row["wall_q1_s"] for row in rows]
                q3 = [row["wall_q3_s"] for row in rows]
                backend = _candidate_backend(candidate)
                axis.fill_between(x, q1, q3, color=COLORS[backend], alpha=0.13, linewidth=0)
                axis.plot(
                    x, median, marker=marker, markersize=6.2, linewidth=2.1,
                    color=COLORS[backend], zorder=3
                )
                axis.annotate(
                    _candidate_label(candidate),
                    xy=(x[-1], median[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9.0, fontweight="semibold", color=COLORS[backend]
                )
            cpu_rows = by_candidate[CPU_CANDIDATE]
            gpu_rows = by_candidate[GPU_CANDIDATE]
            winners = [
                CPU_CANDIDATE if cpu["wall_median_s"] <= gpu["wall_median_s"] else GPU_CANDIDATE
                for cpu, gpu in zip(cpu_rows, gpu_rows)
            ]
            for index in range(len(winners) - 1):
                if winners[index] == winners[index + 1]:
                    continue
                lower = cpu_rows[index]["n_configurations"]
                upper = cpu_rows[index + 1]["n_configurations"]
                axis.axvspan(lower, upper, color="#9CA3AF", alpha=0.10, zorder=0)
                axis.text(
                    math.sqrt(lower * upper), 0.94, "winner flips",
                    transform=axis.get_xaxis_transform(), ha="center", va="top",
                    fontsize=7.8, color="#6B7280"
                )
            axis.set_xscale("log")
            axis.set_yscale("log")
            axis.grid(True, which="major")
            axis.grid(True, which="minor", alpha=0.15)
            axis.set_xlabel("Configurations")
            axis.text(
                0.03, 0.97, _family_label(family), transform=axis.transAxes,
                ha="left", va="top", fontsize=11.2, fontweight="semibold"
            )
            axis.margins(x=0.08, y=0.12)
        axes[0].set_ylabel("Median end-to-end runtime (s)")
        figure.text(
            0.995, 0.01, "Median line · IQR band · measured points only",
            ha="right", fontsize=8.2, color="#6B7280"
        )
        return _save_figure_bundle(
            figure,
            output_stem,
            description="Cross-family CPU16 and NVIDIA L4 repeated runtime scaling with IQR",
        )


def render_pooled_policy_performance(summary_rows: Sequence[Mapping[str, Any]], output_stem: Path) -> dict[str, bool]:
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    pooled = {row["policy"]: row for row in summary_rows if row["scope"] == "pooled"}
    if set(pooled) != set(POLICY_ORDER):
        raise SubmissionFigureError("pooled policy summary is incomplete")
    order = (
        "measured_feasible_oracle",
        "autosbd_full_tree",
        "static_size_threshold",
        "fixed_gpu",
        "size_only_tree_ablation",
        "fixed_cpu16",
    )
    labels = [POLICY_LABELS[policy] for policy in order]
    overhead = [(pooled[policy]["geometric_mean_selected_over_oracle"] - 1.0) * 100.0 for policy in order]
    accuracy = [pooled[policy]["selection_accuracy"] * 100.0 for policy in order]
    colors = [COLORS[policy] for policy in order]
    autosbd = pooled["autosbd_full_tree"]
    time_reduction = (1.0 - 1.0 / autosbd["speedup_vs_gpu"]) * 100.0
    saved_per_1000 = 10.0 * time_reduction

    with mpl.rc_context(_style_context()):
        figure = plt.figure(figsize=(13.4, 4.75), constrained_layout=True)
        grid = figure.add_gridspec(1, 3, width_ratios=(1.48, 1.05, 0.95))
        left = figure.add_subplot(grid[0, 0])
        middle = figure.add_subplot(grid[0, 1])
        right = figure.add_subplot(grid[0, 2])
        y = list(range(len(order)))

        left.hlines(y, 0, overhead, color="#D1D5DB", linewidth=3.0, zorder=1)
        left.scatter(overhead, y, s=92, color=colors, edgecolor="white", linewidth=1.0, zorder=3)
        for yi, value, policy in zip(y, overhead, order):
            left.text(
                value + max(overhead) * 0.02 + 0.25, yi, f"{value:.1f}%",
                va="center", fontsize=9.2,
                fontweight="bold" if policy == "autosbd_full_tree" else "normal"
            )
        left.set_yticks(y, labels)
        left.invert_yaxis()
        left.set_xlabel("Runtime overhead vs measured oracle (%)  ↓")
        left.grid(True, axis="x")
        left.grid(False, axis="y")
        left.axvline(0, color="#4B5563", linewidth=0.9)

        middle.barh(y, accuracy, color=colors, height=0.58, edgecolor="white", linewidth=0.8)
        for yi, value, policy in zip(y, accuracy, order):
            correct = int(round(pooled[policy]["selection_accuracy"] * pooled[policy]["requested_instances"]))
            middle.text(
                min(value - 2.5, 97.0), yi, f"{correct}/15",
                va="center", ha="right", fontsize=9.2,
                fontweight="bold" if policy == "autosbd_full_tree" else "normal",
                color="white" if value > 55 else "#111827"
            )
        middle.set_yticks(y, [""] * len(y))
        middle.invert_yaxis()
        middle.set_xlim(0, 102)
        middle.set_xlabel("Exact backend selections  ↑")
        middle.grid(True, axis="x")
        middle.grid(False, axis="y")

        right.set_xlim(0, 1)
        right.set_ylim(0, 1)
        right.axis("off")
        card = FancyBboxPatch(
            (0.04, 0.12), 0.92, 0.76,
            boxstyle="round,pad=0.035,rounding_size=0.04",
            linewidth=1.3, edgecolor=COLORS["autosbd_full_tree"], facecolor="#FFFFFF"
        )
        right.add_patch(card)
        right.text(0.50, 0.73, f"{saved_per_1000:.1f}", ha="center", va="center", fontsize=31, fontweight="bold", color=COLORS["autosbd_full_tree"])
        right.text(0.50, 0.57, "hours recovered", ha="center", fontsize=12.2, fontweight="semibold")
        right.text(0.50, 0.45, "per 1,000 fixed-GPU hours", ha="center", fontsize=10.0, color="#374151")
        right.text(0.50, 0.29, f"Measured portfolio reduction: {time_reduction:.2f}%", ha="center", fontsize=9.1, color="#4B5563")
        right.text(0.50, 0.19, "same workload mix + same hardware", ha="center", fontsize=8.2, color="#6B7280")

        return _save_figure_bundle(
            figure,
            output_stem,
            description="Pooled held-out policy efficiency, accuracy, and measured portfolio impact",
        )


def render_family_generalization(summary_rows: Sequence[Mapping[str, Any]], output_stem: Path) -> dict[str, bool]:
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    import numpy as np

    selected = [
        row for row in summary_rows
        if row["scope"] == "heldout_family" and row["policy"] in LEARNED_POLICY_ORDER
    ]
    lookup = {(row["heldout_family_id"], row["policy"]): row for row in selected}
    if len(lookup) != 9:
        raise SubmissionFigureError("held-out family learned-policy matrix is incomplete")
    overhead = np.array([
        [(lookup[(family, policy)]["geometric_mean_selected_over_oracle"] - 1.0) * 100.0 for family in FAMILY_ORDER]
        for policy in LEARNED_POLICY_ORDER
    ])

    with mpl.rc_context(_style_context()):
        figure, axis = plt.subplots(figsize=(9.6, 4.3), constrained_layout=True)
        vmax = max(8.0, float(overhead.max()))
        image = axis.imshow(overhead, aspect="auto", cmap="magma_r", vmin=0, vmax=vmax)
        axis.set_xticks(range(3), [_family_label(family) for family in FAMILY_ORDER])
        axis.set_yticks(range(3), [POLICY_LABELS[policy] for policy in LEARNED_POLICY_ORDER])
        axis.tick_params(axis="both", length=0, pad=9)
        for row_index, policy in enumerate(LEARNED_POLICY_ORDER):
            for column_index, family_id in enumerate(FAMILY_ORDER):
                row = lookup[(family_id, policy)]
                correct = int(round(row["selection_accuracy"] * row["requested_instances"]))
                value = overhead[row_index, column_index]
                color = "white" if value > vmax * 0.45 else "#111827"
                axis.text(column_index, row_index - 0.08, f"{correct}/5 correct", ha="center", va="center", color=color, fontsize=10.2, fontweight="bold")
                axis.text(column_index, row_index + 0.19, f"{value:.1f}% overhead", ha="center", va="center", color=color, fontsize=8.7)
        for edge in range(4):
            axis.axhline(edge - 0.5, color="white", linewidth=2)
            axis.axvline(edge - 0.5, color="white", linewidth=2)
        cbar = figure.colorbar(image, ax=axis, fraction=0.035, pad=0.03)
        cbar.set_label("Runtime overhead vs oracle (%)  ↓")
        axis.set_xlabel("Completely held-out chemistry family")
        return _save_figure_bundle(
            figure,
            output_stem,
            description="Per-family held-out exact selections and runtime overhead",
        )

def _instance_order(predictions: Sequence[Mapping[str, Any]]) -> list[tuple[str, str, int]]:
    unique = {
        (row["family_id"], row["instance_id"], row["n_configurations"])
        for row in predictions
    }
    return sorted(unique, key=lambda item: (FAMILY_ORDER.index(item[0]), item[2], item[1]))



def render_decision_map(predictions: Sequence[Mapping[str, Any]], output_stem: Path) -> dict[str, bool]:
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    policies = ("measured_feasible_oracle",) + LEARNED_POLICY_ORDER
    instances = _instance_order(predictions)
    lookup = {(row["policy"], row["instance_id"]): row for row in predictions}
    if len(instances) != 15:
        raise SubmissionFigureError("decision map requires 15 distinct instances")
    for policy in policies:
        for _family, instance_id, _size in instances:
            if (policy, instance_id) not in lookup:
                raise SubmissionFigureError(f"decision map is missing {policy}/{instance_id}")

    with mpl.rc_context(_style_context()):
        figure, axis = plt.subplots(figsize=(13.5, 4.0), constrained_layout=True)
        for y, policy in enumerate(policies):
            for x, (_family, instance_id, _size) in enumerate(instances):
                row = lookup[(policy, instance_id)]
                backend = row["selected_backend"]
                edge = COLORS["error"] if policy != "measured_feasible_oracle" and not row["selection_correct"] else "white"
                linewidth = 2.4 if edge == COLORS["error"] else 1.2
                axis.add_patch(Rectangle(
                    (x - 0.46, y - 0.39), 0.92, 0.78,
                    facecolor=COLORS[backend], edgecolor=edge, linewidth=linewidth
                ))
                axis.text(x, y, "CPU" if backend == "cpu" else "GPU", ha="center", va="center", color="white", fontsize=8.2, fontweight="bold")
        for separator in (4.5, 9.5):
            axis.axvline(separator, color="#9CA3AF", linewidth=1.0)
        axis.set_xlim(-0.6, len(instances) - 0.4)
        axis.set_ylim(len(policies) - 0.55, -0.75)
        axis.set_yticks(range(len(policies)), [POLICY_LABELS[policy] for policy in policies])
        axis.set_xticks(range(len(instances)), [f"{size:,}" for _, _, size in instances], rotation=45, ha="right")
        axis.set_xlabel("Configurations")
        axis.grid(False)
        for spine in axis.spines.values():
            spine.set_visible(False)
        for start, end, family_id in ((0, 4, "fe4s4"), (5, 9, "n2"), (10, 14, "h2o")):
            axis.text((start + end) / 2, -0.66, _family_label(family_id), ha="center", va="bottom", fontsize=10.6, fontweight="semibold", clip_on=False)
        legend = [
            Patch(facecolor=COLORS["cpu"], label="CPU16"),
            Patch(facecolor=COLORS["gpu"], label="L4 GPU"),
            Patch(facecolor="white", edgecolor=COLORS["error"], linewidth=2.4, label="missed measured oracle"),
        ]
        axis.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.5, -0.34), ncol=3)
        return _save_figure_bundle(
            figure,
            output_stem,
            description="Instance-level backend decisions compared directly with the measured oracle",
        )


def render_regret_distribution(predictions: Sequence[Mapping[str, Any]], output_stem: Path) -> dict[str, bool]:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    policies = LEARNED_POLICY_ORDER
    misses = [
        row for row in predictions
        if row["policy"] in policies and row["normalized_regret"] > 0
    ]
    misses.sort(key=lambda row: (policies.index(row["policy"]), row["normalized_regret"], row["family_id"], row["n_configurations"]))
    if not misses:
        raise SubmissionFigureError("regret figure requires at least one nonzero-regret decision")

    labels = [
        f"{POLICY_LABELS[row['policy']]}  ·  {_family_label(row['family_id'])}  ·  {row['n_configurations']:,}"
        for row in misses
    ]
    values = [row["normalized_regret"] * 100.0 for row in misses]
    low_values = [value for value in values if value < 100.0]
    high_values = [value for value in values if value >= 100.0]
    low_max = max(10.0, (max(low_values) if low_values else 10.0) * 1.22)

    with mpl.rc_context(_style_context()):
        if high_values:
            figure, (left, right) = plt.subplots(
                1, 2, figsize=(12.6, max(3.8, 0.52 * len(misses) + 1.3)),
                sharey=True, gridspec_kw={"width_ratios": (4.3, 1.25)}, constrained_layout=True
            )
            axes = (left, right)
        else:
            figure, left = plt.subplots(figsize=(11.2, max(3.8, 0.52 * len(misses) + 1.3)), constrained_layout=True)
            right = None
            axes = (left,)
        y = list(range(len(misses)))
        for yi, row, value in zip(y, misses, values):
            color = COLORS[row["policy"]]
            if value < 100.0:
                left.hlines(yi, 0, value, color=color, linestyle=":", linewidth=2.1)
                left.scatter(value, yi, s=100, color=color, edgecolor="white", linewidth=1.0, zorder=3)
                left.text(value + low_max * 0.02, yi, f"{value:.1f}%", va="center", fontsize=9.1, fontweight="semibold")
            elif right is not None:
                right.hlines(yi, min(high_values) * 0.97, value, color=color, linestyle=":", linewidth=2.1)
                right.scatter(value, yi, s=115, color=color, edgecolor="white", linewidth=1.0, zorder=3)
                right.text(value + max(high_values) * 0.006, yi, f"{value:.1f}%", va="center", fontsize=9.1, fontweight="semibold")
        left.set_xlim(0, low_max)
        left.set_yticks(y, labels)
        left.invert_yaxis()
        left.set_xlabel("Normalized regret (%)  ↓")
        left.grid(True, axis="x")
        left.grid(False, axis="y")
        if right is not None:
            lower = min(high_values) * 0.97
            upper = max(high_values) * 1.04
            right.set_xlim(lower, upper)
            right.set_xlabel("outlier")
            right.grid(True, axis="x")
            right.grid(False, axis="y")
            right.tick_params(labelleft=False)
            # Broken-axis marks.
            d = 0.012
            kwargs = dict(transform=left.transAxes, color="#4B5563", clip_on=False, linewidth=1.0)
            left.plot((1 - d, 1 + d), (-d, +d), **kwargs)
            left.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)
            kwargs.update(transform=right.transAxes)
            right.plot((-d, +d), (-d, +d), **kwargs)
            right.plot((-d, +d), (1 - d, 1 + d), **kwargs)
        figure.text(0.995, 0.01, "Only nonzero-regret decisions are shown; larger is worse.", ha="right", fontsize=8.3, color="#6B7280")
        return _save_figure_bundle(
            figure,
            output_stem,
            description="Visible lollipop comparison of every nonzero held-out regret event",
        )

def _tree_positions(nodes: Sequence[Mapping[str, Any]]) -> tuple[dict[int, tuple[float, int]], int]:
    by_id = {_integer(node["node_id"], "node_id", minimum=0): node for node in nodes}
    positions: dict[int, tuple[float, int]] = {}
    leaf_counter = 0
    max_depth = 0

    def visit(node_id: int, depth: int, stack: set[int]) -> float:
        nonlocal leaf_counter, max_depth
        if node_id in stack:
            raise SubmissionFigureError("deployment tree contains a cycle")
        node = by_id.get(node_id)
        if node is None:
            raise SubmissionFigureError(f"deployment tree references missing node {node_id}")
        max_depth = max(max_depth, depth)
        node_type = node.get("type")
        if node_type == "leaf":
            x = float(leaf_counter)
            leaf_counter += 1
        elif node_type == "split":
            left = _integer(node.get("left_child"), "left_child", minimum=0)
            right = _integer(node.get("right_child"), "right_child", minimum=0)
            left_x = visit(left, depth + 1, stack | {node_id})
            right_x = visit(right, depth + 1, stack | {node_id})
            x = (left_x + right_x) / 2.0
        else:
            raise SubmissionFigureError(f"unexpected tree node type: {node_type}")
        positions[node_id] = (x, depth)
        return x

    visit(0, 0, set())
    return positions, max_depth


def _feature_display(name: str) -> str:
    labels = {
        "log1p_n_configurations": "log(1 + configurations)",
        "backend_gpu": "candidate is GPU",
        "log1p_method0_work_proxy": "log(1 + work proxy)",
        "log1p_determinant_cache_bytes": "log(1 + determinant cache bytes)",
        "log1p_gpu_guard_bytes": "log(1 + GPU guard bytes)",
        "alpha_single_edge_density": "α single-edge density",
        "alpha_double_edge_density": "α double-edge density",
        "beta_single_edge_density": "β single-edge density",
        "beta_double_edge_density": "β double-edge density",
        "cpu_threads": "CPU threads",
    }
    return labels.get(name, name.replace("_", " "))



def render_deployment_tree(model: Mapping[str, Any], output_stem: Path) -> tuple[dict[str, bool], list[dict[str, Any]]]:
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    tree = model["tree"]
    nodes = tree["nodes"]
    positions, max_depth = _tree_positions(nodes)
    by_id = {int(node["node_id"]): node for node in nodes}
    leaf_count = sum(node.get("type") == "leaf" for node in nodes)
    width = max(11.5, leaf_count * 2.45)
    height = max(5.2, (max_depth + 1) * 1.75)
    trace_rows: list[dict[str, Any]] = []

    def human_split(feature_name: str, threshold: float) -> str:
        if feature_name == "log1p_n_configurations":
            return f"Configurations ≤ {int(round(math.expm1(threshold))):,}?"
        if feature_name == "backend_gpu":
            return "GPU candidate?"
        if feature_name == "log1p_method0_work_proxy":
            return f"Work proxy ≤ {math.expm1(threshold):.2g}?"
        if feature_name == "log1p_determinant_cache_bytes":
            return f"Determinant cache ≤ {math.expm1(threshold) / MIB:.1f} MiB?"
        if feature_name == "log1p_gpu_guard_bytes":
            return f"GPU guard ≤ {math.expm1(threshold) / MIB:.1f} MiB?"
        if feature_name == "cpu_threads":
            return f"CPU threads ≤ {threshold:.1f}?"
        if "density" in feature_name:
            return f"{_feature_display(feature_name)} ≤ {threshold:.3g}?"
        return f"{_feature_display(feature_name)} ≤ {threshold:.3g}?"

    with mpl.rc_context(_style_context()):
        figure, axis = plt.subplots(figsize=(width, height), constrained_layout=True)
        axis.set_xlim(-0.95, max(leaf_count - 1, 0) + 0.95)
        axis.set_ylim(max_depth + 0.85, -0.95)
        axis.axis("off")
        for node_id, node in by_id.items():
            if node.get("type") != "split":
                continue
            x, depth = positions[node_id]
            for child_key, edge_label in (("left_child", "YES"), ("right_child", "NO")):
                child_id = int(node[child_key])
                child_x, child_depth = positions[child_id]
                axis.add_patch(FancyArrowPatch(
                    (x, depth + 0.26), (child_x, child_depth - 0.29),
                    arrowstyle="-|>", mutation_scale=11, linewidth=1.2,
                    color="#9CA3AF", zorder=1
                ))
                axis.text(
                    (x + child_x) / 2, (depth + child_depth) / 2 - 0.03,
                    edge_label, fontsize=7.8, color="#6B7280", ha="center", fontweight="bold"
                )
        for node_id, node in by_id.items():
            x, depth = positions[node_id]
            sample_count = _integer(node.get("sample_count"), "sample_count", minimum=1)
            if node.get("type") == "split":
                feature_name = _text(node.get("feature_name"), "feature_name")
                threshold = _number(node.get("threshold"), "tree threshold")
                label = human_split(feature_name, threshold)
                edge = COLORS["autosbd_full_tree"]
                face = "#FFFFFF"
                trace_rows.append({"node_id": node_id, "type": "split", "feature_name": feature_name, "threshold": threshold, "sample_count": sample_count, "predicted_runtime_s": None})
            else:
                value = _number(node.get("value_log1p_median_wall_time_s"), "leaf value")
                runtime = math.expm1(value)
                label = f"Predicted runtime\n{runtime:.3g} s"
                edge = "#4B5563"
                face = "#F9FAFB"
                trace_rows.append({"node_id": node_id, "type": "leaf", "feature_name": None, "threshold": None, "sample_count": sample_count, "predicted_runtime_s": runtime})
            patch = FancyBboxPatch(
                (x - 0.83, depth - 0.29), 1.66, 0.58,
                boxstyle="round,pad=0.035,rounding_size=0.05",
                linewidth=1.3, edgecolor=edge, facecolor=face, zorder=2
            )
            axis.add_patch(patch)
            axis.text(x, depth - 0.035, label, ha="center", va="center", fontsize=8.5, fontweight="semibold" if node.get("type") == "split" else "normal", zorder=3)
            axis.text(x, depth + 0.19, f"n={sample_count}", ha="center", va="center", fontsize=7.2, color="#6B7280", zorder=3)
        axis.text(
            0.99, 0.02, "Deployment-only reconstruction · excluded from held-out metrics",
            transform=axis.transAxes, ha="right", va="bottom", fontsize=8.4, color="#6B7280"
        )
        outputs = _save_figure_bundle(
            figure,
            output_stem,
            description="Manually reconstructed AutoSBD deployment decision tree",
        )
    return outputs, sorted(trace_rows, key=lambda row: row["node_id"])


def render_inference_overhead(rows: Sequence[Mapping[str, Any]], output_stem: Path) -> dict[str, bool]:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    lookup = {row["measurement"]: row for row in rows}
    hot = lookup["hot_selection"]
    cold = lookup["cold_load_plus_selection"]
    hot_percent = hot["hot_percent_of_shortest_sbd"]
    if hot_percent is None or hot_percent <= 0:
        raise SubmissionFigureError("hot selector row must report percent of shortest SBD runtime")
    shortest_sbd_us = hot["median_us"] / (hot_percent / 100.0)
    labels = ("Hot selection", "Load + selection", "Shortest SBD run")
    values = (hot["median_us"], cold["median_us"], shortest_sbd_us)
    colors = (COLORS["autosbd_full_tree"], "#4F46E5", "#6B7280")

    with mpl.rc_context(_style_context()):
        figure, axis = plt.subplots(figsize=(8.8, 4.25), constrained_layout=True)
        bars = axis.bar(range(3), values, width=0.62, color=colors, edgecolor="white", linewidth=0.9)
        axis.set_yscale("log")
        axis.set_xticks(range(3), labels)
        axis.set_ylabel("Median latency (µs, log scale)")
        axis.grid(True, axis="y", which="both")
        axis.grid(False, axis="x")
        for bar, value in zip(bars, values):
            label = f"{value:.1f} µs" if value < 1000 else f"{value / 1000:.1f} ms"
            axis.text(bar.get_x() + bar.get_width() / 2, value * 1.17, label, ha="center", va="bottom", fontsize=9.3, fontweight="semibold")
        ratio = shortest_sbd_us / hot["median_us"]
        axis.annotate(
            f"{ratio:,.0f}× smaller than\nthe shortest SBD median",
            xy=(0, hot["median_us"]), xytext=(0.55, math.sqrt(hot["median_us"] * shortest_sbd_us)),
            textcoords="data", fontsize=9.3, color=COLORS["autosbd_full_tree"],
            arrowprops={"arrowstyle": "->", "color": COLORS["autosbd_full_tree"], "lw": 1.2},
            ha="left", va="center"
        )
        axis.margins(y=0.25)
        return _save_figure_bundle(
            figure,
            output_stem,
            description="Selector latency compared directly with the shortest measured SBD runtime",
        )


def render_memory_headroom(rows: Sequence[Mapping[str, Any]], output_stem: Path) -> tuple[dict[str, bool], list[dict[str, Any]]]:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    summaries: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        family_rows = [row for row in rows if row["family_id"] == family]
        grouped: dict[int, list[Mapping[str, Any]]] = {}
        for row in family_rows:
            grouped.setdefault(int(row["n_configurations"]), []).append(row)
        if len(grouped) != 5:
            raise SubmissionFigureError(f"memory figure requires five final sizes for {family}")
        for size, group in sorted(grouped.items()):
            peaks = sorted(float(row["peak_gpu_memory_mib"]) for row in group)
            median_peak = peaks[len(peaks) // 2]
            guards = {float(row["estimated_gpu_guard_mib"]) for row in group}
            caps = {float(row["gpu_admission_cap_mib"]) for row in group}
            if len(guards) != 1:
                raise SubmissionFigureError(f"memory guard changed within {family}/{size}")
            summaries.append({
                "family_id": family,
                "n_configurations": size,
                "median_peak_gpu_mib": median_peak,
                "estimated_guard_mib": next(iter(guards)),
                "minimum_admission_cap_mib": min(caps),
                "repetitions": len(group),
            })

    with mpl.rc_context(_style_context()):
        figure, axes = plt.subplots(1, 3, figsize=(13.6, 4.15), constrained_layout=True)
        for family in FAMILY_ORDER:
            family_summary = [row for row in summaries if row["family_id"] == family]
            x = [row["n_configurations"] for row in family_summary]
            peak = [row["median_peak_gpu_mib"] for row in family_summary]
            guard = [row["estimated_guard_mib"] for row in family_summary]
            ratio = [row["minimum_admission_cap_mib"] / row["median_peak_gpu_mib"] for row in family_summary]
            axes[0].plot(x, peak, marker="o", markersize=5.8, linewidth=2.0, label=_family_label(family))
            axes[1].plot(x, guard, marker="s", markersize=5.8, linewidth=2.0, label=_family_label(family))
            axes[2].plot(x, ratio, marker="D", markersize=5.5, linewidth=2.0, label=_family_label(family))
            for axis, series in ((axes[0], peak), (axes[1], guard), (axes[2], ratio)):
                axis.annotate(_family_label(family), xy=(x[-1], series[-1]), xytext=(5, 0), textcoords="offset points", va="center", fontsize=8.2)
        for axis in axes:
            axis.set_xscale("log")
            axis.set_xlabel("Configurations")
            axis.grid(True, which="major")
            axis.grid(True, which="minor", alpha=0.12)
            axis.margins(x=0.08, y=0.14)
        axes[0].set_ylabel("Measured peak GPU memory (MiB)")
        axes[1].set_ylabel("Conservative guard estimate (MiB)")
        axes[2].set_ylabel("Admission cap / measured peak (×, log scale)")
        axes[2].set_yscale("log")
        axes[0].text(0.03, 0.97, "A  measured", transform=axes[0].transAxes, ha="left", va="top", fontweight="bold")
        axes[1].text(0.03, 0.97, "B  guarded", transform=axes[1].transAxes, ha="left", va="top", fontweight="bold")
        axes[2].text(0.03, 0.97, "C  headroom", transform=axes[2].transAxes, ha="left", va="top", fontweight="bold")
        figure.text(0.995, 0.01, "A and B use linear y-axes; C uses a logarithmic y-axis.", ha="right", fontsize=8.3, color="#6B7280")
        outputs = _save_figure_bundle(
            figure,
            output_stem,
            description="Measured memory, conservative guard, and logarithmic admission headroom",
        )
    return outputs, summaries


def render_energy_error_margin(rows: Sequence[Mapping[str, Any]], output_stem: Path) -> tuple[dict[str, bool], list[dict[str, Any]]]:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    summaries: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        for backend in ("cpu", "gpu"):
            values = [row["relative_error"] for row in rows if row["family_id"] == family and row["backend"] == backend]
            if not values:
                continue
            summaries.append({
                "family_id": family,
                "backend": backend,
                "maximum_relative_energy_error": max(values),
                "record_count": len(values),
            })
    tolerance = 1e-10
    family_worst: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        values = [row["maximum_relative_energy_error"] for row in summaries if row["family_id"] == family]
        if not values:
            raise SubmissionFigureError(f"energy figure lacks values for {family}")
        worst = max(values)
        display_error = max(worst, 1e-18)
        margin_orders = math.log10(tolerance / display_error)
        family_worst.append({"family_id": family, "worst_error": worst, "margin_orders": margin_orders})

    with mpl.rc_context(_style_context()):
        figure, axis = plt.subplots(figsize=(8.7, 4.15), constrained_layout=True)
        bars = axis.barh(
            range(len(family_worst)),
            [row["margin_orders"] for row in family_worst],
            height=0.58,
            color=[COLORS["autosbd_full_tree"]] * len(family_worst),
            edgecolor="white", linewidth=0.9
        )
        axis.set_yticks(range(len(family_worst)), [_family_label(row["family_id"]) for row in family_worst])
        axis.invert_yaxis()
        axis.set_xlabel("Orders of magnitude inside the 1×10⁻¹⁰ acceptance tolerance  ↑")
        axis.set_xlim(0, max(row["margin_orders"] for row in family_worst) * 1.30)
        axis.grid(True, axis="x")
        axis.grid(False, axis="y")
        for bar, row in zip(bars, family_worst):
            axis.text(
                row["margin_orders"] + 0.08, bar.get_y() + bar.get_height() / 2,
                f"{row['margin_orders']:.1f} orders   (max error {row['worst_error']:.1e})",
                va="center", fontsize=9.3, fontweight="semibold"
            )
        axis.axvline(0, color="#4B5563", linewidth=0.9)
        return _save_figure_bundle(
            figure,
            output_stem,
            description="Numerical correctness shown as orders-of-magnitude safety margin",
        )
    return outputs, summaries

def generate_submission_figure_suite(
    *,
    stage4_aggregate: Path,
    phaseb_aggregate: Path,
    policy_summary: Path,
    policy_predictions: Path,
    models: Path,
    inference_overhead: Path,
    raw_dir: Path,
    numerical_parity_csv: Path,
    output_dir: Path,
    table_dir: Path,
) -> dict[str, Any]:
    """Generate the complete professional submission figure suite."""

    output = Path(output_dir)
    tables = Path(table_dir)
    output.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)

    runtime_rows = extract_runtime_rows(
        stage4_aggregate,
        fallback_family="fe4s4",
        fallback_molecule="Fe4S4",
        fallback_basis=None,
    ) + extract_runtime_rows(phaseb_aggregate)
    if {row["family_id"] for row in runtime_rows} != set(FAMILY_ORDER):
        raise SubmissionFigureError("runtime evidence must contain exactly Fe4S4, N2, and H2O")
    summary_rows = load_policy_summary(policy_summary)
    prediction_rows = load_predictions(policy_predictions)
    model = load_deployment_tree(models)
    overhead_rows = load_inference_overhead(inference_overhead)
    memory_rows = extract_gpu_memory_rows(runtime_rows, raw_dir)
    energy_rows = load_energy_error_rows(numerical_parity_csv)

    changed: dict[str, bool] = {}
    changed.update(render_architecture(output / "01_pipeline_architecture"))
    changed.update(render_runtime_scaling(runtime_rows, output / "02_runtime_scaling_by_family"))
    changed.update(render_pooled_policy_performance(summary_rows, output / "03_pooled_policy_performance"))
    changed.update(render_family_generalization(summary_rows, output / "04_family_holdout_generalization"))
    changed.update(render_decision_map(prediction_rows, output / "05_instance_decision_map"))
    changed.update(render_regret_distribution(prediction_rows, output / "06_regret_distribution"))
    tree_outputs, tree_rows = render_deployment_tree(model, output / "07_deployment_tree")
    changed.update(tree_outputs)
    changed.update(render_inference_overhead(overhead_rows, output / "08_inference_overhead"))
    memory_outputs, memory_summary = render_memory_headroom(memory_rows, output / "09_gpu_memory_headroom")
    changed.update(memory_outputs)
    energy_outputs, energy_summary = render_energy_error_margin(energy_rows, output / "10_energy_error_margin")
    changed.update(energy_outputs)

    table_status = {
        str(tables / "runtime_scaling.csv"): _write_csv(
            tables / "runtime_scaling.csv",
            runtime_rows,
            (
                "family_id", "family_label", "molecule", "basis", "problem_instance",
                "n_configurations", "candidate", "backend", "count", "wall_q1_s",
                "wall_median_s", "wall_q3_s", "wall_iqr_s", "solver_median_s", "record_ids",
            ),
        ),
        str(tables / "policy_summary_normalized.csv"): _write_csv(
            tables / "policy_summary_normalized.csv",
            summary_rows,
            (
                "scope", "heldout_family_id", "policy", "requested_instances",
                "valid_instances", "invalid_instances", "failure_instances",
                "selection_accuracy", "within_5pct_oracle_rate",
                "geometric_mean_selected_over_oracle", "median_regret", "p90_regret",
                "maximum_regret", "speedup_vs_cpu", "speedup_vs_gpu",
            ),
        ),
        str(tables / "heldout_predictions_normalized.csv"): _write_csv(
            tables / "heldout_predictions_normalized.csv",
            prediction_rows,
            (
                "fold_id", "family_id", "family_label", "policy", "instance_id",
                "problem_instance", "n_configurations", "selected_candidate",
                "selected_backend", "oracle_candidates", "oracle_backend",
                "selected_wall_time_s", "oracle_wall_time_s", "normalized_runtime",
                "normalized_regret", "selection_correct", "within_5pct_oracle",
            ),
        ),
        str(tables / "deployment_tree_nodes.csv"): _write_csv(
            tables / "deployment_tree_nodes.csv",
            tree_rows,
            ("node_id", "type", "feature_name", "threshold", "sample_count", "predicted_runtime_s"),
        ),
        str(tables / "gpu_memory_records.csv"): _write_csv(
            tables / "gpu_memory_records.csv",
            memory_rows,
            (
                "family_id", "problem_instance", "n_configurations", "trial_id",
                "raw_sha256", "peak_gpu_memory_mib", "estimated_gpu_guard_mib",
                "gpu_admission_cap_mib",
            ),
        ),
        str(tables / "gpu_memory_summary.csv"): _write_csv(
            tables / "gpu_memory_summary.csv",
            memory_summary,
            ("family_id", "n_configurations", "median_peak_gpu_mib", "estimated_guard_mib", "minimum_admission_cap_mib", "repetitions"),
        ),
        str(tables / "energy_error_summary.csv"): _write_csv(
            tables / "energy_error_summary.csv",
            energy_summary,
            ("family_id", "backend", "maximum_relative_energy_error", "record_count"),
        ),
    }
    changed.update(table_status)

    sources = {
        "stage4_aggregate": Path(stage4_aggregate),
        "phaseb_aggregate": Path(phaseb_aggregate),
        "policy_summary": Path(policy_summary),
        "policy_predictions": Path(policy_predictions),
        "models": Path(models),
        "inference_overhead": Path(inference_overhead),
        "raw_directory": Path(raw_dir),
        "numerical_parity_csv": Path(numerical_parity_csv),
    }
    outputs = sorted(path for path in output.glob("*") if path.is_file()) + sorted(
        path for path in tables.glob("*") if path.is_file()
    )
    manifest = {
        "schema_version": 1,
        "generator": "autosbd.submission_figures.generate_submission_figure_suite",
        "claim_boundary": {
            "families": list(FAMILY_ORDER),
            "instances_per_family": 5,
            "candidate_space": [CPU_CANDIDATE, GPU_CANDIDATE],
            "heldout_protocol": "leave-one-chemistry-family-out",
            "crossover_interpolation": "none",
            "confidence_intervals": "not claimed; runtime bands are IQR",
            "deployment_tree_used_for_heldout_metrics": False,
            "memory_boundary_reached": False,
        },
        "sources": {
            name: (
                {"path": str(path), "type": "directory"}
                if path.is_dir()
                else {
                    "path": str(path),
                    "type": "file",
                    "sha256": sha256_path(path),
                    "size_bytes": path.stat().st_size,
                }
            )
            for name, path in sources.items()
        },
        "outputs": {
            str(path): {
                "sha256": sha256_path(path),
                "size_bytes": path.stat().st_size,
            }
            for path in outputs
        },
    }
    manifest_path = tables / "submission_figure_manifest.json"
    changed[str(manifest_path)] = _atomic_write(
        manifest_path,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return {
        "status": "complete",
        "figures": 10,
        "families": 3,
        "instances": 15,
        "policies": 6,
        "changed": changed,
        "manifest": str(manifest_path),
    }


__all__ = [
    "SubmissionFigureError",
    "extract_gpu_memory_rows",
    "extract_runtime_rows",
    "generate_submission_figure_suite",
    "load_deployment_tree",
    "load_policy_summary",
    "load_predictions",
]
