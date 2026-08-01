"""Hash-bound loading and deterministic artifact writing for Stage 5."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

import sklearn
import yaml

from .evaluation import (
    BALANCED_REPETITIONS,
    FULL_FEATURE_NAMES,
    POLICY_FULL_TREE,
    POLICY_ORDER,
    POLICY_SIZE_TREE,
    POLICY_THRESHOLD,
    REQUIRED_SKLEARN_VERSION,
    SIZE_ONLY_FEATURE_NAMES,
    TREE_MAX_DEPTH,
    TREE_MIN_SAMPLES_LEAF,
    TREE_RANDOM_STATE,
    EvaluationError,
    build_balanced_dataset,
    evaluate_selector,
    fit_runtime_tree,
    fit_static_threshold,
)


ARTIFACT_SCHEMA_VERSION = 1
EXPECTED_CONFIG_NAME = "stage5-amd-fe4s4-selector-v1"


class EvaluationArtifactError(ValueError):
    """Raised when Stage 5 sources or output contracts are invalid."""


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueSafeLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise EvaluationArtifactError(f"duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_evaluation_package(
    config_path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Load explicit hash-bound sources and run the frozen evaluation."""

    root = Path(repository_root).resolve(strict=True)
    config_file = _regular_file(Path(config_path), "Stage 5 config")
    config = _load_yaml(config_file)
    _validate_config(config)
    sources = _mapping(config.get("sources"), "sources")

    protocol_path, protocol = _load_claimed_json(
        sources.get("stage4_protocol"), root, "Stage 4 protocol"
    )
    completion_path, completion = _load_claimed_json(
        sources.get("stage4_completion"), root, "Stage 4 completion"
    )
    aggregate_path, aggregate = _load_claimed_json(
        sources.get("stage4_aggregate"), root, "Stage 4 aggregate"
    )
    raw_dir = _resolve_inside(root, sources.get("raw_directory"), "raw directory")
    if not raw_dir.is_dir():
        raise EvaluationArtifactError(f"raw directory is not a directory: {raw_dir}")

    if protocol.get("status") != "frozen_before_measurement":
        raise EvaluationArtifactError("Stage 4 protocol is not frozen")
    if completion.get("status") != "complete":
        raise EvaluationArtifactError("Stage 4 completion is not complete")
    if completion.get("attestation_type") != "autosbd_stage4_completion":
        raise EvaluationArtifactError("unexpected Stage 4 completion type")
    if _nested(completion, "source_artifacts", "protocol", "sha256") != sha256_path(
        protocol_path
    ):
        raise EvaluationArtifactError("completion/protocol SHA mismatch")
    if _nested(completion, "source_artifacts", "aggregate", "sha256") != sha256_path(
        aggregate_path
    ):
        raise EvaluationArtifactError("completion/aggregate SHA mismatch")
    counts = _mapping(completion.get("campaign_counts"), "campaign_counts")
    expected_counts = {"records": 48, "warmup": 10, "measured": 38, "timing_eligible": 38}
    for key, value in expected_counts.items():
        if counts.get(key) != value:
            raise EvaluationArtifactError(f"completion count mismatch for {key}")

    balanced_view = _mapping(
        _nested(completion, "analysis_views", "balanced_broad_sensitivity"),
        "balanced view",
    )
    balanced_ids = _string_list(balanced_view.get("record_ids"), "balanced record IDs")
    if len(balanced_ids) != 30:
        raise EvaluationArtifactError("balanced completion view must have 30 records")
    trace_by_id: dict[str, Mapping[str, Any]] = {}
    for trace in completion.get("records", []):
        trace_mapping = _mapping(trace, "completion record trace")
        trial_id = _required_text(trace_mapping.get("trial_id"), "completion trial_id")
        if trial_id in trace_by_id:
            raise EvaluationArtifactError(f"duplicate completion trial ID: {trial_id}")
        trace_by_id[trial_id] = trace_mapping
    if len(trace_by_id) != 48:
        raise EvaluationArtifactError("completion must trace exactly 48 records")

    metadata: dict[str, Mapping[str, Any]] = {}
    for trial_id in balanced_ids:
        trace = trace_by_id.get(trial_id)
        if trace is None:
            raise EvaluationArtifactError(f"balanced trial not traced: {trial_id}")
        raw_path = raw_dir / f"{trial_id}.json"
        if raw_path.is_symlink():
            raise EvaluationArtifactError(f"raw record must not be a symlink: {raw_path}")
        raw_path = _regular_file(raw_path, f"raw record {trial_id}")
        raw_claim = _mapping(trace.get("raw_record"), "completion raw_record")
        if raw_claim.get("sha256") != sha256_path(raw_path):
            raise EvaluationArtifactError(f"raw SHA mismatch: {trial_id}")
        if raw_claim.get("size_bytes") != raw_path.stat().st_size:
            raise EvaluationArtifactError(f"raw size mismatch: {trial_id}")
        raw = _load_json(raw_path, f"raw record {trial_id}")
        if raw.get("trial_id") != trial_id:
            raise EvaluationArtifactError(f"raw trial ID mismatch: {trial_id}")
        metadata[trial_id] = raw

    try:
        dataset = build_balanced_dataset(
            aggregate,
            metadata_by_record_id=metadata,
            expected_instances=5,
        )
        evaluation = evaluate_selector(dataset)
        deployment_models = {
            POLICY_THRESHOLD: fit_static_threshold(dataset["rows"]),
            POLICY_FULL_TREE: fit_runtime_tree(
                dataset["rows"], feature_names=FULL_FEATURE_NAMES
            ),
            POLICY_SIZE_TREE: fit_runtime_tree(
                dataset["rows"], feature_names=SIZE_ONLY_FEATURE_NAMES
            ),
        }
    except EvaluationError as error:
        raise EvaluationArtifactError(f"selector evaluation failed: {error}") from error
    if set(dataset["source_record_ids"]) != set(balanced_ids):
        raise EvaluationArtifactError("dataset source IDs do not match completion view")

    package = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "autosbd_stage5_evaluation_package",
        "status": "complete",
        "config": {
            "name": config["name"],
            "path": _display_path(config_file, root),
            "sha256": sha256_path(config_file),
        },
        "sources": {
            "stage4_protocol": _file_claim(protocol_path, root),
            "stage4_completion": _file_claim(completion_path, root),
            "stage4_aggregate": _file_claim(aggregate_path, root),
            "raw_directory": _display_path(raw_dir, root),
            "balanced_record_ids": sorted(balanced_ids),
        },
        "environment": {
            "scikit_learn": sklearn.__version__,
            "required_scikit_learn": REQUIRED_SKLEARN_VERSION,
        },
        "claim_boundary": dict(_mapping(config["claim_boundary"], "claim_boundary")),
        "dataset": dataset,
        "evaluation": evaluation,
        "deployment_models": deployment_models,
    }
    _strict_json_bytes(package)
    return package


