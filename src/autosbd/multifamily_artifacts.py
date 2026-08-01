"""Hash-bound loading and deterministic artifacts for multifamily evaluation.

The pure evaluator in :mod:`autosbd.multifamily_evaluation` deliberately has
no filesystem access.  This module is the provenance boundary around it.  It
accepts only explicitly named, SHA-256-bound sources; verifies both completion
attestations and every raw record they trace; enriches legacy Fe4S4 rows in
memory from the external family registry; and writes deterministic artifacts.

Raw records and timing aggregates are never modified.
"""

from __future__ import annotations

import csv
from copy import deepcopy
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
    EXPECTED_CANDIDATES,
    FULL_FEATURE_NAMES,
    POLICY_FULL_TREE,
    POLICY_ORDER,
    POLICY_SIZE_TREE,
    POLICY_THRESHOLD,
    REQUIRED_SKLEARN_VERSION,
    SIZE_ONLY_FEATURE_NAMES,
    TREE_RANDOM_STATE,
    EvaluationError,
)
from .multifamily_evaluation import (
    EXPECTED_CANDIDATE_ROW_COUNT,
    EXPECTED_FAMILY_ORDER,
    EXPECTED_FAMILY_PROVENANCE,
    EXPECTED_INSTANCE_COUNT,
    EXPECTED_INSTANCE_COUNT_PER_FAMILY,
    EXPECTED_MEASUREMENT_COUNT,
    MULTIFAMILY_EVALUATION_TYPE,
    MULTIFAMILY_TREE_MAX_DEPTH,
    MULTIFAMILY_TREE_MIN_SAMPLES_LEAF,
    build_multifamily_balanced_dataset,
    evaluate_multifamily_selector,
    fit_multifamily_deployment_tree,
    validate_leave_one_family_out_split,
    validate_multifamily_dataset,
)


ARTIFACT_SCHEMA_VERSION = 1
EXPECTED_CONFIG_NAME = "stage5-amd-multifamily-selector-v1"
EXPECTED_UPSTREAM_COMMIT = "729cfa3a5011fb805eb9e686a7711f6919836dcb"
EXPECTED_STAGE4_COMPLETION_TYPE = "autosbd_stage4_completion"
EXPECTED_PHASEB_COMPLETION_TYPE = "autosbd_phaseb_final_completion"
EXPECTED_REGISTRY_TYPE = "autosbd_external_family_registry"
EXPECTED_SOURCE_KEYS = (
    "stage4_protocol",
    "stage4_completion",
    "stage4_aggregate",
    "fe4s4_family_registry",
    "phaseb_protocol",
    "phaseb_completion",
    "phaseb_aggregate",
)
EXPECTED_RAW_DIRECTORY_KEY = "raw_directory"


