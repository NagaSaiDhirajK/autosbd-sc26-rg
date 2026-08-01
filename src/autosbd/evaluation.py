"""Leakage-safe runtime-selector training and held-out evaluation.

The public functions in this module operate on an in-memory timing aggregate;
they intentionally perform no file discovery or writes.  The balanced view is
fixed to measured repetitions 0, 1, and 2 so every problem/candidate pair has
equal weight.  Tree models are trained on the log of the median end-to-end wall
time and exported as deterministic, JSON-compatible node tables.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import json
import math
from typing import Any

import sklearn
from sklearn.tree import DecisionTreeRegressor


EVALUATION_SCHEMA_VERSION = 1
REQUIRED_SKLEARN_VERSION = "1.7.1"
BALANCED_REPETITIONS = (0, 1, 2)
TREE_MAX_DEPTH = 2
TREE_MIN_SAMPLES_LEAF = 1
TREE_RANDOM_STATE = 1729

CPU_CANDIDATE = "amd-cpu-16"
GPU_CANDIDATE = "amd-l4-default"
EXPECTED_CANDIDATES: dict[str, tuple[str, int]] = {
    CPU_CANDIDATE: ("cpu", 16),
    GPU_CANDIDATE: ("gpu", 1),
}

SIZE_ONLY_FEATURE_NAMES = (
    "log1p_n_configurations",
    "backend_gpu",
)
FULL_FEATURE_NAMES = SIZE_ONLY_FEATURE_NAMES + (
    "log1p_method0_work_proxy",
    "log1p_determinant_cache_bytes",
    "log1p_gpu_guard_bytes",
    "alpha_single_edge_density",
    "alpha_double_edge_density",
    "beta_single_edge_density",
    "beta_double_edge_density",
    "cpu_threads",
)

POLICY_FIXED_CPU = "fixed_cpu16"
POLICY_FIXED_GPU = "fixed_gpu"
POLICY_UPSTREAM_DEFAULT = "upstream_default"
POLICY_THRESHOLD = "static_size_threshold"
POLICY_FULL_TREE = "autosbd_full_tree"
POLICY_SIZE_TREE = "size_only_tree_ablation"
POLICY_ORACLE = "measured_feasible_oracle"
POLICY_ORDER = (
    POLICY_FIXED_CPU,
    POLICY_FIXED_GPU,
    POLICY_THRESHOLD,
    POLICY_SIZE_TREE,
    POLICY_FULL_TREE,
    POLICY_ORACLE,
)


class EvaluationError(ValueError):
    """Raised when selector data or evaluation state is unsafe or incomplete."""


def build_balanced_dataset(
    aggregate: Mapping[str, Any],
    *,
    metadata_by_record_id: Mapping[str, Mapping[str, Any]] | None = None,
    expected_instances: int = 5,
) -> dict[str, Any]:
    """Convert the fixed 0..2 view into one median row per instance/candidate.

    ``metadata_by_record_id`` may map each selected aggregate ``trial_id`` to
    its immutable raw record.  Equivalently, callers may enrich aggregate rows
    directly with ``source_memory_estimate`` and ``preflight``.  Only
    pre-execution estimates and admission caps are read from that metadata;
    measured peak memory and other post-execution fields are never features.
    """

    if not isinstance(aggregate, Mapping):
        raise EvaluationError("aggregate must be an object")
    rows = aggregate.get("rows")
    if not isinstance(rows, list):
        raise EvaluationError("aggregate lacks a rows list")
    _require_positive_int("expected_instances", expected_instances)
    if metadata_by_record_id is not None and not isinstance(
        metadata_by_record_id, Mapping
    ):
        raise EvaluationError("metadata_by_record_id must be a mapping")

    selected: list[dict[str, Any]] = []
    seen_trial_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise EvaluationError(f"aggregate row {index} is not an object")
        if (
            row.get("included") is not True
            or row.get("phase") != "measured"
            or row.get("repetition") not in BALANCED_REPETITIONS
        ):
            continue
        trial_id = _required_string(row, "trial_id", f"aggregate row {index}")
        if trial_id in seen_trial_ids:
            raise EvaluationError(f"duplicate selected trial_id: {trial_id}")
        seen_trial_ids.add(trial_id)
        selected.append(
            _selected_measurement(row, metadata_by_record_id, index=index)
        )

    expected_measurements = (
        expected_instances * len(EXPECTED_CANDIDATES) * len(BALANCED_REPETITIONS)
    )
    if len(selected) != expected_measurements:
        raise EvaluationError(
            "balanced view requires exactly "
            f"{expected_measurements} included measured records, found {len(selected)}"
        )

    hashes_by_instance: dict[str, set[str]] = defaultdict(set)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    instance_measurements: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for measurement in selected:
        instance = measurement["problem_instance"]
        hashes_by_instance[instance].add(measurement["input_sha256"])
        grouped[(instance, measurement["candidate_name"])].append(measurement)
        instance_measurements[instance].append(measurement)

    if len(hashes_by_instance) != expected_instances:
        raise EvaluationError(
            f"balanced view requires {expected_instances} problem instances, "
            f"found {len(hashes_by_instance)}"
        )
    for instance, input_hashes in sorted(hashes_by_instance.items()):
        if len(input_hashes) != 1:
            raise EvaluationError(
                f"problem instance {instance!r} maps to multiple input hashes"
            )

    candidate_rows: list[dict[str, Any]] = []
    instance_summaries: list[dict[str, Any]] = []
    for instance in sorted(hashes_by_instance):
        measurements = instance_measurements[instance]
        problem_values = _consistent_problem_values(instance, measurements)
        guard_values = _consistent_guard_values(instance, measurements)
        caps = {
            "host_cap_bytes": min(
                measurement["memory"]["host_cap_bytes"]
                for measurement in measurements
            ),
            "gpu_cap_bytes": min(
                measurement["memory"]["gpu_cap_bytes"]
                for measurement in measurements
            ),
        }
        input_sha256 = next(iter(hashes_by_instance[instance]))
        instance_record_ids: list[str] = []

        for candidate_name, (backend, threads) in EXPECTED_CANDIDATES.items():
            members = grouped.get((instance, candidate_name), [])
            if len(members) != len(BALANCED_REPETITIONS):
                raise EvaluationError(
                    f"{instance}/{candidate_name} requires exactly three records"
                )
            members_by_repetition: dict[int, dict[str, Any]] = {}
            for member in members:
                repetition = member["repetition"]
                if repetition in members_by_repetition:
                    raise EvaluationError(
                        f"duplicate repetition {repetition} for "
                        f"{instance}/{candidate_name}"
                    )
                members_by_repetition[repetition] = member
                if member["backend"] != backend or member["cpu_threads"] != threads:
                    raise EvaluationError(
                        f"candidate identity mismatch for {instance}/{candidate_name}"
                    )
            if tuple(sorted(members_by_repetition)) != BALANCED_REPETITIONS:
                raise EvaluationError(
                    f"{instance}/{candidate_name} repetitions must be exactly 0,1,2"
                )
            ordered = [members_by_repetition[value] for value in BALANCED_REPETITIONS]
            wall_times = sorted(member["wall_time_s"] for member in ordered)
            median_wall = wall_times[1]
            feature_values = dict(problem_values)
            feature_values["backend_gpu"] = 1.0 if backend == "gpu" else 0.0
            feature_values["cpu_threads"] = float(threads)
            _validate_feature_mapping(feature_values, FULL_FEATURE_NAMES)
            record_ids = [member["trial_id"] for member in ordered]
            instance_record_ids.extend(record_ids)
            candidate_rows.append(
                {
                    "problem_instance": instance,
                    "input_sha256": input_sha256,
                    "candidate_name": candidate_name,
                    "backend": backend,
                    "cpu_threads": threads,
                    "n_configurations": problem_values["n_configurations"],
                    "median_wall_time_s": median_wall,
                    "target_log1p_median_wall_time_s": math.log1p(median_wall),
                    "feature_values": feature_values,
                    "memory_guard": dict(guard_values),
                    "memory_caps": dict(caps),
                    "repetitions": list(BALANCED_REPETITIONS),
                    "source_record_ids": record_ids,
                }
            )
        instance_summaries.append(
            {
                "problem_instance": instance,
                "input_sha256": input_sha256,
                "n_configurations": problem_values["n_configurations"],
                "memory_caps": caps,
                "source_record_ids": sorted(instance_record_ids),
            }
        )

    candidate_rows.sort(
        key=lambda row: (row["n_configurations"], row["problem_instance"], row["candidate_name"])
    )
    instance_summaries.sort(
        key=lambda row: (row["n_configurations"], row["problem_instance"])
    )
    dataset = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "dataset_type": "autosbd_balanced_candidate_medians",
        "analysis_view": {
            "phase": "measured",
            "repetitions": list(BALANCED_REPETITIONS),
            "aggregation": "median wall time per problem instance and candidate",
            "memory_cap_aggregation": (
                "minimum host/GPU admission cap across the selected records "
                "for each problem instance"
            ),
        },
        "feature_names": {
            "size_only": list(SIZE_ONLY_FEATURE_NAMES),
            "full": list(FULL_FEATURE_NAMES),
        },
        "target": "log1p(median end-to-end wall_time_s)",
        "record_counts": {
            "selected_measurements": len(selected),
            "candidate_rows": len(candidate_rows),
            "problem_instances": len(instance_summaries),
            "candidates_per_instance": len(EXPECTED_CANDIDATES),
            "repetitions_per_candidate": len(BALANCED_REPETITIONS),
        },
        "candidate_contract": [
            {
                "name": name,
                "backend": backend,
                "cpu_threads": threads,
            }
            for name, (backend, threads) in EXPECTED_CANDIDATES.items()
        ],
        "instances": instance_summaries,
        "rows": candidate_rows,
        "source_record_ids": sorted(seen_trial_ids),
    }
    _validate_jsonable(dataset, "balanced dataset")
    return dataset


def make_primary_split(dataset: Mapping[str, Any]) -> dict[str, Any]:
    """Hold out only the unique largest instance for strict extrapolation."""

    summaries = _instance_summaries(dataset)
    if len(summaries) < 2:
        raise EvaluationError("largest-size holdout requires at least two instances")
    largest_size = max(item["n_configurations"] for item in summaries)
    largest = [
        item for item in summaries if item["n_configurations"] == largest_size
    ]
    if len(largest) != 1:
        raise EvaluationError("strict largest-size holdout requires a unique maximum")
    test_ids = [largest[0]["problem_instance"]]
    train_ids = [
        item["problem_instance"]
        for item in summaries
        if item["problem_instance"] not in test_ids
    ]
    return _make_split(
        dataset,
        name="primary_strict_largest_size_holdout",
        train_instance_ids=train_ids,
        test_instance_ids=test_ids,
    )


def make_leave_one_instance_out_splits(
    dataset: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return deterministic leave-one-instance-out folds."""

    summaries = _instance_summaries(dataset)
    if len(summaries) != 5:
        raise EvaluationError(
            "the registered secondary analysis requires exactly five instances"
        )
    instance_ids = [item["problem_instance"] for item in summaries]
    folds: list[dict[str, Any]] = []
    for index, test_id in enumerate(instance_ids, start=1):
        folds.append(
            _make_split(
                dataset,
                name=f"secondary_leave_one_instance_out_{index:02d}",
                train_instance_ids=[
                    instance for instance in instance_ids if instance != test_id
                ],
                test_instance_ids=[test_id],
            )
        )
    return folds


