"""Pure, leakage-safe evaluation across the three authentic SBD families.

This module deliberately performs no file discovery or writes.  Callers supply
already family-enriched aggregation rows and immutable raw-record metadata.  A
balanced view uses measured repetitions 0, 1, and 2 only, forms one median row
per family/workload/candidate, and then evaluates deterministic leave-one-family-
out folds.  Family identity and chemistry metadata are provenance and grouping
fields only; they never enter a model feature vector.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
import json
import math
from typing import Any

import sklearn
from sklearn.tree import DecisionTreeRegressor

from .evaluation import (
    BALANCED_REPETITIONS,
    CPU_CANDIDATE,
    EVALUATION_SCHEMA_VERSION,
    EXPECTED_CANDIDATES,
    FULL_FEATURE_NAMES,
    GPU_CANDIDATE,
    POLICY_FIXED_CPU,
    POLICY_FIXED_GPU,
    POLICY_FULL_TREE,
    POLICY_ORACLE,
    POLICY_ORDER,
    POLICY_SIZE_TREE,
    POLICY_THRESHOLD,
    POLICY_UPSTREAM_DEFAULT,
    REQUIRED_SKLEARN_VERSION,
    SIZE_ONLY_FEATURE_NAMES,
    TREE_RANDOM_STATE,
    EvaluationError,
    build_balanced_dataset,
    candidate_is_feasible,
    fit_static_threshold,
    normalized_regret,
    select_with_static_threshold,
    select_with_tree,
    summarize_policy_predictions,
)


MULTIFAMILY_DATASET_TYPE = "autosbd_multifamily_balanced_candidate_medians"
MULTIFAMILY_EVALUATION_TYPE = "autosbd_leave_one_family_out_evaluation"
MULTIFAMILY_TREE_MAX_DEPTH = 3
MULTIFAMILY_TREE_MIN_SAMPLES_LEAF = 2
EXPECTED_INSTANCE_COUNT_PER_FAMILY = 5
EXPECTED_MEASUREMENT_COUNT = 90
EXPECTED_CANDIDATE_ROW_COUNT = 30
EXPECTED_INSTANCE_COUNT = 15
EXPECTED_FAMILY_ORDER = ("fe4s4", "n2", "h2o")
EXPECTED_FAMILY_PROVENANCE: dict[str, dict[str, Any]] = {
    "fe4s4": {
        "molecule": "Fe4S4",
        "basis": None,
        "basis_status": "upstream_not_reported",
    },
    "n2": {
        "molecule": "N2",
        "basis": "6-31G",
        "basis_status": "reported",
    },
    "h2o": {
        "molecule": "H2O",
        "basis": "cc-pVDZ",
        "basis_status": "reported",
    },
}
PROVENANCE_ONLY_FIELDS = frozenset(
    {
        "family_id",
        "molecule",
        "basis",
        "basis_status",
        "problem_instance",
        "input_sha256",
        "instance_id",
    }
)


def build_multifamily_balanced_dataset(
    aggregate: Mapping[str, Any],
    *,
    metadata_by_record_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the exact 90-measurement, three-family balanced dataset.

    Rows must already carry trustworthy ``family_id``, ``molecule``, ``basis``,
    and (where the basis is unavailable) ``basis_status`` enrichment.  Included
    measured records are admitted only when raw metadata says their protocol
    purpose is ``final``.  This excludes pilot records even though they may be
    otherwise timing-eligible.
    """

    if not isinstance(aggregate, Mapping):
        raise EvaluationError("multifamily aggregate must be an object")
    rows = aggregate.get("rows")
    if not isinstance(rows, list) or not rows:
        raise EvaluationError("multifamily aggregate lacks rows")
    if not isinstance(metadata_by_record_id, Mapping):
        raise EvaluationError("metadata_by_record_id must be a mapping")

    selected_rows: list[dict[str, Any]] = []
    normalized_metadata: dict[str, dict[str, Any]] = {}
    provenance_by_instance: dict[str, dict[str, Any]] = {}
    repetitions_by_key: dict[tuple[str, str, str, str], set[int]] = defaultdict(set)
    instances_by_family: dict[str, set[str]] = defaultdict(set)
    seen_trial_ids: set[str] = set()

    for index, raw_row in enumerate(rows):
        if not isinstance(raw_row, Mapping):
            raise EvaluationError(f"aggregate row {index} is not an object")
        context = f"aggregate row {index}"
        trial_id = _text(raw_row.get("trial_id"), f"{context}.trial_id")
        if trial_id in seen_trial_ids:
            raise EvaluationError(f"duplicate aggregate trial_id: {trial_id}")
        seen_trial_ids.add(trial_id)

        provenance = _row_provenance(raw_row, context=context)
        instance = _text(
            raw_row.get("problem_instance"), f"{context}.problem_instance"
        )
        input_sha256 = _sha256(
            raw_row.get("input_sha256"), f"{context}.input_sha256"
        )
        instance_id = _instance_id(provenance["family_id"], instance)
        identity = {
            **provenance,
            "instance_id": instance_id,
            "problem_instance": instance,
            "input_sha256": input_sha256,
        }
        previous_identity = provenance_by_instance.setdefault(instance_id, identity)
        if previous_identity != identity:
            raise EvaluationError(
                f"family/workload {instance_id} maps to inconsistent provenance or input hash"
            )
        instances_by_family[provenance["family_id"]].add(instance_id)

        phase = _text(raw_row.get("phase"), f"{context}.phase")
        if phase not in {"warmup", "measured"}:
            raise EvaluationError(f"{context} has invalid phase")
        repetition = _nonnegative_int(
            raw_row.get("repetition"), f"{context}.repetition"
        )
        included = raw_row.get("included")
        if not isinstance(included, bool):
            raise EvaluationError(f"{context}.included must be boolean")
        candidate_name = _validate_candidate(raw_row, context=context)

        if not (
            included is True
            and phase == "measured"
            and repetition in BALANCED_REPETITIONS
        ):
            continue

        metadata = metadata_by_record_id.get(trial_id)
        if not isinstance(metadata, Mapping):
            raise EvaluationError(f"missing raw metadata for {trial_id}")
        protocol = metadata.get("protocol")
        if not isinstance(protocol, Mapping):
            raise EvaluationError(f"raw metadata {trial_id} lacks protocol")
        purpose = protocol.get("purpose")
        if purpose == "pilot":
            continue
        if purpose != "final":
            raise EvaluationError(
                f"raw metadata {trial_id} has unsupported timing purpose {purpose!r}"
            )
        _validate_selected_metadata(
            metadata,
            trial_id=trial_id,
            instance=instance,
            input_sha256=input_sha256,
            repetition=repetition,
            candidate_name=candidate_name,
            provenance=provenance,
        )

        key = (
            provenance["family_id"],
            instance,
            input_sha256,
            candidate_name,
        )
        if repetition in repetitions_by_key[key]:
            raise EvaluationError(f"duplicate repetition {repetition} for {key!r}")
        repetitions_by_key[key].add(repetition)

        normalized_row = deepcopy(dict(raw_row))
        normalized_row["problem_instance"] = instance_id
        selected_rows.append(normalized_row)
        normalized_raw = dict(metadata)
        normalized_raw["problem_instance"] = instance_id
        normalized_metadata[trial_id] = normalized_raw

    _validate_selected_geometry(
        selected_rows=selected_rows,
        repetitions_by_key=repetitions_by_key,
        instances_by_family=instances_by_family,
    )

    core_dataset = build_balanced_dataset(
        {"rows": selected_rows},
        metadata_by_record_id=normalized_metadata,
        expected_instances=EXPECTED_INSTANCE_COUNT,
    )
    enriched_rows: list[dict[str, Any]] = []
    for core_row in core_dataset["rows"]:
        instance_id = core_row["problem_instance"]
        provenance = provenance_by_instance[instance_id]
        enriched = dict(core_row)
        enriched.update(provenance)
        enriched_rows.append(enriched)
    enriched_rows.sort(key=_candidate_row_sort_key)

    enriched_instances: list[dict[str, Any]] = []
    for core_instance in core_dataset["instances"]:
        instance_id = core_instance["problem_instance"]
        provenance = provenance_by_instance[instance_id]
        enriched = dict(core_instance)
        enriched.update(provenance)
        enriched_instances.append(enriched)
    enriched_instances.sort(key=_instance_sort_key)

    families: list[dict[str, Any]] = []
    for family_id in EXPECTED_FAMILY_ORDER:
        members = [row for row in enriched_rows if row["family_id"] == family_id]
        provenance = EXPECTED_FAMILY_PROVENANCE[family_id]
        families.append(
            {
                "family_id": family_id,
                **provenance,
                "problem_instances": sorted(
                    {row["problem_instance"] for row in members}
                ),
                "instance_ids": sorted({row["instance_id"] for row in members}),
                "measurement_records": sum(
                    len(row["source_record_ids"]) for row in members
                ),
                "candidate_rows": len(members),
            }
        )

    dataset = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "dataset_type": MULTIFAMILY_DATASET_TYPE,
        "analysis_view": {
            "phase": "measured",
            "protocol_purpose": "final",
            "repetitions": list(BALANCED_REPETITIONS),
            "aggregation": "median wall time per family/workload/candidate",
            "group_key": [
                "family_id",
                "problem_instance",
                "input_sha256",
                "candidate_name",
            ],
            "provenance_only_fields": sorted(PROVENANCE_ONLY_FIELDS),
        },
        "feature_names": deepcopy(core_dataset["feature_names"]),
        "target": core_dataset["target"],
        "record_counts": deepcopy(core_dataset["record_counts"]),
        "candidate_contract": deepcopy(core_dataset["candidate_contract"]),
        "families": families,
        "instances": enriched_instances,
        "rows": enriched_rows,
        "source_record_ids": list(core_dataset["source_record_ids"]),
    }
    validate_multifamily_dataset(dataset)
    _strict_json(dataset, "multifamily dataset")
    return dataset