class MultifamilyArtifactError(ValueError):
    """Raised when multifamily sources or output contracts are invalid."""


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueSafeLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise MultifamilyArtifactError(f"duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def sha256_path(path: Path) -> str:
    """Return the SHA-256 digest of *path* without following a late swap."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_multifamily_evaluation_package(
    config_path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Load all hash-bound sources and run the frozen multifamily evaluation."""

    root = Path(repository_root).resolve(strict=True)
    if not root.is_dir():
        raise MultifamilyArtifactError("repository root must be a directory")
    config_file = _existing_file_inside(Path(config_path), root, "multifamily config")
    config = _load_yaml(config_file)
    _validate_config(config)
    sources = _mapping(config.get("sources"), "sources")

    loaded_paths: dict[str, Path] = {}
    loaded: dict[str, dict[str, Any]] = {}
    for key in EXPECTED_SOURCE_KEYS:
        path, value = _load_claimed_json(sources.get(key), root, key)
        loaded_paths[key] = path
        loaded[key] = value
    raw_dir = _resolve_inside(root, sources.get(EXPECTED_RAW_DIRECTORY_KEY), "raw directory")
    if not raw_dir.is_dir():
        raise MultifamilyArtifactError(f"raw directory is not a directory: {raw_dir}")

    stage4_protocol = loaded["stage4_protocol"]
    stage4_completion = loaded["stage4_completion"]
    stage4_aggregate = loaded["stage4_aggregate"]
    registry = loaded["fe4s4_family_registry"]
    phaseb_protocol = loaded["phaseb_protocol"]
    phaseb_completion = loaded["phaseb_completion"]
    phaseb_aggregate = loaded["phaseb_aggregate"]

    _validate_protocols(stage4_protocol, phaseb_protocol)
    stage4_traces, stage4_ids = _validate_completion(
        stage4_completion,
        label="Stage 4 completion",
        completion_type=EXPECTED_STAGE4_COMPLETION_TYPE,
        protocol_path=loaded_paths["stage4_protocol"],
        aggregate_path=loaded_paths["stage4_aggregate"],
        root=root,
        expected_counts={
            "records": 48,
            "warmup": 10,
            "measured": 38,
            "timing_eligible": 38,
        },
        view_name="balanced_broad_sensitivity",
        expected_view_records=30,
    )
    phaseb_traces, phaseb_ids = _validate_completion(
        phaseb_completion,
        label="Phase B completion",
        completion_type=EXPECTED_PHASEB_COMPLETION_TYPE,
        protocol_path=loaded_paths["phaseb_protocol"],
        aggregate_path=loaded_paths["phaseb_aggregate"],
        root=root,
        expected_counts={
            "records": 104,
            "warmup": 20,
            "measured": 84,
            "timing_eligible": 84,
        },
        view_name="balanced_broad",
        expected_view_records=60,
    )
    if set(stage4_traces).intersection(phaseb_traces):
        raise MultifamilyArtifactError("Stage 4 and Phase B trial IDs overlap")

    stage4_rows = _aggregate_rows(
        stage4_aggregate,
        label="Stage 4 aggregate",
        expected_schema_version=1,
        expected_rows=48,
        expected_traces=stage4_traces,
    )
    phaseb_rows = _aggregate_rows(
        phaseb_aggregate,
        label="Phase B aggregate",
        expected_schema_version=2,
        expected_rows=104,
        expected_traces=phaseb_traces,
    )
    registry_records, registry_workloads = _validate_registry(
        registry,
        stage4_completion_path=loaded_paths["stage4_completion"],
        stage4_aggregate_path=loaded_paths["stage4_aggregate"],
        root=root,
        stage4_traces=stage4_traces,
    )
    enriched_stage4_rows = _enrich_stage4_rows(
        stage4_rows,
        traces=stage4_traces,
        registry_records=registry_records,
        registry_workloads=registry_workloads,
    )
    normalized_phaseb_rows = _validate_phaseb_rows(phaseb_rows, phaseb_traces)

    computed_stage4_ids = _balanced_record_ids(enriched_stage4_rows)
    computed_phaseb_ids = _balanced_record_ids(normalized_phaseb_rows)
    if computed_stage4_ids != set(stage4_ids):
        raise MultifamilyArtifactError(
            "Stage 4 completion balanced view differs from aggregate predicate"
        )
    if computed_phaseb_ids != set(phaseb_ids):
        raise MultifamilyArtifactError(
            "Phase B completion balanced view differs from aggregate predicate"
        )

    metadata_by_record_id: dict[str, Mapping[str, Any]] = {}
    selected_raw_claims: list[dict[str, Any]] = []
    for family, traces, selected_ids, expected_schema in (
        ("fe4s4", stage4_traces, set(stage4_ids), 2),
        ("phaseb", phaseb_traces, set(phaseb_ids), 3),
    ):
        for trial_id in sorted(traces):
            trace = traces[trial_id]
            raw_path = _verify_raw_claim(
                trace.get("raw_record"),
                root=root,
                raw_dir=raw_dir,
                trial_id=trial_id,
                label=f"{family} raw record {trial_id}",
            )
            raw = _load_json(raw_path, f"{family} raw record {trial_id}")
            _validate_raw_record(
                raw,
                trace=trace,
                expected_schema_version=expected_schema,
                family_scope=family,
            )
            if family == "fe4s4":
                registry_claim = _mapping(
                    registry_records[trial_id].get("raw_record"),
                    f"registry raw claim {trial_id}",
                )
                if dict(registry_claim) != dict(
                    _mapping(trace.get("raw_record"), "completion raw claim")
                ):
                    raise MultifamilyArtifactError(
                        f"registry/completion raw claim mismatch: {trial_id}"
                    )
            if trial_id not in selected_ids:
                continue
            metadata_by_record_id[trial_id] = raw
            raw_claim = _file_claim(raw_path, root)
            selected_raw_claims.append(
                {
                    "family_id": (
                        "fe4s4" if family == "fe4s4" else _required_text(raw.get("family_id"), "raw family_id")
                    ),
                    "trial_id": trial_id,
                    **raw_claim,
                }
            )

    selected_ids = set(stage4_ids) | set(phaseb_ids)
    if len(selected_ids) != EXPECTED_MEASUREMENT_COUNT:
        raise MultifamilyArtifactError("selected source union must contain 90 records")
    if set(metadata_by_record_id) != selected_ids:
        raise MultifamilyArtifactError("selected raw metadata set differs from views")

    combined_aggregate = {
        "rows": enriched_stage4_rows + normalized_phaseb_rows,
    }
    try:
        dataset = build_multifamily_balanced_dataset(
            combined_aggregate,
            metadata_by_record_id=metadata_by_record_id,
        )
        validate_multifamily_dataset(dataset)
        evaluation = evaluate_multifamily_selector(dataset)
        for fold in evaluation["folds"]:
            validate_leave_one_family_out_split(dataset, fold["split"])
    except EvaluationError as error:
        raise MultifamilyArtifactError(
            f"multifamily selector evaluation failed: {error}"
        ) from error
    if set(dataset["source_record_ids"]) != selected_ids:
        raise MultifamilyArtifactError("dataset source IDs differ from attested views")
    if evaluation.get("source_record_ids") != dataset["source_record_ids"]:
        raise MultifamilyArtifactError("evaluation source IDs differ from dataset")

    file_sources = {
        key: _file_claim(loaded_paths[key], root) for key in EXPECTED_SOURCE_KEYS
    }
    selected_raw_claims.sort(
        key=lambda claim: (
            EXPECTED_FAMILY_ORDER.index(str(claim["family_id"])),
            str(claim["trial_id"]),
        )
    )
    source_manifest = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "manifest_type": "autosbd_multifamily_source_manifest",
        "config": {
            "name": config["name"],
            "path": _display_path(config_file, root),
            "sha256": sha256_path(config_file),
            "size_bytes": config_file.stat().st_size,
        },
        "file_sources": file_sources,
        "raw_directory": _display_path(raw_dir, root),
        "selected_views": {
            "stage4_balanced_broad_sensitivity": sorted(stage4_ids),
            "phaseb_balanced_broad": sorted(phaseb_ids),
        },
        "selected_raw_records": selected_raw_claims,
        "source_record_ids": list(dataset["source_record_ids"]),
        "integrity_status": "verified",
    }
    package = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "autosbd_multifamily_evaluation_package",
        "status": "complete",
        "config": source_manifest["config"],
        "sources": {
            **file_sources,
            "raw_directory": source_manifest["raw_directory"],
            "stage4_balanced_record_ids": sorted(stage4_ids),
            "phaseb_balanced_record_ids": sorted(phaseb_ids),
        },
        "source_manifest": source_manifest,
        "environment": {
            "scikit_learn": sklearn.__version__,
            "required_scikit_learn": REQUIRED_SKLEARN_VERSION,
        },
        "claim_boundary": dict(
            _mapping(config.get("claim_boundary"), "claim_boundary")
        ),
        "dataset": dataset,
        "evaluation": evaluation,
    }
    _strict_json_bytes(package)
    return package