def write_evaluation_artifacts(
    package: Mapping[str, Any], output_dir: Path
) -> dict[str, Any]:
    """Write deterministic JSON/CSV artifacts and return changed/hash status."""

    if package.get("status") != "complete":
        raise EvaluationArtifactError("evaluation package is not complete")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    evaluation = _mapping(package.get("evaluation"), "evaluation")

    models = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "config": package["config"],
        "deployment_models": package["deployment_models"],
        "primary": evaluation["primary"]["models"],
        "secondary_leave_one_instance_out": [
            {
                "split_id": fold["split"]["split_id"],
                "models": fold["models"],
            }
            for fold in evaluation["secondary_leave_one_instance_out"]["folds"]
        ],
    }
    splits = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "config": package["config"],
        "source_record_ids": package["dataset"]["source_record_ids"],
        "primary": evaluation["primary"]["split"],
        "secondary_leave_one_instance_out": [
            fold["split"]
            for fold in evaluation["secondary_leave_one_instance_out"]["folds"]
        ],
        "leakage_check": "PASS",
    }
    prediction_rows = _prediction_rows(evaluation)
    summary_rows = _summary_rows(evaluation)
    ablation_rows = [
        row
        for row in summary_rows
        if row["policy"] in (POLICY_THRESHOLD, POLICY_FULL_TREE, POLICY_SIZE_TREE)
    ]
    policy_summary = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "config": package["config"],
        "rows": summary_rows,
        "policy_aliases": {"upstream_default": "fixed_gpu"},
    }

    payloads: dict[str, bytes] = {
        "evaluation.json": _strict_json_bytes(dict(package)),
        "balanced_dataset.json": _strict_json_bytes(package["dataset"]),
        "models.json": _strict_json_bytes(models),
        "split_manifest.json": _strict_json_bytes(splits),
        "policy_summary.json": _strict_json_bytes(policy_summary),
        "policy_predictions.csv": _csv_bytes(
            prediction_rows,
            (
                "view",
                "fold_id",
                "policy",
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
                "speedup_vs_fixed_cpu",
                "speedup_vs_fixed_gpu",
                "selection_correct",
                "within_5pct_oracle",
                "valid",
                "failure",
                "invalid_reason",
                "selected_source_record_ids",
                "oracle_source_record_ids",
                "candidate_predictions",
            ),
        ),
        "policy_summary.csv": _csv_bytes(summary_rows, tuple(summary_rows[0])),
        "selector_ablation.csv": _csv_bytes(ablation_rows, tuple(ablation_rows[0])),
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
    return {
        "status": "complete",
        "changed": changed,
        "files": files,
        "balanced_measurements": package["dataset"]["record_counts"][
            "selected_measurements"
        ],
        "candidate_rows": package["dataset"]["record_counts"]["candidate_rows"],
        "primary_test_instances": len(
            evaluation["primary"]["split"]["test_instance_ids"]
        ),
        "secondary_folds": len(
            evaluation["secondary_leave_one_instance_out"]["folds"]
        ),
    }


def build_and_write_evaluation(
    config_path: Path,
    output_dir: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    package = build_evaluation_package(config_path, repository_root=repository_root)
    return write_evaluation_artifacts(package, output_dir)


def _validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema_version") != 1 or config.get("name") != EXPECTED_CONFIG_NAME:
        raise EvaluationArtifactError("unexpected Stage 5 config identity")
    dataset = _mapping(config.get("dataset"), "dataset")
    expected_dataset = {
        "source_view": "balanced_broad_sensitivity",
        "phase": "measured",
        "repetitions": list(BALANCED_REPETITIONS),
        "expected_measurements": 30,
        "expected_candidate_rows": 10,
        "expected_problem_instances": 5,
        "expected_candidates_per_instance": 2,
        "pilot_records_allowed": False,
        "post_execution_selection_features_allowed": False,
    }
    for key, value in expected_dataset.items():
        if dataset.get(key) != value:
            raise EvaluationArtifactError(f"Stage 5 dataset config mismatch: {key}")
    model = _mapping(config.get("model"), "model")
    expected_model = {
        "implementation": "sklearn.tree.DecisionTreeRegressor",
        "sklearn_version": REQUIRED_SKLEARN_VERSION,
        "max_depth": TREE_MAX_DEPTH,
        "min_samples_leaf": TREE_MIN_SAMPLES_LEAF,
        "random_state": TREE_RANDOM_STATE,
        "heldout_hyperparameter_tuning": False,
        "full_features": list(FULL_FEATURE_NAMES),
        "size_only_ablation_features": list(SIZE_ONLY_FEATURE_NAMES),
    }
    for key, value in expected_model.items():
        if model.get(key) != value:
            raise EvaluationArtifactError(f"Stage 5 model config mismatch: {key}")
    if sklearn.__version__ != REQUIRED_SKLEARN_VERSION:
        raise EvaluationArtifactError(
            f"scikit-learn must be {REQUIRED_SKLEARN_VERSION}, got {sklearn.__version__}"
        )
    splits = _mapping(config.get("splits"), "splits")
    if _nested(splits, "primary", "type") != "largest_size_holdout":
        raise EvaluationArtifactError("primary split must be largest-size holdout")
    if _nested(splits, "primary", "holdout_largest_instances") != 1:
        raise EvaluationArtifactError("primary split must hold out one largest instance")
    if _nested(splits, "sensitivity", "type") != "leave_one_problem_instance_out":
        raise EvaluationArtifactError("unexpected sensitivity split")
    if _nested(splits, "sensitivity", "folds") != 5:
        raise EvaluationArtifactError("sensitivity split must have five folds")
    if config.get("policy_aliases") != {"upstream_default": "fixed_gpu"}:
        raise EvaluationArtifactError("upstream-default alias must equal fixed GPU")
    policies = config.get("policies")
    if policies != list(POLICY_ORDER):
        raise EvaluationArtifactError("policy order does not match evaluator")
    boundary = _mapping(config.get("claim_boundary"), "claim_boundary")
    if boundary.get("broad_family_generalization_claim_allowed") is not False:
        raise EvaluationArtifactError("broad family claim boundary must be false")


def _prediction_rows(evaluation: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sources = [("primary_largest_size_holdout", evaluation["primary"])] + [
        ("secondary_leave_one_instance_out", fold)
        for fold in evaluation["secondary_leave_one_instance_out"]["folds"]
    ]
    for view, fold in sources:
        fold_id = fold["split"]["split_id"]
        for prediction in fold["predictions"]:
            rows.append(
                {
                    "view": view,
                    "fold_id": fold_id,
                    **{key: prediction.get(key) for key in (
                        "policy",
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
                        "speedup_vs_fixed_cpu",
                        "speedup_vs_fixed_gpu",
                        "selection_correct",
                        "within_5pct_oracle",
                        "valid",
                        "failure",
                        "invalid_reason",
                        "selected_source_record_ids",
                        "oracle_source_record_ids",
                        "candidate_predictions",
                    )},
                }
            )
    return rows


def _summary_rows(evaluation: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for view, metrics in (
        ("primary_largest_size_holdout", evaluation["primary"]["metrics"]),
        (
            "secondary_leave_one_instance_out",
            evaluation["secondary_leave_one_instance_out"]["metrics"],
        ),
    ):
        for policy in POLICY_ORDER:
            value = metrics[policy]
            rows.append(
                {
                    "view": view,
                    "policy": policy,
                    "requested_instances": value.get("requested_instances"),
                    "valid_instances": value.get("valid_instances"),
                    "invalid_instances": value.get("invalid_instances"),
                    "failure_instances": value.get("failure_instances"),
                    "selection_accuracy": value.get("selection_accuracy"),
                    "within_5pct_oracle_rate": value.get("within_5pct_oracle_rate"),
                    "invalid_rate": value.get("invalid_rate"),
                    "failure_rate": value.get("failure_rate"),
                    "geometric_mean_selected_over_oracle_valid_only": value.get(
                        "geometric_mean_selected_over_oracle_valid_only"
                    ),
                    "geometric_mean_speedup_vs_oracle_inverse_valid_only": value.get(
                        "geometric_mean_speedup_vs_oracle_inverse_valid_only"
                    ),
                    "median_normalized_regret_valid_only": value.get(
                        "median_normalized_regret_valid_only"
                    ),
                    "p90_normalized_regret_valid_only": value.get(
                        "p90_normalized_regret_valid_only"
                    ),
                    "maximum_normalized_regret_valid_only": value.get(
                        "maximum_normalized_regret_valid_only"
                    ),
                    "geometric_mean_speedup_vs_fixed_cpu_valid_only": value.get(
                        "geometric_mean_speedup_vs_fixed_cpu_valid_only"
                    ),
                    "geometric_mean_speedup_vs_fixed_gpu_valid_only": value.get(
                        "geometric_mean_speedup_vs_fixed_gpu_valid_only"
                    ),
                }
            )
    return rows


def _csv_bytes(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                field: json.dumps(row.get(field), sort_keys=True, allow_nan=False)
                if isinstance(row.get(field), (list, dict))
                else row.get(field)
                for field in fields
            }
        )
    return stream.getvalue().encode("utf-8")


def _load_claimed_json(
    value: Any, root: Path, label: str
) -> tuple[Path, dict[str, Any]]:
    claim = _mapping(value, f"{label} claim")
    path = _resolve_inside(root, claim.get("path"), label)
    path = _regular_file(path, label)
    expected = _required_digest(claim.get("sha256"), f"{label} SHA")
    if sha256_path(path) != expected:
        raise EvaluationArtifactError(f"{label} SHA mismatch")
    return path, _load_json(path, label)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueSafeLoader)
    except (OSError, UnicodeError, yaml.YAMLError, EvaluationArtifactError) as error:
        raise EvaluationArtifactError(f"cannot load Stage 5 config: {error}") from error
    if not isinstance(value, dict):
        raise EvaluationArtifactError("Stage 5 config must be an object")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
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
            path.read_text(encoding="utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=unique,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise EvaluationArtifactError(f"cannot load {label}: {error}") from error
    if not isinstance(value, dict):
        raise EvaluationArtifactError(f"{label} must be an object")
    return value


def _strict_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise EvaluationArtifactError(f"artifact is not strict JSON: {error}") from error


def _atomic_write_changed(path: Path, payload: bytes) -> bool:
    if path.is_symlink():
        raise EvaluationArtifactError(f"output must not be a symlink: {path}")
    if path.exists():
        if not path.is_file() or path.is_symlink():
            raise EvaluationArtifactError(f"output is not a regular file: {path}")
        if path.read_bytes() == payload:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True


def _resolve_inside(root: Path, value: Any, label: str) -> Path:
    text = _required_text(value, f"{label} path")
    path = Path(text)
    if path.is_absolute():
        raise EvaluationArtifactError(f"{label} path must be repository-relative")
    try:
        resolved = (root / path).resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise EvaluationArtifactError(f"cannot resolve {label}: {error}") from error
    return resolved


def _regular_file(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise EvaluationArtifactError(f"cannot resolve {label}: {error}") from error
    if not resolved.is_file():
        raise EvaluationArtifactError(f"{label} is not a regular file")
    return resolved


def _file_claim(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": _display_path(path, root),
        "sha256": sha256_path(path),
        "size_bytes": path.stat().st_size,
    }


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path.resolve())


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvaluationArtifactError(f"{label} must be an object")
    return value


def _nested(mapping: Any, *keys: str) -> Any:
    value = mapping
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            raise EvaluationArtifactError(f"missing field: {'.'.join(keys)}")
        value = value[key]
    return value


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvaluationArtifactError(f"{label} must be nonempty text")
    return value


def _required_digest(value: Any, label: str) -> str:
    text = _required_text(value, label)
    if len(text) != 64:
        raise EvaluationArtifactError(f"{label} must be SHA-256")
    try:
        int(text, 16)
    except ValueError as error:
        raise EvaluationArtifactError(f"{label} must be SHA-256") from error
    if text.lower() != text:
        raise EvaluationArtifactError(f"{label} must be lowercase SHA-256")
    return text


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise EvaluationArtifactError(f"{label} must be a string list")
    if len(value) != len(set(value)):
        raise EvaluationArtifactError(f"{label} contains duplicates")
    return list(value)


__all__ = [
    "EvaluationArtifactError",
    "build_and_write_evaluation",
    "build_evaluation_package",
    "sha256_path",
    "write_evaluation_artifacts",
]