def validate_multifamily_dataset(dataset: Mapping[str, Any]) -> None:
    """Validate exact geometry, provenance, candidate pairing, and source IDs."""

    if not isinstance(dataset, Mapping):
        raise EvaluationError("multifamily dataset must be an object")
    if dataset.get("dataset_type") != MULTIFAMILY_DATASET_TYPE:
        raise EvaluationError("unexpected multifamily dataset type")
    expected_counts = {
        "selected_measurements": EXPECTED_MEASUREMENT_COUNT,
        "candidate_rows": EXPECTED_CANDIDATE_ROW_COUNT,
        "problem_instances": EXPECTED_INSTANCE_COUNT,
        "candidates_per_instance": len(EXPECTED_CANDIDATES),
        "repetitions_per_candidate": len(BALANCED_REPETITIONS),
    }
    if dataset.get("record_counts") != expected_counts:
        raise EvaluationError("multifamily dataset record counts differ")
    feature_names = dataset.get("feature_names")
    if not isinstance(feature_names, Mapping):
        raise EvaluationError("multifamily dataset lacks feature names")
    if tuple(feature_names.get("size_only", ())) != SIZE_ONLY_FEATURE_NAMES:
        raise EvaluationError("size-only feature contract differs")
    if tuple(feature_names.get("full", ())) != FULL_FEATURE_NAMES:
        raise EvaluationError("full feature contract differs")
    if PROVENANCE_ONLY_FIELDS.intersection(FULL_FEATURE_NAMES):
        raise EvaluationError("provenance field leaked into registered model features")

    rows = _object_list(dataset.get("rows"), "dataset rows")
    instances = _object_list(dataset.get("instances"), "dataset instances")
    families = _object_list(dataset.get("families"), "dataset families")
    if len(rows) != EXPECTED_CANDIDATE_ROW_COUNT:
        raise EvaluationError("multifamily dataset must contain 30 candidate rows")
    if len(instances) != EXPECTED_INSTANCE_COUNT:
        raise EvaluationError("multifamily dataset must contain 15 instances")
    if [family.get("family_id") for family in families] != list(
        EXPECTED_FAMILY_ORDER
    ):
        raise EvaluationError("multifamily dataset family order differs")

    source_ids = _string_list(dataset.get("source_record_ids"), "source_record_ids")
    if len(source_ids) != EXPECTED_MEASUREMENT_COUNT or len(set(source_ids)) != len(
        source_ids
    ):
        raise EvaluationError("multifamily dataset source IDs must be 90 unique records")

    rows_by_instance: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    family_instances: dict[str, set[str]] = defaultdict(set)
    row_source_ids: set[str] = set()
    allowed_feature_values = set(FULL_FEATURE_NAMES) | {"n_configurations"}
    for row in rows:
        provenance = _row_provenance(row, context="candidate row")
        instance_id = _text(row.get("instance_id"), "candidate row.instance_id")
        instance = _text(
            row.get("problem_instance"), "candidate row.problem_instance"
        )
        if instance_id != _instance_id(provenance["family_id"], instance):
            raise EvaluationError("candidate row instance_id disagrees with family/workload")
        _sha256(row.get("input_sha256"), "candidate row.input_sha256")
        candidate_name = _text(
            row.get("candidate_name"), "candidate row.candidate_name"
        )
        if candidate_name not in EXPECTED_CANDIDATES:
            raise EvaluationError(f"unexpected candidate {candidate_name!r}")
        if row.get("repetitions") != list(BALANCED_REPETITIONS):
            raise EvaluationError("candidate row repetitions must be exactly 0,1,2")
        row_ids = _string_list(row.get("source_record_ids"), "row source_record_ids")
        if len(row_ids) != len(BALANCED_REPETITIONS):
            raise EvaluationError("candidate row must cite exactly three records")
        overlap = row_source_ids.intersection(row_ids)
        if overlap:
            raise EvaluationError(f"source record reused across rows: {sorted(overlap)}")
        row_source_ids.update(row_ids)
        values = row.get("feature_values")
        if not isinstance(values, Mapping):
            raise EvaluationError("candidate row lacks feature_values")
        if set(values) != allowed_feature_values:
            raise EvaluationError("candidate row feature-value contract differs")
        if PROVENANCE_ONLY_FIELDS.intersection(values):
            raise EvaluationError("provenance field leaked into feature_values")
        for feature_name in FULL_FEATURE_NAMES:
            _finite_number(values.get(feature_name), f"feature {feature_name}")
        rows_by_instance[instance_id].append(row)
        family_instances[provenance["family_id"]].add(instance_id)

    if row_source_ids != set(source_ids):
        raise EvaluationError("candidate-row source IDs do not match dataset source IDs")
    instances_by_id: dict[str, Mapping[str, Any]] = {}
    for item in instances:
        instance_id = _text(
            item.get("instance_id"), "instance summary.instance_id"
        )
        if instance_id in instances_by_id:
            raise EvaluationError(f"duplicate instance summary: {instance_id}")
        instances_by_id[instance_id] = item
    if set(rows_by_instance) != set(instances_by_id):
        raise EvaluationError("candidate rows and instance summaries disagree")
    for instance_id, members in rows_by_instance.items():
        names = {row["candidate_name"] for row in members}
        if len(members) != 2 or names != set(EXPECTED_CANDIDATES):
            raise EvaluationError(
                f"{instance_id} must contain exactly the CPU and GPU candidates"
            )
        hashes = {row["input_sha256"] for row in members}
        provenance = {
            (row["family_id"], row["molecule"], row["basis"], row["basis_status"])
            for row in members
        }
        if len(hashes) != 1 or len(provenance) != 1:
            raise EvaluationError(f"candidate provenance mismatch for {instance_id}")
        first = members[0]
        summary_fields = (
            "family_id",
            "molecule",
            "basis",
            "basis_status",
            "instance_id",
            "problem_instance",
            "input_sha256",
            "n_configurations",
            "memory_caps",
        )
        for member in members[1:]:
            if any(member.get(field) != first.get(field) for field in summary_fields):
                raise EvaluationError(
                    f"candidate summary fields disagree for {instance_id}"
                )
        expected_summary = {
            "problem_instance": first["problem_instance"],
            "input_sha256": first["input_sha256"],
            "n_configurations": first["n_configurations"],
            "memory_caps": first["memory_caps"],
            "source_record_ids": sorted(
                record_id
                for member in members
                for record_id in _string_list(
                    member.get("source_record_ids"), "candidate source IDs"
                )
            ),
            "family_id": first["family_id"],
            "molecule": first["molecule"],
            "basis": first["basis"],
            "basis_status": first["basis_status"],
            "instance_id": first["instance_id"],
        }
        if dict(instances_by_id[instance_id]) != expected_summary:
            raise EvaluationError(
                f"instance summary differs from candidate rows: {instance_id}"
            )
    if set(family_instances) != set(EXPECTED_FAMILY_ORDER):
        raise EvaluationError("multifamily dataset family set differs")
    for family_id, family_summary in zip(EXPECTED_FAMILY_ORDER, families):
        if len(family_instances[family_id]) != EXPECTED_INSTANCE_COUNT_PER_FAMILY:
            raise EvaluationError(f"family {family_id} must contain exactly five instances")
        members = [row for row in rows if row["family_id"] == family_id]
        expected_family_summary = {
            "family_id": family_id,
            **EXPECTED_FAMILY_PROVENANCE[family_id],
            "problem_instances": sorted(
                {row["problem_instance"] for row in members}
            ),
            "instance_ids": sorted({row["instance_id"] for row in members}),
            "measurement_records": sum(
                len(
                    _string_list(
                        row.get("source_record_ids"), "family source IDs"
                    )
                )
                for row in members
            ),
            "candidate_rows": len(members),
        }
        if dict(family_summary) != expected_family_summary:
            raise EvaluationError(
                f"family summary differs from candidate rows: {family_id}"
            )