def write_multifamily_evaluation_artifacts(
    package: Mapping[str, Any], output_dir: Path
) -> dict[str, Any]:
    """Write the fixed multifamily output set atomically and deterministically."""

    if package.get("status") != "complete":
        raise MultifamilyArtifactError("multifamily evaluation package is not complete")
    if package.get("artifact_type") != "autosbd_multifamily_evaluation_package":
        raise MultifamilyArtifactError("unexpected multifamily package type")
    dataset = _mapping(package.get("dataset"), "dataset")
    evaluation = _mapping(package.get("evaluation"), "evaluation")
    try:
        validate_multifamily_dataset(dataset)
    except EvaluationError as error:
        raise MultifamilyArtifactError(f"invalid multifamily dataset: {error}") from error
    if evaluation.get("evaluation_type") != MULTIFAMILY_EVALUATION_TYPE:
        raise MultifamilyArtifactError("unexpected multifamily evaluation type")
    if evaluation.get("source_record_ids") != dataset.get("source_record_ids"):
        raise MultifamilyArtifactError("package evaluation/dataset source mismatch")
    try:
        recomputed_evaluation = evaluate_multifamily_selector(dataset)
    except EvaluationError as error:
        raise MultifamilyArtifactError(
            f"cannot independently recompute multifamily evaluation: {error}"
        ) from error
    if recomputed_evaluation != evaluation:
        raise MultifamilyArtifactError(
            "package evaluation differs from deterministic recomputation"
        )

    folds = _object_list(evaluation.get("folds"), "evaluation folds")
    if len(folds) != len(EXPECTED_FAMILY_ORDER):
        raise MultifamilyArtifactError("evaluation must contain three family folds")
    for fold in folds:
        try:
            validate_leave_one_family_out_split(
                dataset, _mapping(fold.get("split"), "fold split")
            )
        except EvaluationError as error:
            raise MultifamilyArtifactError(f"invalid family fold: {error}") from error

    try:
        deployment_tree = fit_multifamily_deployment_tree(dataset)
    except EvaluationError as error:
        raise MultifamilyArtifactError(
            f"cannot fit multifamily deployment tree: {error}"
        ) from error
    models = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "config": package["config"],
        "split_type": evaluation["split_type"],
        "deployment_model_scope": {
            "fit_scope": "all_balanced_instances_after_heldout_evaluation",
            "purpose": "deployment_selection_and_inference_overhead_only",
            "used_for_heldout_metrics": False,
            "training_instance_count": EXPECTED_INSTANCE_COUNT,
            "training_source_record_count": EXPECTED_MEASUREMENT_COUNT,
        },
        "deployment_models": {POLICY_FULL_TREE: deployment_tree},
        "folds": [
            {
                "split_name": fold["split"]["name"],
                "heldout_family_id": fold["split"]["heldout_family_id"],
                "training_source_record_ids": fold["training_source_record_ids"],
                "models": fold["models"],
            }
            for fold in folds
        ],
    }
    splits = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "config": package["config"],
        "split_type": evaluation["split_type"],
        "source_record_ids": dataset["source_record_ids"],
        "folds": [fold["split"] for fold in folds],
        "leakage_check": "PASS",
    }
    prediction_rows = _prediction_rows(evaluation)
    summary_rows = _summary_rows(evaluation)
    ablation_rows = [
        row
        for row in summary_rows
        if row["policy"] in (POLICY_THRESHOLD, POLICY_SIZE_TREE, POLICY_FULL_TREE)
    ]
    policy_summary = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "config": package["config"],
        "policy_aliases": evaluation["policy_aliases"],
        "rows": summary_rows,
    }

    prediction_fields = (
        "fold_id",
        "heldout_family_id",
        "policy",
        "family_id",
        "molecule",
        "basis",
        "basis_status",
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
    )
    summary_fields = tuple(summary_rows[0])
    payloads: dict[str, bytes] = {
        "source_manifest.json": _strict_json_bytes(package["source_manifest"]),
        "balanced_dataset.json": _strict_json_bytes(dict(dataset)),
        "split_manifest.json": _strict_json_bytes(splits),
        "models.json": _strict_json_bytes(models),
        "evaluation.json": _strict_json_bytes(dict(package)),
        "policy_predictions.csv": _csv_bytes(prediction_rows, prediction_fields),
        "policy_summary.json": _strict_json_bytes(policy_summary),
        "policy_summary.csv": _csv_bytes(summary_rows, summary_fields),
        "selector_ablation.csv": _csv_bytes(ablation_rows, summary_fields),
    }

    output = Path(output_dir)
    if output.is_symlink():
        raise MultifamilyArtifactError(f"output directory must not be a symlink: {output}")
    output.mkdir(parents=True, exist_ok=True)
    if not output.is_dir():
        raise MultifamilyArtifactError(f"output path is not a directory: {output}")
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
        "balanced_measurements": dataset["record_counts"]["selected_measurements"],
        "candidate_rows": dataset["record_counts"]["candidate_rows"],
        "problem_instances": dataset["record_counts"]["problem_instances"],
        "family_folds": len(folds),
    }