def validate_split(dataset: Mapping[str, Any], split: Mapping[str, Any]) -> None:
    """Reject overlap, omitted instances, and record-level leakage."""

    if not isinstance(split, Mapping):
        raise EvaluationError("split must be an object")
    train_ids = _string_list(split.get("train_instance_ids"), "train_instance_ids")
    test_ids = _string_list(split.get("test_instance_ids"), "test_instance_ids")
    if not train_ids or not test_ids:
        raise EvaluationError("train and test instance sets must both be nonempty")
    train_set = set(train_ids)
    test_set = set(test_ids)
    if train_set.intersection(test_set):
        raise EvaluationError("train/test problem-instance leakage detected")
    dataset_ids = {
        item["problem_instance"] for item in _instance_summaries(dataset)
    }
    if train_set.union(test_set) != dataset_ids:
        raise EvaluationError("split must partition every dataset instance exactly once")

    expected_train_records = set(_source_ids(dataset, train_set))
    expected_test_records = set(_source_ids(dataset, test_set))
    if expected_train_records.intersection(expected_test_records):
        raise EvaluationError("train/test source-record leakage detected")
    if "train_source_record_ids" in split and set(
        _string_list(split["train_source_record_ids"], "train_source_record_ids")
    ) != expected_train_records:
        raise EvaluationError("split train_source_record_ids do not match instances")
    if "test_source_record_ids" in split and set(
        _string_list(split["test_source_record_ids"], "test_source_record_ids")
    ) != expected_test_records:
        raise EvaluationError("split test_source_record_ids do not match instances")