def make_leave_one_family_out_splits(
    dataset: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return deterministic Fe4S4, N2, and H2O held-out folds."""

    validate_multifamily_dataset(dataset)
    instances = _object_list(dataset["instances"], "dataset instances")
    folds: list[dict[str, Any]] = []
    for index, heldout_family in enumerate(EXPECTED_FAMILY_ORDER, start=1):
        train_families = [
            family for family in EXPECTED_FAMILY_ORDER if family != heldout_family
        ]
        train_instances = sorted(
            item["instance_id"]
            for item in instances
            if item["family_id"] in train_families
        )
        test_instances = sorted(
            item["instance_id"]
            for item in instances
            if item["family_id"] == heldout_family
        )
        split = {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "name": f"primary_leave_one_family_out_{index:02d}_{heldout_family}",
            "group_key": "family_id and instance_id; all candidates and repetitions remain together",
            "heldout_family_id": heldout_family,
            "train_family_ids": train_families,
            "test_family_ids": [heldout_family],
            "train_instance_ids": train_instances,
            "test_instance_ids": test_instances,
            "train_source_record_ids": sorted(
                _source_ids_for_instances(dataset, set(train_instances))
            ),
            "test_source_record_ids": sorted(
                _source_ids_for_instances(dataset, set(test_instances))
            ),
        }
        validate_leave_one_family_out_split(dataset, split)
        folds.append(split)
    return folds


def validate_leave_one_family_out_split(
    dataset: Mapping[str, Any], split: Mapping[str, Any]
) -> None:
    """Fail closed on family, instance, or immutable source-record leakage."""

    validate_multifamily_dataset(dataset)
    if not isinstance(split, Mapping):
        raise EvaluationError("leave-one-family-out split must be an object")
    heldout = _text(split.get("heldout_family_id"), "heldout_family_id")
    if heldout not in EXPECTED_FAMILY_ORDER:
        raise EvaluationError("unexpected held-out family")
    train_families = _string_list(split.get("train_family_ids"), "train_family_ids")
    test_families = _string_list(split.get("test_family_ids"), "test_family_ids")
    expected_train_families = [
        family for family in EXPECTED_FAMILY_ORDER if family != heldout
    ]
    if train_families != expected_train_families or test_families != [heldout]:
        raise EvaluationError("leave-one-family-out family partition differs")
    if set(train_families).intersection(test_families):
        raise EvaluationError("train/test family leakage detected")

    instances = _object_list(dataset["instances"], "dataset instances")
    expected_train_instances = {
        item["instance_id"]
        for item in instances
        if item["family_id"] in train_families
    }
    expected_test_instances = {
        item["instance_id"]
        for item in instances
        if item["family_id"] == heldout
    }
    train_instances = set(
        _string_list(split.get("train_instance_ids"), "train_instance_ids")
    )
    test_instances = set(
        _string_list(split.get("test_instance_ids"), "test_instance_ids")
    )
    if train_instances.intersection(test_instances):
        raise EvaluationError("train/test instance leakage detected")
    if train_instances != expected_train_instances or test_instances != expected_test_instances:
        raise EvaluationError("leave-one-family-out instance partition differs")
    if len(train_instances) != 10 or len(test_instances) != 5:
        raise EvaluationError("leave-one-family-out split must be 10 train / 5 test instances")

    expected_train_sources = set(_source_ids_for_instances(dataset, train_instances))
    expected_test_sources = set(_source_ids_for_instances(dataset, test_instances))
    train_sources = set(
        _string_list(
            split.get("train_source_record_ids"), "train_source_record_ids"
        )
    )
    test_sources = set(
        _string_list(split.get("test_source_record_ids"), "test_source_record_ids")
    )
    if train_sources.intersection(test_sources):
        raise EvaluationError("train/test source-record leakage detected")
    if train_sources != expected_train_sources or test_sources != expected_test_sources:
        raise EvaluationError("leave-one-family-out source-record partition differs")
    if len(train_sources) != 60 or len(test_sources) != 30:
        raise EvaluationError("leave-one-family-out split must be 60 train / 30 test records")
    if train_sources.union(test_sources) != set(dataset["source_record_ids"]):
        raise EvaluationError("leave-one-family-out split omits dataset source records")


def evaluate_multifamily_fold(
    dataset: Mapping[str, Any], split: Mapping[str, Any]
) -> dict[str, Any]:
    """Train on two families and evaluate all six policies on the third."""

    validate_leave_one_family_out_split(dataset, split)
    train_ids = set(split["train_instance_ids"])
    test_ids = set(split["test_instance_ids"])
    rows = _object_list(dataset["rows"], "dataset rows")
    train_rows = [_model_row(row) for row in rows if row["instance_id"] in train_ids]
    test_rows = [row for row in rows if row["instance_id"] in test_ids]

    threshold = fit_static_threshold(train_rows)
    full_model = _fit_multifamily_runtime_tree(
        train_rows, feature_names=FULL_FEATURE_NAMES
    )
    size_model = _fit_multifamily_runtime_tree(
        train_rows, feature_names=SIZE_ONLY_FEATURE_NAMES
    )
    expected_training_sources = sorted(split["train_source_record_ids"])
    for model in (threshold, full_model, size_model):
        if model.get("training_source_record_ids") != expected_training_sources:
            raise EvaluationError("fitted model source IDs differ from training split")

    by_instance: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in test_rows:
        by_instance[row["instance_id"]].append(row)
    predictions: list[dict[str, Any]] = []
    for instance_id in sorted(by_instance):
        instance_rows = sorted(
            by_instance[instance_id], key=lambda row: row["candidate_name"]
        )
        by_name = {row["candidate_name"]: row for row in instance_rows}
        caps = _consistent_caps(instance_rows)
        feasible = [
            row
            for row in instance_rows
            if candidate_is_feasible(row, memory_caps=caps)
        ]
        if feasible:
            oracle_time = min(float(row["median_wall_time_s"]) for row in feasible)
            oracle_rows = [
                row
                for row in feasible
                if math.isclose(
                    float(row["median_wall_time_s"]),
                    oracle_time,
                    rel_tol=1e-15,
                    abs_tol=0.0,
                )
            ]
        else:
            oracle_time = None
            oracle_rows = []
        threshold_name = select_with_static_threshold(
            threshold, int(instance_rows[0]["n_configurations"])
        )
        full_selection = select_with_tree(full_model, instance_rows, memory_caps=caps)
        size_selection = select_with_tree(size_model, instance_rows, memory_caps=caps)
        decisions = {
            POLICY_FIXED_CPU: (CPU_CANDIDATE, None),
            POLICY_FIXED_GPU: (GPU_CANDIDATE, None),
            POLICY_THRESHOLD: (threshold_name, None),
            POLICY_SIZE_TREE: (
                size_selection["selected_candidate_name"],
                size_selection["predictions"],
            ),
            POLICY_FULL_TREE: (
                full_selection["selected_candidate_name"],
                full_selection["predictions"],
            ),
            POLICY_ORACLE: (
                min((row["candidate_name"] for row in oracle_rows), default=None),
                None,
            ),
        }
        for policy in POLICY_ORDER:
            decision, model_predictions = decisions[policy]
            predictions.append(
                _policy_prediction(
                    policy=policy,
                    decision_candidate_name=decision,
                    model_predictions=model_predictions,
                    by_name=by_name,
                    caps=caps,
                    oracle_rows=oracle_rows,
                    oracle_time=oracle_time,
                )
            )

    metrics = {
        policy: summarize_policy_predictions(
            [row for row in predictions if row["policy"] == policy]
        )
        for policy in POLICY_ORDER
    }
    result = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "evaluation_type": "autosbd_multifamily_held_out_fold",
        "split": dict(split),
        "models": {
            POLICY_THRESHOLD: threshold,
            POLICY_SIZE_TREE: size_model,
            POLICY_FULL_TREE: full_model,
        },
        "policy_aliases": {POLICY_UPSTREAM_DEFAULT: POLICY_FIXED_GPU},
        "predictions": predictions,
        "metrics": metrics,
        "training_source_record_ids": expected_training_sources,
        "test_source_record_ids": sorted(split["test_source_record_ids"]),
    }
    _strict_json(result, "multifamily fold evaluation")
    return result


def evaluate_multifamily_selector(dataset: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate and pool the three primary leave-one-family-out folds."""

    validate_multifamily_dataset(dataset)
    folds = [
        evaluate_multifamily_fold(dataset, split)
        for split in make_leave_one_family_out_splits(dataset)
    ]
    predictions = [
        prediction for fold in folds for prediction in fold["predictions"]
    ]
    if len(predictions) != len(POLICY_ORDER) * EXPECTED_INSTANCE_COUNT:
        raise EvaluationError("pooled multifamily prediction count differs")
    metrics = {
        policy: summarize_policy_predictions(
            [row for row in predictions if row["policy"] == policy]
        )
        for policy in POLICY_ORDER
    }
    per_family_metrics = {
        family_id: {
            policy: summarize_policy_predictions(
                [
                    row
                    for row in predictions
                    if row["family_id"] == family_id and row["policy"] == policy
                ]
            )
            for policy in POLICY_ORDER
        }
        for family_id in EXPECTED_FAMILY_ORDER
    }
    result = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "evaluation_type": MULTIFAMILY_EVALUATION_TYPE,
        "split_type": "leave_one_chemistry_family_out",
        "policy_order": list(POLICY_ORDER),
        "policy_aliases": {POLICY_UPSTREAM_DEFAULT: POLICY_FIXED_GPU},
        "source_record_ids": list(dataset["source_record_ids"]),
        "folds": folds,
        "predictions": predictions,
        "metrics": metrics,
        "per_heldout_family_metrics": per_family_metrics,
    }
    _strict_json(result, "multifamily selector evaluation")
    return result