def build_and_write_multifamily_evaluation(
    config_path: Path,
    output_dir: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Build the verified package and write its deterministic output set."""

    package = build_multifamily_evaluation_package(
        config_path, repository_root=repository_root
    )
    return write_multifamily_evaluation_artifacts(package, output_dir)


def _validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema_version") != 1 or config.get("name") != EXPECTED_CONFIG_NAME:
        raise MultifamilyArtifactError("unexpected multifamily config identity")
    sources = _mapping(config.get("sources"), "sources")
    expected_source_keys = set(EXPECTED_SOURCE_KEYS) | {EXPECTED_RAW_DIRECTORY_KEY}
    if set(sources) != expected_source_keys:
        raise MultifamilyArtifactError("multifamily config source keys differ")
    for key in EXPECTED_SOURCE_KEYS:
        _validate_config_source_claim_shape(sources.get(key), f"config source {key}")
    _required_text(sources.get(EXPECTED_RAW_DIRECTORY_KEY), "raw_directory")

    dataset = _mapping(config.get("dataset"), "dataset")
    expected_dataset = {
        "stage4_source_view": "balanced_broad_sensitivity",
        "phaseb_source_view": "balanced_broad",
        "family_order": list(EXPECTED_FAMILY_ORDER),
        "phase": "measured",
        "purpose": "final",
        "repetitions": list(BALANCED_REPETITIONS),
        "expected_measurements": EXPECTED_MEASUREMENT_COUNT,
        "expected_candidate_rows": EXPECTED_CANDIDATE_ROW_COUNT,
        "expected_problem_instances": EXPECTED_INSTANCE_COUNT,
        "expected_instances_per_family": EXPECTED_INSTANCE_COUNT_PER_FAMILY,
        "expected_candidates_per_instance": len(EXPECTED_CANDIDATES),
        "pilot_records_allowed": False,
        "post_execution_selection_features_allowed": False,
    }
    _require_expected_values(dataset, expected_dataset, "dataset")

    splits = _mapping(config.get("splits"), "splits")
    expected_splits = {
        "primary_type": "leave_one_chemistry_family_out",
        "folds": len(EXPECTED_FAMILY_ORDER),
        "group_key": "family_id_and_instance_id",
        "all_candidates_and_repetitions_stay_together": True,
    }
    _require_expected_values(splits, expected_splits, "splits")

    model = _mapping(config.get("model"), "model")
    expected_model = {
        "implementation": "sklearn.tree.DecisionTreeRegressor",
        "sklearn_version": REQUIRED_SKLEARN_VERSION,
        "max_depth": MULTIFAMILY_TREE_MAX_DEPTH,
        "min_samples_leaf": MULTIFAMILY_TREE_MIN_SAMPLES_LEAF,
        "random_state": TREE_RANDOM_STATE,
        "heldout_hyperparameter_tuning": False,
        "full_features": list(FULL_FEATURE_NAMES),
        "size_only_ablation_features": list(SIZE_ONLY_FEATURE_NAMES),
    }
    _require_expected_values(model, expected_model, "model")
    if sklearn.__version__ != REQUIRED_SKLEARN_VERSION:
        raise MultifamilyArtifactError(
            f"scikit-learn must be {REQUIRED_SKLEARN_VERSION}, got {sklearn.__version__}"
        )
    if config.get("policies") != list(POLICY_ORDER):
        raise MultifamilyArtifactError("policy order does not match evaluator")
    if config.get("policy_aliases") != {"upstream_default": "fixed_gpu"}:
        raise MultifamilyArtifactError("upstream-default alias must equal fixed GPU")
    boundary = _mapping(config.get("claim_boundary"), "claim_boundary")
    if boundary.get("universal_generalization_claim_allowed") is not False:
        raise MultifamilyArtifactError("universal generalization claim must be disabled")
    if boundary.get("multi_node_claim_allowed") is not False:
        raise MultifamilyArtifactError("multi-node claim must be disabled")


def _validate_protocols(
    stage4_protocol: Mapping[str, Any], phaseb_protocol: Mapping[str, Any]
) -> None:
    if stage4_protocol.get("schema_version") != 1:
        raise MultifamilyArtifactError("unexpected Stage 4 protocol schema")
    if stage4_protocol.get("status") != "frozen_before_measurement":
        raise MultifamilyArtifactError("Stage 4 protocol is not frozen")
    if phaseb_protocol.get("schema_version") != 1:
        raise MultifamilyArtifactError("unexpected Phase B protocol schema")
    if phaseb_protocol.get("name") != "phaseb-amd-n2-h2o-grid-final-v1":
        raise MultifamilyArtifactError("unexpected Phase B protocol identity")
    if phaseb_protocol.get("status") != "frozen_before_measurement":
        raise MultifamilyArtifactError("Phase B protocol is not frozen")
    if _nested(phaseb_protocol, "protocol", "purpose") != "final":
        raise MultifamilyArtifactError("Phase B protocol purpose is not final")
    scope = _mapping(phaseb_protocol.get("scope"), "Phase B scope")
    if (
        scope.get("upstream_git_commit") != EXPECTED_UPSTREAM_COMMIT
        or scope.get("official_primary_only") is not True
        or scope.get("distinct_chemistry_families") != ["n2", "h2o"]
    ):
        raise MultifamilyArtifactError("Phase B official-upstream scope differs")
    if _nested(phaseb_protocol, "analysis_views", "balanced_broad", "repetitions") != list(
        BALANCED_REPETITIONS
    ):
        raise MultifamilyArtifactError("Phase B balanced repetitions differ")


def _validate_completion(
    completion: Mapping[str, Any],
    *,
    label: str,
    completion_type: str,
    protocol_path: Path,
    aggregate_path: Path,
    root: Path,
    expected_counts: Mapping[str, int],
    view_name: str,
    expected_view_records: int,
) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    if completion.get("schema_version") != 1:
        raise MultifamilyArtifactError(f"unexpected {label} schema")
    if completion.get("status") != "complete":
        raise MultifamilyArtifactError(f"{label} is not complete")
    if completion.get("attestation_type") != completion_type:
        raise MultifamilyArtifactError(f"unexpected {label} type")
    source_artifacts = _mapping(
        completion.get("source_artifacts"), f"{label} source_artifacts"
    )
    _require_embedded_file_claim(
        source_artifacts.get("protocol"), protocol_path, root, f"{label} protocol"
    )
    _require_embedded_file_claim(
        source_artifacts.get("aggregate"), aggregate_path, root, f"{label} aggregate"
    )
    counts = _mapping(completion.get("campaign_counts"), f"{label} counts")
    _require_expected_values(counts, expected_counts, f"{label} counts")

    records = _object_list(completion.get("records"), f"{label} records")
    if len(records) != expected_counts["records"]:
        raise MultifamilyArtifactError(f"{label} record trace count differs")
    trace_by_id: dict[str, Mapping[str, Any]] = {}
    for trace in records:
        trial_id = _required_digest(trace.get("trial_id"), f"{label} trial_id")
        if trial_id in trace_by_id:
            raise MultifamilyArtifactError(f"duplicate {label} trial ID: {trial_id}")
        _required_digest(trace.get("logical_trial_id"), f"{label} logical_trial_id")
        _validate_file_claim_shape(trace.get("raw_record"), f"{label} raw_record")
        trace_by_id[trial_id] = trace

    view = _mapping(
        _nested(completion, "analysis_views", view_name), f"{label} {view_name} view"
    )
    view_ids = _string_list(view.get("record_ids"), f"{label} balanced record IDs")
    if len(view_ids) != expected_view_records:
        raise MultifamilyArtifactError(f"{label} balanced view count differs")
    if "record_count" in view and view.get("record_count") != len(view_ids):
        raise MultifamilyArtifactError(f"{label} balanced view count differs")
    if not set(view_ids).issubset(trace_by_id):
        raise MultifamilyArtifactError(f"{label} balanced view contains untraced IDs")
    return trace_by_id, view_ids


def _aggregate_rows(
    aggregate: Mapping[str, Any],
    *,
    label: str,
    expected_schema_version: int,
    expected_rows: int,
    expected_traces: Mapping[str, Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if aggregate.get("schema_version") != expected_schema_version:
        raise MultifamilyArtifactError(f"unexpected {label} schema")
    if aggregate.get("analysis_type") != "autosbd_timing_aggregation":
        raise MultifamilyArtifactError(f"unexpected {label} type")
    rows = _object_list(aggregate.get("rows"), f"{label} rows")
    if len(rows) != expected_rows:
        raise MultifamilyArtifactError(f"{label} row count differs")
    row_ids: list[str] = []
    for row in rows:
        trial_id = _required_digest(row.get("trial_id"), f"{label} row trial_id")
        row_ids.append(trial_id)
    if len(set(row_ids)) != len(row_ids):
        raise MultifamilyArtifactError(f"{label} contains duplicate trial IDs")
    if set(row_ids) != set(expected_traces):
        raise MultifamilyArtifactError(f"{label}/completion trial-ID sets differ")
    input_record_ids = _string_list(
        aggregate.get("input_record_ids"), f"{label} input_record_ids"
    )
    if set(input_record_ids) != set(row_ids):
        raise MultifamilyArtifactError(f"{label} input record IDs differ from rows")
    counts = _mapping(aggregate.get("record_counts"), f"{label} record_counts")
    if counts.get("input") != expected_rows:
        raise MultifamilyArtifactError(f"{label} input count differs")
    return rows


def _validate_registry(
    registry: Mapping[str, Any],
    *,
    stage4_completion_path: Path,
    stage4_aggregate_path: Path,
    root: Path,
    stage4_traces: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], dict[tuple[str, str], Mapping[str, Any]]]:
    if registry.get("schema_version") != 1:
        raise MultifamilyArtifactError("unexpected Fe4S4 registry schema")
    if registry.get("registry_type") != EXPECTED_REGISTRY_TYPE:
        raise MultifamilyArtifactError("unexpected Fe4S4 registry type")
    if registry.get("status") != "complete":
        raise MultifamilyArtifactError("Fe4S4 registry is not complete")
    family = _mapping(registry.get("family"), "registry family")
    expected_family = EXPECTED_FAMILY_PROVENANCE["fe4s4"]
    _require_expected_values(
        family,
        {"family_id": "fe4s4", **expected_family},
        "registry family",
    )
    counts = _mapping(registry.get("record_counts"), "registry record_counts")
    _require_expected_values(
        counts, {"raw_records": 48, "workload_entries": 5}, "registry counts"
    )
    sources = _mapping(registry.get("sources"), "registry sources")
    _require_embedded_file_claim(
        sources.get("stage4_completion"),
        stage4_completion_path,
        root,
        "registry Stage 4 completion",
    )
    _require_embedded_file_claim(
        sources.get("stage4_aggregate"),
        stage4_aggregate_path,
        root,
        "registry Stage 4 aggregate",
    )
    contract = _mapping(registry.get("augmentation_contract"), "registry contract")
    _require_expected_values(
        contract,
        {
            "lookup_key": ["problem_instance", "input_sha256"],
            "mode": "external_metadata_only",
            "raw_records_modified": False,
            "raw_trial_ids_modified": False,
        },
        "registry contract",
    )

    workloads = _object_list(registry.get("workloads"), "registry workloads")
    if len(workloads) != 5:
        raise MultifamilyArtifactError("registry must contain five workloads")
    workload_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    workload_source_ids: set[str] = set()
    for workload in workloads:
        problem = _required_text(
            workload.get("problem_instance"), "registry workload problem_instance"
        )
        input_sha = _required_digest(
            workload.get("input_sha256"), "registry workload input_sha256"
        )
        key = (problem, input_sha)
        if key in workload_by_key:
            raise MultifamilyArtifactError(f"duplicate registry workload: {key!r}")
        _require_expected_values(
            workload,
            {"family_id": "fe4s4", **expected_family},
            f"registry workload {problem}",
        )
        source_ids = _string_list(
            workload.get("source_record_ids"), f"registry workload {problem} sources"
        )
        if workload.get("source_record_count") != len(source_ids):
            raise MultifamilyArtifactError(f"registry workload source count differs: {problem}")
        overlap = workload_source_ids.intersection(source_ids)
        if overlap:
            raise MultifamilyArtifactError(
                f"registry source IDs reused across workloads: {sorted(overlap)}"
            )
        workload_source_ids.update(source_ids)
        _nonnegative_int(workload.get("n_configurations"), "registry n_configurations")
        components = _mapping(workload.get("components"), "registry components")
        for component in ("fcidump", "alpha_determinants", "beta_determinants"):
            _validate_file_claim_shape(
                components.get(component), f"registry component {component}"
            )
        workload_by_key[key] = workload
    if workload_source_ids != set(stage4_traces):
        raise MultifamilyArtifactError("registry workload sources differ from completion")

    records = _object_list(registry.get("records"), "registry records")
    if len(records) != 48:
        raise MultifamilyArtifactError("registry must trace 48 records")
    record_by_id: dict[str, Mapping[str, Any]] = {}
    for record in records:
        trial_id = _required_digest(record.get("trial_id"), "registry trial_id")
        if trial_id in record_by_id:
            raise MultifamilyArtifactError(f"duplicate registry trial ID: {trial_id}")
        trace = stage4_traces.get(trial_id)
        if trace is None:
            raise MultifamilyArtifactError(f"registry trial is not in completion: {trial_id}")
        problem = _required_text(record.get("problem_instance"), "registry problem")
        input_sha = _required_digest(record.get("input_sha256"), "registry input SHA")
        workload = workload_by_key.get((problem, input_sha))
        if workload is None or trial_id not in workload["source_record_ids"]:
            raise MultifamilyArtifactError(f"registry trial/workload mismatch: {trial_id}")
        if (
            record.get("logical_trial_id") != trace.get("logical_trial_id")
            or problem != trace.get("problem_instance")
            or input_sha != trace.get("input_sha256")
            or record.get("entry_id") != workload.get("entry_id")
        ):
            raise MultifamilyArtifactError(f"registry/completion identity mismatch: {trial_id}")
        if dict(_mapping(record.get("raw_record"), "registry raw_record")) != dict(
            _mapping(trace.get("raw_record"), "completion raw_record")
        ):
            raise MultifamilyArtifactError(f"registry raw claim mismatch: {trial_id}")
        record_by_id[trial_id] = record
    if set(record_by_id) != set(stage4_traces):
        raise MultifamilyArtifactError("registry/completion record sets differ")
    return record_by_id, workload_by_key


def _enrich_stage4_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    traces: Mapping[str, Mapping[str, Any]],
    registry_records: Mapping[str, Mapping[str, Any]],
    registry_workloads: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    provenance = {"family_id": "fe4s4", **EXPECTED_FAMILY_PROVENANCE["fe4s4"]}
    for row in rows:
        trial_id = _required_digest(row.get("trial_id"), "Stage 4 row trial_id")
        trace = traces[trial_id]
        registry_record = registry_records[trial_id]
        problem = _required_text(row.get("problem_instance"), "Stage 4 problem")
        input_sha = _required_digest(row.get("input_sha256"), "Stage 4 input SHA")
        workload = registry_workloads.get((problem, input_sha))
        if workload is None:
            raise MultifamilyArtifactError(f"Stage 4 row lacks registry workload: {trial_id}")
        _validate_row_against_trace(row, trace, family_scope="fe4s4")
        if (
            registry_record.get("problem_instance") != problem
            or registry_record.get("input_sha256") != input_sha
        ):
            raise MultifamilyArtifactError(f"Stage 4 registry row mismatch: {trial_id}")
        features = _mapping(row.get("features"), "Stage 4 row features")
        if (
            features.get("combined_input_sha256") != input_sha
            or features.get("n_configurations") != workload.get("n_configurations")
            or _nested(features, "fcidump", "sha256")
            != _nested(workload, "components", "fcidump", "sha256")
            or _nested(features, "alpha", "sha256")
            != _nested(workload, "components", "alpha_determinants", "sha256")
            or _nested(features, "beta", "sha256")
            != _nested(workload, "components", "beta_determinants", "sha256")
        ):
            raise MultifamilyArtifactError(f"Stage 4 registry component mismatch: {trial_id}")
        for field, expected in provenance.items():
            if field in row and row.get(field) != expected:
                raise MultifamilyArtifactError(
                    f"Stage 4 row has conflicting {field}: {trial_id}"
                )
        copy = deepcopy(dict(row))
        copy.update(provenance)
        enriched.append(copy)
    return enriched


def _validate_phaseb_rows(
    rows: Sequence[Mapping[str, Any]],
    traces: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {"n2": 0, "h2o": 0}
    for row in rows:
        trial_id = _required_digest(row.get("trial_id"), "Phase B row trial_id")
        trace = traces[trial_id]
        _validate_row_against_trace(row, trace, family_scope="phaseb")
        family_id = _required_text(row.get("family_id"), "Phase B family_id")
        if family_id not in family_counts:
            raise MultifamilyArtifactError(f"unexpected Phase B family: {family_id}")
        expected = EXPECTED_FAMILY_PROVENANCE[family_id]
        basis_status = row.get("basis_status")
        if basis_status is None:
            basis_status = "reported"
        if (
            row.get("molecule") != expected["molecule"]
            or row.get("basis") != expected["basis"]
            or basis_status != expected["basis_status"]
        ):
            raise MultifamilyArtifactError(
                f"Phase B family provenance mismatch: {trial_id}"
            )
        family_counts[family_id] += 1
        copy = deepcopy(dict(row))
        copy["basis_status"] = basis_status
        normalized.append(copy)
    if family_counts != {"n2": 52, "h2o": 52}:
        raise MultifamilyArtifactError("Phase B family record counts differ")
    return normalized


def _validate_row_against_trace(
    row: Mapping[str, Any],
    trace: Mapping[str, Any],
    *,
    family_scope: str,
) -> None:
    trial_id = str(row.get("trial_id"))
    for field in (
        "trial_id",
        "logical_trial_id",
        "problem_instance",
        "input_sha256",
        "phase",
        "repetition",
    ):
        if row.get(field) != trace.get(field):
            raise MultifamilyArtifactError(
                f"{family_scope} aggregate/completion {field} mismatch: {trial_id}"
            )
    row_candidate = _mapping(row.get("candidate"), "aggregate candidate")
    trace_candidate_value = trace.get("candidate")
    if isinstance(trace_candidate_value, Mapping):
        for field in ("name", "backend", "cpu_threads"):
            if row_candidate.get(field) != trace_candidate_value.get(field):
                raise MultifamilyArtifactError(
                    f"{family_scope} aggregate/completion candidate mismatch: {trial_id}"
                )
    elif row_candidate.get("name") != trace.get("candidate_name"):
        raise MultifamilyArtifactError(
            f"{family_scope} aggregate/completion candidate mismatch: {trial_id}"
        )
    _validate_candidate(row_candidate, f"{family_scope} candidate {trial_id}")
    phase = row.get("phase")
    if phase not in ("warmup", "measured"):
        raise MultifamilyArtifactError(f"invalid aggregate phase: {trial_id}")
    repetition = _nonnegative_int(row.get("repetition"), "aggregate repetition")
    if repetition > 4:
        raise MultifamilyArtifactError(f"unexpected aggregate repetition: {trial_id}")
    if not isinstance(row.get("included"), bool):
        raise MultifamilyArtifactError(f"aggregate included must be boolean: {trial_id}")
    expected_included = phase == "measured" and trace.get("timing_eligible") is True
    if family_scope == "fe4s4":
        expected_included = (
            expected_included
            and trace.get("status") == "success"
            and trace.get("correct") is True
        )
    if row.get("included") is not expected_included:
        raise MultifamilyArtifactError(
            f"aggregate inclusion disagrees with completion gates: {trial_id}"
        )
    if family_scope == "phaseb" and row.get("family_id") != trace.get("family_id"):
        raise MultifamilyArtifactError(
            f"Phase B aggregate/completion family_id mismatch: {trial_id}"
        )


def _balanced_record_ids(rows: Sequence[Mapping[str, Any]]) -> set[str]:
    return {
        _required_digest(row.get("trial_id"), "balanced trial_id")
        for row in rows
        if row.get("included") is True
        and row.get("phase") == "measured"
        and row.get("repetition") in BALANCED_REPETITIONS
    }


def _validate_raw_record(
    raw: Mapping[str, Any],
    *,
    trace: Mapping[str, Any],
    expected_schema_version: int,
    family_scope: str,
) -> None:
    trial_id = _required_digest(trace.get("trial_id"), "trace trial_id")
    if raw.get("schema_version") != expected_schema_version:
        raise MultifamilyArtifactError(f"raw schema mismatch: {trial_id}")
    for raw_field, trace_field in (
        ("trial_id", "trial_id"),
        ("logical_trial_id", "logical_trial_id"),
        ("problem_instance", "problem_instance"),
        ("input_sha256", "input_sha256"),
        ("repetition", "repetition"),
        ("timing_eligible", "timing_eligible"),
    ):
        if raw.get(raw_field) != trace.get(trace_field):
            raise MultifamilyArtifactError(
                f"raw/completion {raw_field} mismatch: {trial_id}"
            )
    if raw.get("warmup_or_measured") != trace.get("phase"):
        raise MultifamilyArtifactError(f"raw/completion phase mismatch: {trial_id}")
    if raw.get("status") != "success" or raw.get("correct") is not True:
        raise MultifamilyArtifactError(f"raw success/correctness gate failed: {trial_id}")
    if "status" in trace and raw.get("status") != trace.get("status"):
        raise MultifamilyArtifactError(f"raw/completion status mismatch: {trial_id}")
    if "correct" in trace and raw.get("correct") != trace.get("correct"):
        raise MultifamilyArtifactError(f"raw/completion correctness mismatch: {trial_id}")
    protocol = _mapping(raw.get("protocol"), f"raw protocol {trial_id}")
    if protocol.get("purpose") != "final" or protocol.get("correctness_validated") is not True:
        raise MultifamilyArtifactError(f"raw protocol is not final/correct: {trial_id}")
    logical = _mapping(raw.get("logical_identity"), f"raw logical_identity {trial_id}")
    logical_protocol = _mapping(
        logical.get("protocol"), f"raw logical protocol {trial_id}"
    )
    if (
        logical.get("phase") != trace.get("phase")
        or logical.get("repetition") != trace.get("repetition")
        or logical.get("input_sha256") != trace.get("input_sha256")
        or logical_protocol.get("purpose") != "final"
        or logical.get("upstream_commit") != EXPECTED_UPSTREAM_COMMIT
        or raw.get("upstream_git_commit") != EXPECTED_UPSTREAM_COMMIT
        or raw.get("official_upstream_primary") is not True
    ):
        raise MultifamilyArtifactError(f"raw official identity mismatch: {trial_id}")
    raw_candidate = _mapping(logical.get("candidate"), f"raw candidate {trial_id}")
    trace_candidate_value = trace.get("candidate")
    if isinstance(trace_candidate_value, Mapping):
        trace_candidate_name = trace_candidate_value.get("name")
        trace_candidate_backend = trace_candidate_value.get("backend")
    else:
        trace_candidate_name = trace.get("candidate_name")
        trace_candidate_backend = EXPECTED_CANDIDATES.get(
            str(trace_candidate_name), (None, 0)
        )[0]
    if (
        raw_candidate.get("name") != trace_candidate_name
        or raw_candidate.get("backend") != trace_candidate_backend
    ):
        raise MultifamilyArtifactError(f"raw candidate mismatch: {trial_id}")
    if trace_candidate_name not in EXPECTED_CANDIDATES:
        raise MultifamilyArtifactError(f"unexpected trace candidate: {trial_id}")
    expected_backend, expected_threads = EXPECTED_CANDIDATES[trace_candidate_name]
    if (
        raw_candidate.get("backend") != expected_backend
        or raw_candidate.get("threads") != expected_threads
    ):
        raise MultifamilyArtifactError(f"raw candidate contract mismatch: {trial_id}")
    if family_scope == "phaseb":
        family_id = _required_text(trace.get("family_id"), "Phase B trace family_id")
        if family_id not in ("n2", "h2o"):
            raise MultifamilyArtifactError(f"unexpected Phase B family: {trial_id}")
        expected_provenance = EXPECTED_FAMILY_PROVENANCE[family_id]
        for field, expected in (
            ("family_id", family_id),
            ("molecule", expected_provenance["molecule"]),
            ("basis", expected_provenance["basis"]),
        ):
            if raw.get(field) != expected or logical.get(field) != expected:
                raise MultifamilyArtifactError(
                    f"Phase B raw authentic {field} mismatch: {trial_id}"
                )
        if logical.get("sweep_name") != "phaseb-amd-n2-h2o-grid-final-v1":
            raise MultifamilyArtifactError(f"Phase B sweep identity mismatch: {trial_id}")
    elif logical.get("sweep_name") != "stage4-amd-fe4s4-final-v1":
        raise MultifamilyArtifactError(f"Stage 4 sweep identity mismatch: {trial_id}")


def _validate_candidate(candidate: Mapping[str, Any], label: str) -> None:
    name = _required_text(candidate.get("name"), f"{label} name")
    if name not in EXPECTED_CANDIDATES:
        raise MultifamilyArtifactError(f"unexpected candidate {name!r}")
    backend, threads = EXPECTED_CANDIDATES[name]
    if candidate.get("backend") != backend or candidate.get("cpu_threads") != threads:
        raise MultifamilyArtifactError(f"{label} backend/thread contract differs")


def _prediction_rows(evaluation: Mapping[str, Any]) -> list[dict[str, Any]]:
    fold_by_family = {
        fold["split"]["heldout_family_id"]: fold["split"]["name"]
        for fold in _object_list(evaluation.get("folds"), "evaluation folds")
    }
    rows: list[dict[str, Any]] = []
    for prediction in _object_list(evaluation.get("predictions"), "predictions"):
        family_id = _required_text(prediction.get("family_id"), "prediction family_id")
        rows.append(
            {
                "fold_id": fold_by_family[family_id],
                "heldout_family_id": family_id,
                **dict(prediction),
            }
        )
    return rows


def _summary_rows(evaluation: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    global_metrics = _mapping(evaluation.get("metrics"), "global metrics")
    for policy in POLICY_ORDER:
        rows.append(_summary_row("pooled", None, policy, global_metrics.get(policy)))
    per_family = _mapping(
        evaluation.get("per_heldout_family_metrics"), "per-family metrics"
    )
    for family_id in EXPECTED_FAMILY_ORDER:
        metrics = _mapping(per_family.get(family_id), f"metrics for {family_id}")
        for policy in POLICY_ORDER:
            rows.append(_summary_row("heldout_family", family_id, policy, metrics.get(policy)))
    return rows


def _summary_row(
    scope: str, family_id: str | None, policy: str, value: Any
) -> dict[str, Any]:
    metrics = _mapping(value, f"metrics for {scope}/{policy}")
    return {
        "scope": scope,
        "heldout_family_id": family_id,
        "policy": policy,
        "requested_instances": metrics.get("instances_total"),
        "valid_instances": metrics.get("valid_instances"),
        "invalid_instances": metrics.get("invalid_instances"),
        "failure_instances": metrics.get("failure_count"),
        "selection_accuracy": metrics.get("selection_accuracy"),
        "within_5pct_oracle_rate": metrics.get("within_5pct_oracle_rate"),
        "invalid_rate": metrics.get("invalid_rate"),
        "failure_rate": metrics.get("failure_rate"),
        "geometric_mean_selected_over_oracle_valid_only": metrics.get(
            "geometric_mean_selected_over_oracle_valid_only"
        ),
        "geometric_mean_speedup_vs_oracle_inverse_valid_only": metrics.get(
            "geometric_mean_oracle_over_selected_valid_only"
        ),
        "median_normalized_regret_valid_only": metrics.get(
            "median_normalized_regret_valid_only"
        ),
        "p90_normalized_regret_valid_only": metrics.get(
            "p90_normalized_regret_valid_only"
        ),
        "maximum_normalized_regret_valid_only": metrics.get(
            "maximum_normalized_regret_valid_only"
        ),
        "geometric_mean_speedup_vs_fixed_cpu_valid_only": metrics.get(
            "geometric_mean_speedup_vs_fixed_cpu_valid_only"
        ),
        "geometric_mean_speedup_vs_fixed_gpu_valid_only": metrics.get(
            "geometric_mean_speedup_vs_fixed_gpu_valid_only"
        ),
    }


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
    claim = _validate_config_source_claim_shape(value, f"{label} claim")
    path = _resolve_inside(root, claim.get("path"), label)
    if not path.is_file():
        raise MultifamilyArtifactError(f"{label} is not a regular file")
    if sha256_path(path) != claim["sha256"]:
        raise MultifamilyArtifactError(f"{label} SHA mismatch")
    return path, _load_json(path, label)


def _verify_raw_claim(
    value: Any,
    *,
    root: Path,
    raw_dir: Path,
    trial_id: str,
    label: str,
) -> Path:
    claim = _validate_file_claim_shape(value, f"{label} claim")
    path = _resolve_inside(root, claim["path"], label)
    expected = (raw_dir / f"{trial_id}.json").resolve(strict=True)
    if path != expected or path.parent != raw_dir:
        raise MultifamilyArtifactError(f"{label} path does not match trial ID")
    if not path.is_file():
        raise MultifamilyArtifactError(f"{label} is not a regular file")
    if sha256_path(path) != claim["sha256"]:
        raise MultifamilyArtifactError(f"{label} SHA mismatch")
    if path.stat().st_size != claim["size_bytes"]:
        raise MultifamilyArtifactError(f"{label} size mismatch")
    return path


def _validate_file_claim_shape(value: Any, label: str) -> Mapping[str, Any]:
    claim = _mapping(value, label)
    if set(claim) != {"path", "sha256", "size_bytes"}:
        raise MultifamilyArtifactError(f"{label} fields differ")
    _required_text(claim.get("path"), f"{label} path")
    _required_digest(claim.get("sha256"), f"{label} sha256")
    size = _nonnegative_int(claim.get("size_bytes"), f"{label} size_bytes")
    if size == 0:
        raise MultifamilyArtifactError(f"{label} size_bytes must be positive")
    return claim


def _validate_config_source_claim_shape(
    value: Any, label: str
) -> Mapping[str, Any]:
    claim = _mapping(value, label)
    if set(claim) != {"path", "sha256"}:
        raise MultifamilyArtifactError(f"{label} fields differ")
    _required_text(claim.get("path"), f"{label} path")
    _required_digest(claim.get("sha256"), f"{label} sha256")
    return claim


def _require_embedded_file_claim(
    value: Any, path: Path, root: Path, label: str
) -> None:
    claim = _validate_file_claim_shape(value, label)
    expected = _file_claim(path, root)
    if dict(claim) != expected:
        raise MultifamilyArtifactError(f"{label} claim mismatch")


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueSafeLoader)
    except (OSError, UnicodeError, yaml.YAMLError, MultifamilyArtifactError) as error:
        raise MultifamilyArtifactError(
            f"cannot load multifamily config: {error}"
        ) from error
    if not isinstance(value, dict):
        raise MultifamilyArtifactError("multifamily config must be an object")
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
        raise MultifamilyArtifactError(f"cannot load {label}: {error}") from error
    if not isinstance(value, dict):
        raise MultifamilyArtifactError(f"{label} must be an object")
    return value


def _strict_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise MultifamilyArtifactError(f"artifact is not strict JSON: {error}") from error


def _atomic_write_changed(path: Path, payload: bytes) -> bool:
    if path.is_symlink():
        raise MultifamilyArtifactError(f"output must not be a symlink: {path}")
    if path.exists():
        if not path.is_file() or path.is_symlink():
            raise MultifamilyArtifactError(f"output is not a regular file: {path}")
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


def _existing_file_inside(path: Path, root: Path, label: str) -> Path:
    candidate = path if path.is_absolute() else (Path.cwd() / path)
    try:
        relative = candidate.absolute().relative_to(root)
    except ValueError as error:
        raise MultifamilyArtifactError(f"{label} must be inside repository") from error
    resolved = _resolve_inside(root, relative.as_posix(), label)
    if not resolved.is_file():
        raise MultifamilyArtifactError(f"{label} is not a regular file")
    return resolved


def _resolve_inside(root: Path, value: Any, label: str) -> Path:
    text = _required_text(value, f"{label} path")
    relative = Path(text)
    if relative.is_absolute() or ".." in relative.parts:
        raise MultifamilyArtifactError(f"{label} path must be repository-relative")
    current = root
    for part in relative.parts:
        if part in ("", "."):
            continue
        current = current / part
        if current.is_symlink():
            raise MultifamilyArtifactError(f"{label} path must not use symlinks")
    try:
        resolved = (root / relative).resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise MultifamilyArtifactError(f"cannot resolve {label}: {error}") from error
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
        raise MultifamilyArtifactError(f"{label} must be an object")
    return value


def _object_list(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise MultifamilyArtifactError(f"{label} must be a list of objects")
    return list(value)


def _nested(mapping: Any, *keys: str) -> Any:
    value = mapping
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            raise MultifamilyArtifactError(f"missing field: {'.'.join(keys)}")
        value = value[key]
    return value


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise MultifamilyArtifactError(f"{label} must be nonempty trimmed text")
    return value


def _required_digest(value: Any, label: str) -> str:
    text = _required_text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise MultifamilyArtifactError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MultifamilyArtifactError(f"{label} must be a nonnegative integer")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise MultifamilyArtifactError(f"{label} must be a string list")
    if len(value) != len(set(value)):
        raise MultifamilyArtifactError(f"{label} contains duplicates")
    return list(value)


def _require_expected_values(
    mapping: Mapping[str, Any], expected: Mapping[str, Any], label: str
) -> None:
    for key, value in expected.items():
        if mapping.get(key) != value:
            raise MultifamilyArtifactError(f"{label} mismatch: {key}")


__all__ = [
    "MultifamilyArtifactError",
    "build_and_write_multifamily_evaluation",
    "build_multifamily_evaluation_package",
    "sha256_path",
    "write_multifamily_evaluation_artifacts",
]