def fit_static_threshold(candidate_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Fit CPU-if-size<=T/GPU-otherwise using training rows only.

    Candidates are always-GPU, geometric midpoints between adjacent unique
    training sizes, and always-CPU, in that registered order.  The objective
    is the equal-instance geometric mean of selected/oracle median wall time.
    Objective ties retain the first registered candidate deterministically.
    """

    by_instance = _validate_candidate_rows(candidate_rows)
    sizes = sorted(
        {int(rows[0]["n_configurations"]) for rows in by_instance.values()}
    )
    threshold_candidates: list[dict[str, Any]] = [
        {"kind": "always_gpu", "threshold_n_configurations": None}
    ]
    threshold_candidates.extend(
        {
            "kind": "geometric_midpoint",
            "threshold_n_configurations": math.sqrt(lower * upper),
            "adjacent_training_sizes": [lower, upper],
        }
        for lower, upper in zip(sizes, sizes[1:])
    )
    threshold_candidates.append(
        {"kind": "always_cpu", "threshold_n_configurations": None}
    )
    objectives: list[dict[str, Any]] = []
    best_candidate: dict[str, Any] | None = None
    best_objective: float | None = None
    for threshold_candidate in threshold_candidates:
        normalized_runtimes: list[float] = []
        for rows in by_instance.values():
            candidates = {row["candidate_name"]: row for row in rows}
            n_configurations = int(rows[0]["n_configurations"])
            selected_name = select_with_static_threshold(
                threshold_candidate, n_configurations
            )
            selected_time = _positive_float(
                candidates[selected_name].get("median_wall_time_s"),
                "median_wall_time_s",
            )
            oracle_time = min(
                _positive_float(row.get("median_wall_time_s"), "median_wall_time_s")
                for row in rows
            )
            normalized_runtimes.append(selected_time / oracle_time)
        objective = geometric_mean(normalized_runtimes)
        objectives.append(
            {
                **threshold_candidate,
                "training_geometric_mean_selected_over_oracle": objective,
            }
        )
        if (
            best_objective is None
            or (
                objective < best_objective
                and not math.isclose(
                    objective, best_objective, rel_tol=1e-15, abs_tol=0.0
                )
            )
        ):
            best_candidate = threshold_candidate
            best_objective = objective
    assert best_candidate is not None and best_objective is not None
    result = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "policy_type": "training_only_static_size_threshold",
        "rule": "finite midpoint selects amd-cpu-16 at or below T and amd-l4-default above T; sentinel kinds select one backend unconditionally",
        "kind": best_candidate["kind"],
        "threshold_n_configurations": best_candidate[
            "threshold_n_configurations"
        ],
        "training_objective": "geometric mean of selected/oracle median wall time",
        "training_objective_value": best_objective,
        "tie_break": "registered candidate order on equal objective: always_gpu, geometric midpoints ascending, always_cpu",
        "candidate_objectives": objectives,
        "training_instance_ids": sorted(by_instance),
        "training_source_record_ids": sorted(
            record_id
            for rows in by_instance.values()
            for row in rows
            for record_id in _row_source_ids(row)
        ),
    }
    _validate_jsonable(result, "static threshold")
    return result


def select_with_static_threshold(
    model: Mapping[str, Any], n_configurations: int
) -> str:
    """Select a candidate using a fitted finite or sentinel threshold."""

    if not isinstance(model, Mapping):
        raise EvaluationError("static threshold model must be an object")
    size = _positive_int(n_configurations, "n_configurations")
    kind = _required_string(model, "kind", "static threshold model")
    threshold = model.get("threshold_n_configurations")
    if kind == "always_gpu":
        if threshold is not None:
            raise EvaluationError("always_gpu threshold must be null")
        return GPU_CANDIDATE
    if kind == "always_cpu":
        if threshold is not None:
            raise EvaluationError("always_cpu threshold must be null")
        return CPU_CANDIDATE
    if kind == "geometric_midpoint":
        finite_threshold = _positive_float(
            threshold, "threshold_n_configurations"
        )
        return CPU_CANDIDATE if size <= finite_threshold else GPU_CANDIDATE
    raise EvaluationError(f"unsupported static threshold kind {kind!r}")


def fit_runtime_tree(
    candidate_rows: Sequence[Mapping[str, Any]],
    *,
    feature_names: Sequence[str] = FULL_FEATURE_NAMES,
) -> dict[str, Any]:
    """Fit and deterministically export the fixed shallow runtime tree."""

    if sklearn.__version__ != REQUIRED_SKLEARN_VERSION:
        raise EvaluationError(
            f"scikit-learn {REQUIRED_SKLEARN_VERSION} is required; "
            f"found {sklearn.__version__}"
        )
    names = tuple(feature_names)
    if names not in (SIZE_ONLY_FEATURE_NAMES, FULL_FEATURE_NAMES):
        raise EvaluationError("feature_names must be the registered size-only or full set")
    by_instance = _validate_candidate_rows(candidate_rows)
    ordered_rows = sorted(
        (row for rows in by_instance.values() for row in rows),
        key=lambda row: (row["problem_instance"], row["candidate_name"]),
    )
    matrix = [
        _feature_vector(row.get("feature_values"), names, context="training row")
        for row in ordered_rows
    ]
    targets = [
        _finite_float(
            row.get("target_log1p_median_wall_time_s"),
            "target_log1p_median_wall_time_s",
        )
        for row in ordered_rows
    ]
    estimator = DecisionTreeRegressor(
        max_depth=TREE_MAX_DEPTH,
        min_samples_leaf=TREE_MIN_SAMPLES_LEAF,
        random_state=TREE_RANDOM_STATE,
    )
    estimator.fit(matrix, targets)
    nodes: list[dict[str, Any]] = []
    tree = estimator.tree_
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
            "max_depth": TREE_MAX_DEPTH,
            "min_samples_leaf": TREE_MIN_SAMPLES_LEAF,
            "random_state": TREE_RANDOM_STATE,
        },
        "training_instance_ids": sorted(by_instance),
        "training_source_record_ids": sorted(
            record_id
            for row in ordered_rows
            for record_id in _row_source_ids(row)
        ),
        "tree": {
            "node_count": int(tree.node_count),
            "actual_depth": int(tree.max_depth),
            "leaf_count": int(estimator.get_n_leaves()),
            "nodes": nodes,
        },
    }
    _validate_jsonable(model, "runtime tree")
    return model


def tree_model_json(model: Mapping[str, Any]) -> str:
    """Return a byte-stable compact JSON representation of an exported tree."""

    try:
        return json.dumps(
            model,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise EvaluationError(f"tree model is not strict JSON: {error}") from error


def predict_exported_tree(
    model: Mapping[str, Any], feature_values: Mapping[str, Any]
) -> float:
    """Traverse a JSON-exported tree and return predicted log runtime."""

    if not isinstance(model, Mapping):
        raise EvaluationError("model must be an object")
    names = tuple(_string_list(model.get("feature_names"), "model.feature_names"))
    vector = _feature_vector(feature_values, names, context="prediction")
    tree = model.get("tree")
    if not isinstance(tree, Mapping) or not isinstance(tree.get("nodes"), list):
        raise EvaluationError("model lacks tree nodes")
    nodes_list = tree["nodes"]
    nodes: dict[int, Mapping[str, Any]] = {}
    for raw_node in nodes_list:
        if not isinstance(raw_node, Mapping):
            raise EvaluationError("tree node is not an object")
        node_id = raw_node.get("node_id")
        if isinstance(node_id, bool) or not isinstance(node_id, int):
            raise EvaluationError("tree node_id must be an integer")
        if node_id in nodes:
            raise EvaluationError(f"duplicate tree node_id {node_id}")
        nodes[node_id] = raw_node
    node_id = 0
    visited: set[int] = set()
    while True:
        if node_id in visited:
            raise EvaluationError("tree contains a cycle")
        visited.add(node_id)
        node = nodes.get(node_id)
        if node is None:
            raise EvaluationError(f"tree references missing node {node_id}")
        node_type = node.get("type")
        if node_type == "leaf":
            return _finite_float(
                node.get("value_log1p_median_wall_time_s"),
                "leaf prediction",
            )
        if node_type != "split":
            raise EvaluationError(f"tree node {node_id} has invalid type")
        feature_index = node.get("feature_index")
        if (
            isinstance(feature_index, bool)
            or not isinstance(feature_index, int)
            or feature_index < 0
            or feature_index >= len(vector)
        ):
            raise EvaluationError(f"tree node {node_id} has invalid feature_index")
        threshold = _finite_float(node.get("threshold"), "tree threshold")
        child_key = "left_child" if vector[feature_index] <= threshold else "right_child"
        child = node.get(child_key)
        if isinstance(child, bool) or not isinstance(child, int):
            raise EvaluationError(f"tree node {node_id} has invalid {child_key}")
        node_id = child


def candidate_is_feasible(
    candidate_row: Mapping[str, Any],
    *,
    memory_caps: Mapping[str, Any] | None = None,
) -> bool:
    """Apply host/device guard-vs-cap admission before model prediction."""

    if not isinstance(candidate_row, Mapping):
        raise EvaluationError("candidate row must be an object")
    guard = candidate_row.get("memory_guard")
    caps = memory_caps if memory_caps is not None else candidate_row.get("memory_caps")
    if not isinstance(guard, Mapping) or not isinstance(caps, Mapping):
        raise EvaluationError("candidate row lacks memory guard or caps")
    host_cap = _nonnegative_int(caps.get("host_cap_bytes"), "host_cap_bytes")
    gpu_cap = _nonnegative_int(caps.get("gpu_cap_bytes"), "gpu_cap_bytes")
    backend = candidate_row.get("backend")
    if backend == "cpu":
        return (
            _nonnegative_int(guard.get("host_guard_bytes"), "host_guard_bytes")
            <= host_cap
        )
    if backend == "gpu":
        return (
            _nonnegative_int(
                guard.get("gpu_host_guard_bytes"), "gpu_host_guard_bytes"
            )
            <= host_cap
            and _nonnegative_int(guard.get("gpu_guard_bytes"), "gpu_guard_bytes")
            <= gpu_cap
        )
    raise EvaluationError(f"unsupported backend {backend!r}")


def select_with_tree(
    model: Mapping[str, Any],
    candidate_rows: Sequence[Mapping[str, Any]],
    *,
    memory_caps: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Filter infeasible candidates, then predict and select minimum runtime."""

    rows = list(candidate_rows)
    if not rows:
        raise EvaluationError("selection requires at least one candidate row")
    feasible = [
        row for row in rows if candidate_is_feasible(row, memory_caps=memory_caps)
    ]
    if not feasible:
        return {
            "selected_candidate_name": None,
            "predictions": [],
            "invalid_reason": "no_feasible_candidates",
        }
    predictions: list[dict[str, Any]] = []
    for row in sorted(feasible, key=lambda value: str(value.get("candidate_name"))):
        candidate_name = _required_string(row, "candidate_name", "candidate row")
        prediction = predict_exported_tree(model, row.get("feature_values"))
        predictions.append(
            {
                "candidate_name": candidate_name,
                "predicted_log1p_median_wall_time_s": prediction,
            }
        )
    selected = min(
        predictions,
        key=lambda value: (
            value["predicted_log1p_median_wall_time_s"],
            value["candidate_name"],
        ),
    )
    return {
        "selected_candidate_name": selected["candidate_name"],
        "predictions": predictions,
        "tie_break": "lexicographically smallest candidate name on equal prediction",
        "invalid_reason": None,
    }


def normalized_regret(selected_time_s: float, oracle_time_s: float) -> float:
    """Return ``(selected - oracle) / oracle`` for positive finite times."""

    selected = _positive_float(selected_time_s, "selected_time_s")
    oracle = _positive_float(oracle_time_s, "oracle_time_s")
    return (selected - oracle) / oracle


def geometric_mean(values: Sequence[float]) -> float:
    """Return a stable geometric mean of positive finite values."""

    if not values:
        raise EvaluationError("geometric mean requires at least one value")
    checked = [_positive_float(value, "geometric mean value") for value in values]
    return math.exp(math.fsum(math.log(value) for value in checked) / len(checked))


def summarize_policy_predictions(
    predictions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compute exact policy metrics; regret distributions are valid-only."""

    rows = list(predictions)
    if not rows:
        raise EvaluationError("policy summary requires at least one prediction")
    policies = {row.get("policy") for row in rows}
    if len(policies) != 1 or not isinstance(next(iter(policies)), str):
        raise EvaluationError("policy summary rows must share one policy name")
    total = len(rows)
    valid = [row for row in rows if row.get("valid") is True]
    invalid_count = total - len(valid)
    failure_count = sum(row.get("failure") is True for row in rows)
    selection_correct = sum(row.get("selection_correct") is True for row in rows)
    within_five = sum(row.get("within_5pct_oracle") is True for row in rows)

    regrets = [
        _finite_float(row.get("normalized_regret"), "normalized_regret")
        for row in valid
    ]
    normalized_runtimes = [
        _positive_float(row.get("normalized_runtime"), "normalized_runtime")
        for row in valid
    ]
    speedups_cpu = [
        _positive_float(row.get("speedup_vs_fixed_cpu"), "speedup_vs_fixed_cpu")
        for row in valid
        if row.get("speedup_vs_fixed_cpu") is not None
    ]
    speedups_gpu = [
        _positive_float(row.get("speedup_vs_fixed_gpu"), "speedup_vs_fixed_gpu")
        for row in valid
        if row.get("speedup_vs_fixed_gpu") is not None
    ]
    result = {
        "policy": next(iter(policies)),
        "instances_total": total,
        "valid_instances": len(valid),
        "invalid_instances": invalid_count,
        "invalid_rate": invalid_count / total,
        "failure_count": failure_count,
        "failure_rate": failure_count / total,
        "selection_accuracy": selection_correct / total,
        "within_5pct_oracle_rate": within_five / total,
        "geometric_mean_selected_over_oracle_valid_only": (
            geometric_mean(normalized_runtimes) if normalized_runtimes else None
        ),
        "geometric_mean_oracle_over_selected_valid_only": (
            geometric_mean([1.0 / value for value in normalized_runtimes])
            if normalized_runtimes
            else None
        ),
        "median_normalized_regret_valid_only": (
            _linear_percentile(regrets, 0.5) if regrets else None
        ),
        "p90_normalized_regret_valid_only": (
            _linear_percentile(regrets, 0.9) if regrets else None
        ),
        "maximum_normalized_regret_valid_only": max(regrets) if regrets else None,
        "geometric_mean_speedup_vs_fixed_cpu_valid_only": (
            geometric_mean(speedups_cpu) if len(speedups_cpu) == len(valid) and valid else None
        ),
        "geometric_mean_speedup_vs_fixed_gpu_valid_only": (
            geometric_mean(speedups_gpu) if len(speedups_gpu) == len(valid) and valid else None
        ),
        "definitions": {
            "normalized_regret": "(selected_wall_time - oracle_wall_time) / oracle_wall_time",
            "selection_accuracy_denominator": "all requested problem instances; invalid is incorrect",
            "invalid_and_failure_denominator": "all requested problem instances",
            "percentile_method": "linear interpolation at zero-based position (n - 1) * p",
        },
    }
    _validate_jsonable(result, "policy metrics")
    return result


def evaluate_fold(
    dataset: Mapping[str, Any], split: Mapping[str, Any]
) -> dict[str, Any]:
    """Train on a split's train instances and evaluate all registered policies."""

    validate_split(dataset, split)
    all_rows = _dataset_rows(dataset)
    train_ids = set(split["train_instance_ids"])
    test_ids = set(split["test_instance_ids"])
    train_rows = [row for row in all_rows if row["problem_instance"] in train_ids]
    test_rows = [row for row in all_rows if row["problem_instance"] in test_ids]
    threshold = fit_static_threshold(train_rows)
    full_model = fit_runtime_tree(train_rows, feature_names=FULL_FEATURE_NAMES)
    size_model = fit_runtime_tree(train_rows, feature_names=SIZE_ONLY_FEATURE_NAMES)

    by_test: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in test_rows:
        by_test[row["problem_instance"]].append(row)
    predictions: list[dict[str, Any]] = []
    for instance in sorted(by_test):
        rows = sorted(by_test[instance], key=lambda row: row["candidate_name"])
        by_name = {row["candidate_name"]: row for row in rows}
        caps = _consistent_caps(rows)
        feasible_rows = [row for row in rows if candidate_is_feasible(row, memory_caps=caps)]
        oracle_rows: list[Mapping[str, Any]] = []
        if feasible_rows:
            oracle_time = min(
                _positive_float(row["median_wall_time_s"], "median_wall_time_s")
                for row in feasible_rows
            )
            oracle_rows = [
                row
                for row in feasible_rows
                if math.isclose(
                    _positive_float(row["median_wall_time_s"], "median_wall_time_s"),
                    oracle_time,
                    rel_tol=1e-15,
                    abs_tol=0.0,
                )
            ]
        else:
            oracle_time = None

        n_configurations = int(rows[0]["n_configurations"])
        threshold_name = select_with_static_threshold(threshold, n_configurations)
        full_selection = select_with_tree(full_model, rows, memory_caps=caps)
        size_selection = select_with_tree(size_model, rows, memory_caps=caps)
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
            decision_name, model_predictions = decisions[policy]
            predictions.append(
                _policy_prediction(
                    policy=policy,
                    decision_candidate_name=decision_name,
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
        "evaluation_type": "autosbd_held_out_fold",
        "split": dict(split),
        "models": {
            POLICY_THRESHOLD: threshold,
            POLICY_FULL_TREE: full_model,
            POLICY_SIZE_TREE: size_model,
        },
        "policy_aliases": {POLICY_UPSTREAM_DEFAULT: POLICY_FIXED_GPU},
        "predictions": predictions,
        "metrics": metrics,
        "training_source_record_ids": sorted(
            record_id for row in train_rows for record_id in _row_source_ids(row)
        ),
        "test_source_record_ids": sorted(
            record_id for row in test_rows for record_id in _row_source_ids(row)
        ),
    }
    _validate_jsonable(result, "fold evaluation")
    return result


def evaluate_selector(dataset: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate the primary split and five secondary out-of-fold predictions."""

    primary = evaluate_fold(dataset, make_primary_split(dataset))
    secondary_folds = [
        evaluate_fold(dataset, split)
        for split in make_leave_one_instance_out_splits(dataset)
    ]
    out_of_fold_predictions = [
        prediction
        for fold in secondary_folds
        for prediction in fold["predictions"]
    ]
    secondary_metrics = {
        policy: summarize_policy_predictions(
            [
                row
                for row in out_of_fold_predictions
                if row["policy"] == policy
            ]
        )
        for policy in POLICY_ORDER
    }
    result = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "evaluation_type": "autosbd_selector_evaluation",
        "source_record_ids": list(dataset.get("source_record_ids", [])),
        "primary": primary,
        "secondary_leave_one_instance_out": {
            "folds": secondary_folds,
            "predictions": out_of_fold_predictions,
            "metrics": secondary_metrics,
        },
    }
    _validate_jsonable(result, "selector evaluation")
    return result


def _selected_measurement(
    row: Mapping[str, Any],
    metadata_by_record_id: Mapping[str, Mapping[str, Any]] | None,
    *,
    index: int,
) -> dict[str, Any]:
    context = f"aggregate row {index}"
    trial_id = _required_string(row, "trial_id", context)
    problem_instance = _required_string(row, "problem_instance", context)
    input_sha256 = _required_string(row, "input_sha256", context)
    candidate = row.get("candidate")
    if not isinstance(candidate, Mapping):
        raise EvaluationError(f"{context} lacks candidate identity")
    candidate_name = _required_string(candidate, "name", f"{context}.candidate")
    if candidate_name not in EXPECTED_CANDIDATES:
        raise EvaluationError(f"unexpected candidate {candidate_name!r}")
    backend = _required_string(candidate, "backend", f"{context}.candidate")
    threads = _positive_int(candidate.get("cpu_threads"), "candidate.cpu_threads")
    repetition = row.get("repetition")
    if isinstance(repetition, bool) or not isinstance(repetition, int):
        raise EvaluationError(f"{context} has invalid repetition")
    wall = _positive_float(_mapping_path(row, ("times_s", "wall")), "wall_time_s")
    features = row.get("features")
    if not isinstance(features, Mapping):
        raise EvaluationError(f"{context} lacks pre-execution features")

    metadata: Mapping[str, Any] = row
    if metadata_by_record_id is not None and trial_id in metadata_by_record_id:
        metadata = metadata_by_record_id[trial_id]
        if not isinstance(metadata, Mapping):
            raise EvaluationError(f"metadata for {trial_id} is not an object")
    for key, expected in (
        ("trial_id", trial_id),
        ("problem_instance", problem_instance),
        ("input_sha256", input_sha256),
    ):
        if key in metadata and metadata.get(key) != expected:
            raise EvaluationError(f"metadata {key} mismatch for {trial_id}")
    memory = _memory_metadata(metadata, trial_id)
    problem_values = _problem_feature_values(features, memory, context=trial_id)
    return {
        "trial_id": trial_id,
        "problem_instance": problem_instance,
        "input_sha256": input_sha256,
        "candidate_name": candidate_name,
        "backend": backend,
        "cpu_threads": threads,
        "repetition": repetition,
        "wall_time_s": wall,
        "problem_values": problem_values,
        "memory": memory,
    }


def _memory_metadata(metadata: Mapping[str, Any], trial_id: str) -> dict[str, int]:
    estimate = metadata.get("source_memory_estimate")
    if not isinstance(estimate, Mapping):
        preexecution = metadata.get("preexecution_metadata")
        if isinstance(preexecution, Mapping):
            estimate = preexecution.get("source_memory_estimate")
    if not isinstance(estimate, Mapping):
        raise EvaluationError(
            f"record {trial_id} lacks source_memory_estimate; provide raw metadata"
        )
    cache = metadata.get("estimated_cache_bytes")
    if cache is None:
        cache = estimate.get("determinant_cache_bytes")
    preflight = metadata.get("preflight")
    if not isinstance(preflight, Mapping):
        preflight = metadata.get("memory_caps")
    if not isinstance(preflight, Mapping):
        raise EvaluationError(
            f"record {trial_id} lacks pre-execution memory admission caps"
        )
    return {
        "determinant_cache_bytes": _nonnegative_int(
            cache, "determinant_cache_bytes"
        ),
        "host_guard_bytes": _nonnegative_int(
            estimate.get("host_guard_bytes"), "host_guard_bytes"
        ),
        "gpu_host_guard_bytes": _nonnegative_int(
            estimate.get("gpu_host_guard_bytes"), "gpu_host_guard_bytes"
        ),
        "gpu_guard_bytes": _nonnegative_int(
            estimate.get("gpu_guard_bytes"), "gpu_guard_bytes"
        ),
        "host_cap_bytes": _nonnegative_int(
            preflight.get("host_memory_cap_bytes", preflight.get("host_cap_bytes")),
            "host_cap_bytes",
        ),
        "gpu_cap_bytes": _nonnegative_int(
            preflight.get("gpu_memory_cap_bytes", preflight.get("gpu_cap_bytes")),
            "gpu_cap_bytes",
        ),
    }


def _problem_feature_values(
    features: Mapping[str, Any], memory: Mapping[str, int], *, context: str
) -> dict[str, float | int]:
    n_configurations = _positive_int(
        features.get("n_configurations"), f"{context}.n_configurations"
    )
    logged_n = _finite_float(
        features.get("log1p_n_configurations"),
        f"{context}.log1p_n_configurations",
    )
    _require_log_matches(logged_n, n_configurations, "log1p_n_configurations")
    method0_work = _nonnegative_int(
        features.get("method0_work_proxy"), f"{context}.method0_work_proxy"
    )
    logged_work = _finite_float(
        features.get("log1p_method0_work_proxy"),
        f"{context}.log1p_method0_work_proxy",
    )
    _require_log_matches(logged_work, method0_work, "log1p_method0_work_proxy")
    connectivity = features.get("connectivity")
    if not isinstance(connectivity, Mapping):
        raise EvaluationError(f"{context} lacks connectivity features")
    alpha = connectivity.get("alpha")
    beta = connectivity.get("beta")
    if not isinstance(alpha, Mapping) or not isinstance(beta, Mapping):
        raise EvaluationError(f"{context} has incomplete connectivity features")
    result: dict[str, float | int] = {
        "n_configurations": n_configurations,
        "log1p_n_configurations": logged_n,
        "log1p_method0_work_proxy": logged_work,
        "log1p_determinant_cache_bytes": math.log1p(
            memory["determinant_cache_bytes"]
        ),
        "log1p_gpu_guard_bytes": math.log1p(memory["gpu_guard_bytes"]),
        "alpha_single_edge_density": _density(
            alpha.get("single_edge_density"),
            f"{context}.connectivity.alpha.single_edge_density",
        ),
        "alpha_double_edge_density": _density(
            alpha.get("double_edge_density"),
            f"{context}.connectivity.alpha.double_edge_density",
        ),
        "beta_single_edge_density": _density(
            beta.get("single_edge_density"),
            f"{context}.connectivity.beta.single_edge_density",
        ),
        "beta_double_edge_density": _density(
            beta.get("double_edge_density"),
            f"{context}.connectivity.beta.double_edge_density",
        ),
    }
    return result


def _consistent_problem_values(
    instance: str, measurements: Sequence[Mapping[str, Any]]
) -> dict[str, float | int]:
    first = dict(measurements[0]["problem_values"])
    for measurement in measurements[1:]:
        if dict(measurement["problem_values"]) != first:
            raise EvaluationError(
                f"pre-execution feature mismatch across records for {instance}"
            )
    return first


def _consistent_guard_values(
    instance: str, measurements: Sequence[Mapping[str, Any]]
) -> dict[str, int]:
    keys = ("host_guard_bytes", "gpu_host_guard_bytes", "gpu_guard_bytes")
    first = {key: int(measurements[0]["memory"][key]) for key in keys}
    for measurement in measurements[1:]:
        current = {key: int(measurement["memory"][key]) for key in keys}
        if current != first:
            raise EvaluationError(
                f"source memory estimate mismatch across records for {instance}"
            )
    return first


def _instance_summaries(dataset: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    _dataset_rows(dataset)
    instances = dataset.get("instances")
    if not isinstance(instances, list) or not instances:
        raise EvaluationError("dataset lacks instance summaries")
    checked: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for item in instances:
        if not isinstance(item, Mapping):
            raise EvaluationError("dataset instance summary is not an object")
        name = _required_string(item, "problem_instance", "instance summary")
        if name in seen:
            raise EvaluationError(f"duplicate instance summary {name}")
        seen.add(name)
        _positive_int(item.get("n_configurations"), "n_configurations")
        checked.append(item)
    return sorted(
        checked,
        key=lambda item: (item["n_configurations"], item["problem_instance"]),
    )


def _dataset_rows(dataset: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if not isinstance(dataset, Mapping):
        raise EvaluationError("dataset must be an object")
    rows = dataset.get("rows")
    if not isinstance(rows, list) or not rows:
        raise EvaluationError("dataset lacks candidate rows")
    checked: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise EvaluationError("candidate row is not an object")
        checked.append(row)
    _validate_candidate_rows(checked)
    return checked


def _make_split(
    dataset: Mapping[str, Any],
    *,
    name: str,
    train_instance_ids: Sequence[str],
    test_instance_ids: Sequence[str],
) -> dict[str, Any]:
    train = sorted(train_instance_ids)
    test = sorted(test_instance_ids)
    split = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "name": name,
        "group_key": "problem_instance (all candidates and repetitions remain together)",
        "train_instance_ids": train,
        "test_instance_ids": test,
        "train_source_record_ids": sorted(_source_ids(dataset, set(train))),
        "test_source_record_ids": sorted(_source_ids(dataset, set(test))),
    }
    validate_split(dataset, split)
    return split


def _source_ids(dataset: Mapping[str, Any], instance_ids: set[str]) -> list[str]:
    return [
        record_id
        for row in _dataset_rows(dataset)
        if row["problem_instance"] in instance_ids
        for record_id in _row_source_ids(row)
    ]


def _row_source_ids(row: Mapping[str, Any]) -> list[str]:
    return _string_list(row.get("source_record_ids"), "source_record_ids")


def _validate_candidate_rows(
    candidate_rows: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    rows = list(candidate_rows)
    if not rows:
        raise EvaluationError("at least one candidate row is required")
    by_instance: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    seen_records: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise EvaluationError("candidate row must be an object")
        instance = _required_string(row, "problem_instance", "candidate row")
        candidate_name = _required_string(row, "candidate_name", "candidate row")
        if candidate_name not in EXPECTED_CANDIDATES:
            raise EvaluationError(f"unexpected candidate {candidate_name!r}")
        _positive_int(row.get("n_configurations"), "n_configurations")
        _positive_float(row.get("median_wall_time_s"), "median_wall_time_s")
        source_ids = _row_source_ids(row)
        if len(source_ids) != len(BALANCED_REPETITIONS):
            raise EvaluationError("candidate row must cite exactly three source records")
        overlap = seen_records.intersection(source_ids)
        if overlap:
            raise EvaluationError(f"source record reused across candidate rows: {sorted(overlap)}")
        seen_records.update(source_ids)
        by_instance[instance].append(row)
    for instance, instance_rows in by_instance.items():
        names = [row["candidate_name"] for row in instance_rows]
        if len(names) != len(EXPECTED_CANDIDATES) or set(names) != set(
            EXPECTED_CANDIDATES
        ):
            raise EvaluationError(
                f"{instance} must have exactly the registered CPU and GPU candidates"
            )
        sizes = {row["n_configurations"] for row in instance_rows}
        if len(sizes) != 1:
            raise EvaluationError(f"candidate size mismatch for {instance}")
    return dict(sorted(by_instance.items()))


def _consistent_caps(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    first = rows[0].get("memory_caps")
    if not isinstance(first, Mapping):
        raise EvaluationError("candidate row lacks memory_caps")
    caps = {
        "host_cap_bytes": _nonnegative_int(first.get("host_cap_bytes"), "host_cap_bytes"),
        "gpu_cap_bytes": _nonnegative_int(first.get("gpu_cap_bytes"), "gpu_cap_bytes"),
    }
    for row in rows[1:]:
        other = row.get("memory_caps")
        if not isinstance(other, Mapping) or dict(other) != caps:
            raise EvaluationError("memory caps differ across candidates for one instance")
    return caps


def _policy_prediction(
    *,
    policy: str,
    decision_candidate_name: str | None,
    model_predictions: Any,
    by_name: Mapping[str, Mapping[str, Any]],
    caps: Mapping[str, Any],
    oracle_rows: Sequence[Mapping[str, Any]],
    oracle_time: float | None,
) -> dict[str, Any]:
    representative = next(iter(by_name.values()))
    oracle_names = sorted(row["candidate_name"] for row in oracle_rows)
    oracle_source_ids = sorted(
        record_id for row in oracle_rows for record_id in _row_source_ids(row)
    )
    base: dict[str, Any] = {
        "policy": policy,
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
    selected_time = _positive_float(selected["median_wall_time_s"], "median_wall_time_s")
    cpu_time = _positive_float(
        by_name[CPU_CANDIDATE]["median_wall_time_s"], "CPU median wall time"
    )
    gpu_time = _positive_float(
        by_name[GPU_CANDIDATE]["median_wall_time_s"], "GPU median wall time"
    )
    normalized_runtime = selected_time / oracle_time
    base.update(
        {
            "selected_candidate_name": decision_candidate_name,
            "selected_source_record_ids": _row_source_ids(selected),
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


def _feature_vector(
    feature_values: Any, feature_names: Sequence[str], *, context: str
) -> list[float]:
    if not isinstance(feature_values, Mapping):
        raise EvaluationError(f"{context} lacks feature_values")
    return [
        _finite_float(feature_values.get(name), f"{context}.{name}")
        for name in feature_names
    ]


def _validate_feature_mapping(
    feature_values: Mapping[str, Any], feature_names: Sequence[str]
) -> None:
    _feature_vector(feature_values, feature_names, context="candidate features")


def _require_log_matches(logged: float, raw: int, name: str) -> None:
    expected = math.log1p(raw)
    if not math.isclose(logged, expected, rel_tol=1e-12, abs_tol=1e-12):
        raise EvaluationError(f"{name} does not match its raw pre-execution value")


def _density(value: Any, name: str) -> float:
    result = _finite_float(value, name)
    if not 0.0 <= result <= 1.0:
        raise EvaluationError(f"{name} must be between zero and one")
    return result


def _mapping_path(mapping: Mapping[str, Any], path: Sequence[str]) -> Any:
    value: Any = mapping
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _required_string(mapping: Mapping[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise EvaluationError(f"{context} has invalid {key}")
    return value


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise EvaluationError(f"{name} must be a list of nonempty strings")
    if len(set(value)) != len(value):
        raise EvaluationError(f"{name} contains duplicates")
    return list(value)


def _finite_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EvaluationError(f"{name} must be finite")
    return result


def _positive_float(value: Any, name: str) -> float:
    result = _finite_float(value, name)
    if result <= 0.0:
        raise EvaluationError(f"{name} must be positive")
    return result


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvaluationError(f"{name} must be a nonnegative integer")
    return value


def _positive_int(value: Any, name: str) -> int:
    result = _nonnegative_int(value, name)
    if result == 0:
        raise EvaluationError(f"{name} must be positive")
    return result


def _require_positive_int(name: str, value: Any) -> int:
    return _positive_int(value, name)


def _linear_percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise EvaluationError("percentile requires at least one value")
    ordered = sorted(_finite_float(value, "percentile value") for value in values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _validate_jsonable(value: Any, context: str) -> None:
    try:
        json.dumps(value, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as error:
        raise EvaluationError(f"{context} is not strict JSON: {error}") from error