def fit_multifamily_deployment_tree(
    dataset: Mapping[str, Any],
) -> dict[str, Any]:
    """Fit a post-evaluation deployment tree on all balanced instances.

    This model is a deployment artifact, not a held-out evaluation model.  The
    leave-one-family-out folds above remain the only source of generalization
    metrics.  Exact instance and immutable-record provenance binds the exported
    tree to the validated 15-instance balanced dataset.
    """

    validate_multifamily_dataset(dataset)
    rows = [
        _model_row(row)
        for row in _object_list(dataset.get("rows"), "dataset rows")
    ]
    model = _fit_multifamily_runtime_tree(rows, feature_names=FULL_FEATURE_NAMES)
    expected_instance_ids = sorted(
        item["instance_id"]
        for item in _object_list(dataset.get("instances"), "dataset instances")
    )
    expected_source_ids = sorted(
        _string_list(dataset.get("source_record_ids"), "dataset source_record_ids")
    )
    if model.get("training_instance_ids") != expected_instance_ids:
        raise EvaluationError(
            "deployment tree training instances differ from balanced dataset"
        )
    if model.get("training_source_record_ids") != expected_source_ids:
        raise EvaluationError(
            "deployment tree source records differ from balanced dataset"
        )
    return model


def _fit_multifamily_runtime_tree(
    candidate_rows: Sequence[Mapping[str, Any]],
    *,
    feature_names: Sequence[str],
) -> dict[str, Any]:
    if sklearn.__version__ != REQUIRED_SKLEARN_VERSION:
        raise EvaluationError(
            f"scikit-learn {REQUIRED_SKLEARN_VERSION} is required; "
            f"found {sklearn.__version__}"
        )
    names = tuple(feature_names)
    if names not in (SIZE_ONLY_FEATURE_NAMES, FULL_FEATURE_NAMES):
        raise EvaluationError("unregistered multifamily feature set")
    by_instance = _validate_model_rows(candidate_rows)
    ordered_rows = sorted(
        (row for members in by_instance.values() for row in members),
        key=lambda row: (row["problem_instance"], row["candidate_name"]),
    )
    matrix = [
        [_finite_number(row["feature_values"].get(name), f"training.{name}") for name in names]
        for row in ordered_rows
    ]
    targets = [
        _finite_number(
            row.get("target_log1p_median_wall_time_s"),
            "target_log1p_median_wall_time_s",
        )
        for row in ordered_rows
    ]
    estimator = DecisionTreeRegressor(
        max_depth=MULTIFAMILY_TREE_MAX_DEPTH,
        min_samples_leaf=MULTIFAMILY_TREE_MIN_SAMPLES_LEAF,
        random_state=TREE_RANDOM_STATE,
    )
    estimator.fit(matrix, targets)
    tree = estimator.tree_
    nodes: list[dict[str, Any]] = []
    for node_id in range(tree.node_count):
        left = int(tree.children_left[node_id])
        right = int(tree.children_right[node_id])
        node: dict[str, Any] = {
            "node_id": node_id,
            "sample_count": int(tree.n_node_samples[node_id]),
            "weighted_sample_count": float(tree.weighted_n_node_samples[node_id]),
            "impurity": float(tree.impurity[node_id]),
        }
        if left == right:
            node.update(
                {
                    "type": "leaf",
                    "value_log1p_median_wall_time_s": float(tree.value[node_id][0][0]),
                }
            )
        else:
            feature_index = int(tree.feature[node_id])
            node.update(
                {
                    "type": "split",
                    "feature_index": feature_index,
                    "feature_name": names[feature_index],
                    "threshold": float(tree.threshold[node_id]),
                    "left_child": left,
                    "right_child": right,
                    "rule": "left when feature_value <= threshold; right otherwise",
                }
            )
        nodes.append(node)
    model = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "model_type": "sklearn.tree.DecisionTreeRegressor",
        "sklearn_version": sklearn.__version__,
        "feature_set": "size_only" if names == SIZE_ONLY_FEATURE_NAMES else "full",
        "feature_names": list(names),
        "target": "log1p(median end-to-end wall_time_s)",
        "hyperparameters": {
            "max_depth": MULTIFAMILY_TREE_MAX_DEPTH,
            "min_samples_leaf": MULTIFAMILY_TREE_MIN_SAMPLES_LEAF,
            "random_state": TREE_RANDOM_STATE,
        },
        "training_instance_ids": sorted(by_instance),
        "training_source_record_ids": sorted(
            record_id
            for row in ordered_rows
            for record_id in _string_list(
                row.get("source_record_ids"), "training source_record_ids"
            )
        ),
        "tree": {
            "node_count": int(tree.node_count),
            "actual_depth": int(tree.max_depth),
            "leaf_count": int(estimator.get_n_leaves()),
            "nodes": nodes,
        },
    }
    _strict_json(model, "multifamily runtime tree")
    return model


def _validate_model_rows(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    by_instance: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    seen_sources: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise EvaluationError("model row is not an object")
        instance_id = _text(row.get("problem_instance"), "model instance_id")
        candidate = _text(row.get("candidate_name"), "model candidate_name")
        if candidate not in EXPECTED_CANDIDATES:
            raise EvaluationError(f"unexpected model candidate {candidate!r}")
        source_ids = _string_list(row.get("source_record_ids"), "model source IDs")
        if len(source_ids) != len(BALANCED_REPETITIONS):
            raise EvaluationError("model candidate row must cite exactly three records")
        if seen_sources.intersection(source_ids):
            raise EvaluationError("model source record reused across candidate rows")
        seen_sources.update(source_ids)
        values = row.get("feature_values")
        if not isinstance(values, Mapping):
            raise EvaluationError("model row lacks feature_values")
        if PROVENANCE_ONLY_FIELDS.intersection(values):
            raise EvaluationError("provenance field leaked into model features")
        by_instance[instance_id].append(row)
    for instance_id, members in by_instance.items():
        if {row["candidate_name"] for row in members} != set(EXPECTED_CANDIDATES):
            raise EvaluationError(f"model instance {instance_id} lacks candidate pair")
    return dict(sorted(by_instance.items()))


def _policy_prediction(
    *,
    policy: str,
    decision_candidate_name: str | None,
    model_predictions: Any,
    by_name: Mapping[str, Mapping[str, Any]],
    caps: Mapping[str, int],
    oracle_rows: Sequence[Mapping[str, Any]],
    oracle_time: float | None,
) -> dict[str, Any]:
    representative = next(iter(by_name.values()))
    oracle_names = sorted(row["candidate_name"] for row in oracle_rows)
    oracle_source_ids = sorted(
        record_id
        for row in oracle_rows
        for record_id in _string_list(
            row.get("source_record_ids"), "oracle source IDs"
        )
    )
    base = {
        "policy": policy,
        "family_id": representative["family_id"],
        "molecule": representative["molecule"],
        "basis": representative["basis"],
        "basis_status": representative["basis_status"],
        "instance_id": representative["instance_id"],
        "problem_instance": representative["problem_instance"],
        "input_sha256": representative["input_sha256"],
        "n_configurations": representative["n_configurations"],
        "decision_candidate_name": decision_candidate_name,
        "selected_candidate_name": None,
        "selected_source_record_ids": [],
        "oracle_candidate_names": oracle_names,
        "oracle_source_record_ids": oracle_source_ids,
        "oracle_wall_time_s": oracle_time,
        "selected_wall_time_s": None,
        "normalized_runtime": None,
        "normalized_regret": None,
        "speedup_vs_fixed_cpu": None,
        "speedup_vs_fixed_gpu": None,
        "selection_correct": False,
        "within_5pct_oracle": False,
        "valid": False,
        "failure": False,
        "invalid_reason": None,
        "candidate_predictions": model_predictions,
    }
    if oracle_time is None:
        base["invalid_reason"] = "no_feasible_candidates"
        return base
    if decision_candidate_name is None:
        base["invalid_reason"] = "policy_returned_no_candidate"
        return base
    selected = by_name.get(decision_candidate_name)
    if selected is None:
        base["invalid_reason"] = "candidate_not_in_matrix"
        return base
    if not candidate_is_feasible(selected, memory_caps=caps):
        base["invalid_reason"] = "selected_candidate_memory_infeasible"
        return base
    selected_time = _positive_number(
        selected.get("median_wall_time_s"), "selected median wall time"
    )
    cpu_time = _positive_number(
        by_name[CPU_CANDIDATE].get("median_wall_time_s"), "CPU median wall time"
    )
    gpu_time = _positive_number(
        by_name[GPU_CANDIDATE].get("median_wall_time_s"), "GPU median wall time"
    )
    normalized_runtime = selected_time / oracle_time
    base.update(
        {
            "selected_candidate_name": decision_candidate_name,
            "selected_source_record_ids": _string_list(
                selected.get("source_record_ids"), "selected source IDs"
            ),
            "selected_wall_time_s": selected_time,
            "normalized_runtime": normalized_runtime,
            "normalized_regret": normalized_regret(selected_time, oracle_time),
            "speedup_vs_fixed_cpu": cpu_time / selected_time,
            "speedup_vs_fixed_gpu": gpu_time / selected_time,
            "selection_correct": decision_candidate_name in oracle_names,
            "within_5pct_oracle": normalized_runtime <= 1.05,
            "valid": True,
        }
    )
    return base


def _row_provenance(row: Mapping[str, Any], *, context: str) -> dict[str, Any]:
    family_id = _text(row.get("family_id"), f"{context}.family_id")
    if family_id not in EXPECTED_FAMILY_PROVENANCE:
        raise EvaluationError(f"unexpected authentic family {family_id!r}")
    expected = EXPECTED_FAMILY_PROVENANCE[family_id]
    molecule = _text(row.get("molecule"), f"{context}.molecule")
    basis = row.get("basis")
    basis_status = row.get("basis_status")
    if basis_status is None and isinstance(basis, str) and basis:
        basis_status = "reported"
    if (
        molecule != expected["molecule"]
        or basis != expected["basis"]
        or basis_status != expected["basis_status"]
    ):
        raise EvaluationError(f"{context} family provenance differs for {family_id}")
    return {
        "family_id": family_id,
        "molecule": molecule,
        "basis": basis,
        "basis_status": basis_status,
    }


def _validate_candidate(row: Mapping[str, Any], *, context: str) -> str:
    candidate = row.get("candidate")
    if not isinstance(candidate, Mapping):
        raise EvaluationError(f"{context} lacks candidate identity")
    name = _text(candidate.get("name"), f"{context}.candidate.name")
    if name not in EXPECTED_CANDIDATES:
        raise EvaluationError(f"unexpected candidate {name!r}")
    expected_backend, expected_threads = EXPECTED_CANDIDATES[name]
    if (
        candidate.get("backend") != expected_backend
        or candidate.get("cpu_threads") != expected_threads
    ):
        raise EvaluationError(f"{context} candidate backend/thread mismatch")
    return name


def _validate_selected_metadata(
    metadata: Mapping[str, Any],
    *,
    trial_id: str,
    instance: str,
    input_sha256: str,
    repetition: int,
    candidate_name: str,
    provenance: Mapping[str, Any],
) -> None:
    for key, expected in (
        ("trial_id", trial_id),
        ("problem_instance", instance),
        ("input_sha256", input_sha256),
        ("repetition", repetition),
    ):
        if metadata.get(key) != expected:
            raise EvaluationError(f"raw metadata {key} mismatch for {trial_id}")
    if (
        metadata.get("warmup_or_measured") != "measured"
        or metadata.get("timing_eligible") is not True
        or metadata.get("status") != "success"
        or metadata.get("correct") is not True
    ):
        raise EvaluationError(f"raw metadata timing gates failed for {trial_id}")
    logical = metadata.get("logical_identity")
    candidate = logical.get("candidate") if isinstance(logical, Mapping) else None
    if not isinstance(candidate, Mapping) or candidate.get("name") != candidate_name:
        raise EvaluationError(f"raw metadata candidate mismatch for {trial_id}")
    if metadata.get("schema_version") == 3:
        for field in ("family_id", "molecule", "basis"):
            if metadata.get(field) != provenance[field]:
                raise EvaluationError(
                    f"raw metadata {field} mismatch for family-aware record {trial_id}"
                )


def _validate_selected_geometry(
    *,
    selected_rows: Sequence[Mapping[str, Any]],
    repetitions_by_key: Mapping[tuple[str, str, str, str], set[int]],
    instances_by_family: Mapping[str, set[str]],
) -> None:
    if len(selected_rows) != EXPECTED_MEASUREMENT_COUNT:
        raise EvaluationError(
            f"balanced multifamily view requires 90 measurements, found {len(selected_rows)}"
        )
    if len(repetitions_by_key) != EXPECTED_CANDIDATE_ROW_COUNT:
        raise EvaluationError("balanced multifamily view requires 30 candidate groups")
    expected_repetitions = set(BALANCED_REPETITIONS)
    for key, repetitions in repetitions_by_key.items():
        if repetitions != expected_repetitions:
            raise EvaluationError(f"candidate group {key!r} lacks repetitions 0,1,2")
    if set(instances_by_family) != set(EXPECTED_FAMILY_ORDER):
        raise EvaluationError("balanced multifamily family set differs")
    for family_id in EXPECTED_FAMILY_ORDER:
        if len(instances_by_family[family_id]) != EXPECTED_INSTANCE_COUNT_PER_FAMILY:
            raise EvaluationError(f"family {family_id} must contain exactly five instances")


def _model_row(row: Mapping[str, Any]) -> dict[str, Any]:
    model_row = dict(row)
    model_row["problem_instance"] = row["instance_id"]
    return model_row


def _consistent_caps(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    first = rows[0].get("memory_caps")
    if not isinstance(first, Mapping):
        raise EvaluationError("candidate row lacks memory caps")
    caps = {
        "host_cap_bytes": _nonnegative_int(
            first.get("host_cap_bytes"), "host_cap_bytes"
        ),
        "gpu_cap_bytes": _nonnegative_int(
            first.get("gpu_cap_bytes"), "gpu_cap_bytes"
        ),
    }
    for row in rows[1:]:
        if row.get("memory_caps") != first:
            raise EvaluationError("candidate memory-cap mismatch within instance")
    return caps


def _source_ids_for_instances(
    dataset: Mapping[str, Any], instance_ids: set[str]
) -> list[str]:
    return [
        record_id
        for row in _object_list(dataset.get("rows"), "dataset rows")
        if row.get("instance_id") in instance_ids
        for record_id in _string_list(
            row.get("source_record_ids"), "candidate source IDs"
        )
    ]


def _candidate_row_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        EXPECTED_FAMILY_ORDER.index(str(row["family_id"])),
        int(row["n_configurations"]),
        str(row["problem_instance"]),
        str(row["candidate_name"]),
    )


def _instance_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        EXPECTED_FAMILY_ORDER.index(str(row["family_id"])),
        int(row["n_configurations"]),
        str(row["problem_instance"]),
    )


def _instance_id(family_id: str, problem_instance: str) -> str:
    return f"{family_id}::{problem_instance}"


def _object_list(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise EvaluationError(f"{label} must be a list of objects")
    return list(value)


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise EvaluationError(f"{label} must be a list of nonempty strings")
    if len(value) != len(set(value)):
        raise EvaluationError(f"{label} contains duplicates")
    return list(value)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EvaluationError(f"{label} must be a nonempty trimmed string")
    return value


def _sha256(value: Any, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise EvaluationError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvaluationError(f"{label} must be a nonnegative integer")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise EvaluationError(f"{label} must be finite")
    return numeric


def _positive_number(value: Any, label: str) -> float:
    numeric = _finite_number(value, label)
    if numeric <= 0.0:
        raise EvaluationError(f"{label} must be positive")
    return numeric


def _strict_json(value: Any, label: str) -> None:
    try:
        json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as error:
        raise EvaluationError(f"{label} is not strict JSON: {error}") from error
