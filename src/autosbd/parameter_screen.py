"""Strict, deterministic analysis of the frozen Phase C parameter screen.

The analyzer intentionally performs no file discovery, imputation, pruning, or
model fitting.  It derives raw-record paths only from the supplied aggregate's
explicit record IDs, verifies that deterministic aggregation of those records
exactly reproduces the supplied aggregate, and then reports direct descriptive
comparisons for the complete frozen factorial design.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .analysis import AnalysisError, aggregate_records, summarize_values
from .records import RecordError, canonical_json, validate_record


PARAMETER_SCREEN_SCHEMA_VERSION = 1
PARAMETER_SCREEN_ANALYSIS_TYPE = "autosbd_phasec_parameter_screen"
UPSTREAM_URL = "https://github.com/AMD-HPC/amd-sbd"
UPSTREAM_COMMIT = "729cfa3a5011fb805eb9e686a7711f6919836dcb"
EXPECTED_WARMUP_REPETITIONS = (0,)
EXPECTED_MEASURED_REPETITIONS = (0,)

# The order is scientific protocol, not discovery order.  It is also used for
# deterministic output ordering.
EXPECTED_WORKLOADS: tuple[dict[str, Any], ...] = (
    {
        "family_id": "fe4s4",
        "molecule": "Fe4S4",
        "basis": "upstream-not-reported",
        "problem_instance": "fe4s4-prefix-0032",
        "n_configurations": 1024,
    },
    {
        "family_id": "fe4s4",
        "molecule": "Fe4S4",
        "basis": "upstream-not-reported",
        "problem_instance": "fe4s4-prefix-0055",
        "n_configurations": 3025,
    },
    {
        "family_id": "fe4s4",
        "molecule": "Fe4S4",
        "basis": "upstream-not-reported",
        "problem_instance": "fe4s4-prefix-0244",
        "n_configurations": 59536,
    },
    {
        "family_id": "n2",
        "molecule": "N2",
        "basis": "6-31G",
        "problem_instance": "n2-prefix-0032",
        "n_configurations": 1024,
    },
    {
        "family_id": "n2",
        "molecule": "N2",
        "basis": "6-31G",
        "problem_instance": "n2-prefix-0055",
        "n_configurations": 3025,
    },
    {
        "family_id": "n2",
        "molecule": "N2",
        "basis": "6-31G",
        "problem_instance": "n2-prefix-0239",
        "n_configurations": 57121,
    },
    {
        "family_id": "h2o",
        "molecule": "H2O",
        "basis": "cc-pVDZ",
        "problem_instance": "h2o-prefix-0032",
        "n_configurations": 1024,
    },
    {
        "family_id": "h2o",
        "molecule": "H2O",
        "basis": "cc-pVDZ",
        "problem_instance": "h2o-prefix-0100",
        "n_configurations": 10000,
    },
    {
        "family_id": "h2o",
        "molecule": "H2O",
        "basis": "cc-pVDZ",
        "problem_instance": "h2o-prefix-0275",
        "n_configurations": 75625,
    },
)

EXPECTED_CANDIDATES: tuple[dict[str, Any], ...] = tuple(
    {
        "name": f"amd-{'cpu16' if backend == 'cpu' else 'l4'}-b{bit_length}-s{shuffle}",
        "backend": backend,
        "cpu_threads": 16 if backend == "cpu" else 1,
        "bit_length": bit_length,
        "shuffle": bool(shuffle),
    }
    for bit_length, shuffle in ((20, 0), (20, 1), (48, 0), (48, 1))
    for backend in ("cpu", "gpu")
)

_FAMILY_ORDER = {name: index for index, name in enumerate(("fe4s4", "n2", "h2o"))}
_WORKLOAD_ORDER = {
    row["problem_instance"]: index for index, row in enumerate(EXPECTED_WORKLOADS)
}
_CANDIDATE_ORDER = {
    row["name"]: index for index, row in enumerate(EXPECTED_CANDIDATES)
}
_PAIR_FACTOR_ORDER = {name: index for index, name in enumerate(("backend", "bit_length", "shuffle"))}

_CSV_FIELDS = (
    "row_type",
    "scope",
    "factor",
    "family_id",
    "molecule",
    "basis",
    "problem_instance",
    "n_configurations",
    "input_sha256",
    "candidate_name",
    "backend",
    "cpu_threads",
    "bit_length",
    "shuffle",
    "trial_id",
    "repetition",
    "wall_time_s",
    "solver_time_s",
    "wall_rank",
    "solver_rank",
    "wall_regret_over_oracle",
    "solver_regret_over_oracle",
    "wall_oracle_winner",
    "solver_oracle_winner",
    "left_level",
    "right_level",
    "fixed_factors",
    "left_candidate",
    "right_candidate",
    "wall_ratio_left_over_right",
    "solver_ratio_left_over_right",
    "wall_winner",
    "solver_winner",
    "count",
    "wall_time_summary",
    "solver_time_summary",
    "wall_ratio_summary",
    "solver_ratio_summary",
    "wall_left_wins",
    "wall_right_wins",
    "wall_ties",
    "solver_left_wins",
    "solver_right_wins",
    "solver_ties",
    "wall_oracle_win_count",
    "solver_oracle_win_count",
)


class ParameterScreenError(ValueError):
    """Raised when Phase C evidence or output is incomplete or inconsistent."""


def build_parameter_screen_analysis(
    aggregate_path: str | os.PathLike[str],
    raw_directory: str | os.PathLike[str],
    *,
    repository_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Verify sealed evidence and build the complete descriptive analysis."""

    root = Path(repository_root or Path.cwd()).resolve(strict=True)
    aggregate_file = _regular_file_inside(aggregate_path, root, "aggregate")
    raw_dir = _directory_inside(raw_directory, root, "raw directory")
    aggregate = _load_strict_object(aggregate_file, "aggregate")
    record_ids = _validate_aggregate_header(aggregate)

    records: list[dict[str, Any]] = []
    raw_claims: list[dict[str, Any]] = []
    raw_paths: list[Path] = []
    for trial_id in record_ids:
        raw_path = _regular_file_inside(
            raw_dir / f"{trial_id}.json", root, f"raw record {trial_id}"
        )
        if raw_path.parent != raw_dir:
            raise ParameterScreenError(f"raw record path escapes raw directory: {trial_id}")
        record = _load_strict_object(raw_path, f"raw record {trial_id}")
        try:
            validate_record(record)
        except RecordError as error:
            raise ParameterScreenError(f"invalid raw record {trial_id}: {error}") from error
        if record.get("trial_id") != trial_id:
            raise ParameterScreenError(f"raw record filename/ID mismatch: {trial_id}")
        records.append(record)
        raw_paths.append(raw_path)
        raw_claims.append(_file_claim(raw_path, root, trial_id=trial_id))

    try:
        recomputed = aggregate_records(raw_paths)
    except AnalysisError as error:
        raise ParameterScreenError(f"cannot recompute timing aggregate: {error}") from error
    if canonical_json(recomputed) != canonical_json(aggregate):
        raise ParameterScreenError(
            "aggregate does not exactly match deterministic recomputation from raw IDs"
        )

    measurements, design_evidence = _validate_and_extract_measurements(records)
    workload_results = _workload_results(measurements)
    paired_effects = _paired_effects(measurements)
    summaries = _summaries(workload_results, paired_effects)
    csv_rows = _csv_rows(measurements, paired_effects, summaries)

    aggregate_claim = _file_claim(aggregate_file, root)
    raw_claims.sort(key=lambda row: str(row["trial_id"]))
    evidence = {
        "aggregate": aggregate_claim,
        "aggregate_recomputed_exactly": True,
        "raw_record_count": len(raw_claims),
        "raw_records": raw_claims,
        "raw_claims_sha256": hashlib.sha256(
            canonical_json(raw_claims).encode("utf-8")
        ).hexdigest(),
        **design_evidence,
    }
    result = {
        "schema_version": PARAMETER_SCREEN_SCHEMA_VERSION,
        "analysis_type": PARAMETER_SCREEN_ANALYSIS_TYPE,
        "evidence": evidence,
        "design": {
            "workloads": [dict(row) for row in EXPECTED_WORKLOADS],
            "candidates": [dict(row) for row in EXPECTED_CANDIDATES],
            "warmup_repetitions": list(EXPECTED_WARMUP_REPETITIONS),
            "measured_repetitions": list(EXPECTED_MEASURED_REPETITIONS),
            "factor_levels": {
                "backend": ["cpu", "gpu"],
                "bit_length": [20, 48],
                "shuffle": [False, True],
            },
            "measurement_count": len(measurements),
            "paired_effect_count": len(paired_effects),
        },
        "analysis_boundary": {
            "descriptive_observed_measurements_only": True,
            "missing_measurements_imputed": False,
            "configuration_pruning_performed": False,
            "model_fitting_performed": False,
            "statistical_significance_claimed": False,
        },
        "measurements": measurements,
        "workload_results": workload_results,
        "paired_effects": paired_effects,
        "summaries": summaries,
        "csv_rows": csv_rows,
    }
    _validate_output(result)
    return result


def write_parameter_screen_outputs(
    analysis: Mapping[str, Any],
    output_json: str | os.PathLike[str],
    output_csv: str | os.PathLike[str],
) -> dict[str, Any]:
    """Atomically write deterministic JSON and unified long-form CSV."""

    _validate_output(analysis)
    json_path = Path(output_json)
    csv_path = Path(output_csv)
    if json_path.resolve() == csv_path.resolve():
        raise ParameterScreenError("JSON and CSV output paths must differ")
    json_payload = (
        json.dumps(analysis, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    csv_payload = _render_csv(analysis["csv_rows"])
    json_changed = _atomic_write_changed(json_path, json_payload)
    csv_changed = _atomic_write_changed(csv_path, csv_payload)
    return {
        "json_changed": json_changed,
        "csv_changed": csv_changed,
        "raw_records": analysis["evidence"]["raw_record_count"],
        "measurements": analysis["design"]["measurement_count"],
        "paired_effects": analysis["design"]["paired_effect_count"],
    }


def analyze_and_write_parameter_screen(
    aggregate_path: str | os.PathLike[str],
    raw_directory: str | os.PathLike[str],
    output_json: str | os.PathLike[str],
    output_csv: str | os.PathLike[str],
    *,
    repository_root: str | os.PathLike[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a verified analysis and atomically write its two artifacts."""

    analysis = build_parameter_screen_analysis(
        aggregate_path, raw_directory, repository_root=repository_root
    )
    return analysis, write_parameter_screen_outputs(analysis, output_json, output_csv)


def _validate_aggregate_header(aggregate: Mapping[str, Any]) -> tuple[str, ...]:
    if aggregate.get("schema_version") != 2:
        raise ParameterScreenError("aggregate must be family-aware schema_version 2")
    if aggregate.get("record_schema_version") != 3:
        raise ParameterScreenError("aggregate must contain schema-v3 raw records")
    if aggregate.get("analysis_type") != "autosbd_timing_aggregation":
        raise ParameterScreenError("aggregate analysis_type differs")
    expected_measurements = len(EXPECTED_WORKLOADS) * len(EXPECTED_CANDIDATES)
    expected_inputs = expected_measurements * (
        len(EXPECTED_WARMUP_REPETITIONS) + len(EXPECTED_MEASURED_REPETITIONS)
    )
    if aggregate.get("record_counts") != {
        "input": expected_inputs,
        "included": expected_measurements,
        "excluded": expected_measurements,
    }:
        raise ParameterScreenError("aggregate record counts do not match 144/72/72")
    record_ids = aggregate.get("input_record_ids")
    if (
        not isinstance(record_ids, list)
        or len(record_ids) != expected_inputs
        or record_ids != sorted(record_ids)
        or len(set(record_ids)) != len(record_ids)
        or not all(_is_sha256(value) for value in record_ids)
    ):
        raise ParameterScreenError("aggregate input_record_ids are not 144 unique sorted SHAs")
    return tuple(record_ids)


def _validate_and_extract_measurements(
    records: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_count = len(EXPECTED_WORKLOADS) * len(EXPECTED_CANDIDATES) * 2
    if len(records) != expected_count:
        raise ParameterScreenError(f"expected {expected_count} raw records")
    workload_by_name = {row["problem_instance"]: row for row in EXPECTED_WORKLOADS}
    candidate_by_name = {row["name"]: row for row in EXPECTED_CANDIDATES}
    geometry: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    measured: list[dict[str, Any]] = []
    sweep_names: set[str] = set()
    validation_shas: set[str] = set()
    input_hashes: dict[str, str] = {}

    for record in records:
        trial_id = str(record.get("trial_id", "<unknown>"))
        if record.get("schema_version") != 3:
            raise ParameterScreenError(f"record {trial_id} is not schema version 3")
        workload_name = record.get("problem_instance")
        expected_workload = workload_by_name.get(workload_name)
        if expected_workload is None:
            raise ParameterScreenError(f"unexpected Phase C workload: {workload_name!r}")
        for field in ("family_id", "molecule", "basis"):
            if record.get(field) != expected_workload[field]:
                raise ParameterScreenError(f"record {trial_id} workload {field} differs")
        if record.get("n_configurations") != expected_workload["n_configurations"]:
            raise ParameterScreenError(f"record {trial_id} configuration count differs")

        input_sha = record.get("input_sha256")
        if not _is_sha256(input_sha):
            raise ParameterScreenError(f"record {trial_id} has invalid input hash")
        previous_hash = input_hashes.setdefault(str(workload_name), str(input_sha))
        if previous_hash != input_sha:
            raise ParameterScreenError(f"workload {workload_name} has inconsistent input hash")

        logical = _mapping(record.get("logical_identity"), f"record {trial_id} logical identity")
        candidate_identity = _mapping(
            logical.get("candidate"), f"record {trial_id} candidate identity"
        )
        candidate_name = candidate_identity.get("name")
        expected_candidate = candidate_by_name.get(candidate_name)
        if expected_candidate is None:
            raise ParameterScreenError(f"unexpected Phase C candidate: {candidate_name!r}")
        expected_identity = {
            "backend": expected_candidate["backend"],
            "threads": expected_candidate["cpu_threads"],
        }
        for field, value in expected_identity.items():
            if candidate_identity.get(field) != value:
                raise ParameterScreenError(f"record {trial_id} candidate {field} differs")
        for field, value in (
            ("backend", expected_candidate["backend"]),
            ("cpu_threads", expected_candidate["cpu_threads"]),
            ("bit_length", expected_candidate["bit_length"]),
            ("shuffle", expected_candidate["shuffle"]),
        ):
            if record.get(field) != value:
                raise ParameterScreenError(f"record {trial_id} parameter {field} differs")

        solver = _mapping(logical.get("solver"), f"record {trial_id} solver identity")
        if solver.get("bit_length") != expected_candidate["bit_length"]:
            raise ParameterScreenError(f"record {trial_id} logical bit_length differs")
        if solver.get("shuffle") != int(expected_candidate["shuffle"]):
            raise ParameterScreenError(f"record {trial_id} logical shuffle differs")
        _validate_command_parameter(
            logical.get("command"), "--bit_length", str(expected_candidate["bit_length"]), trial_id
        )
        _validate_command_parameter(
            logical.get("command"), "--shuffle", str(int(expected_candidate["shuffle"])), trial_id
        )

        if record.get("upstream_url") != UPSTREAM_URL:
            raise ParameterScreenError(f"record {trial_id} upstream URL differs")
        if record.get("upstream_git_commit") != UPSTREAM_COMMIT:
            raise ParameterScreenError(f"record {trial_id} upstream commit differs")
        sweep_name = record.get("problem_family")
        if not isinstance(sweep_name, str) or not sweep_name:
            raise ParameterScreenError(f"record {trial_id} has invalid sweep name")
        sweep_names.add(sweep_name)

        phase = record.get("warmup_or_measured")
        repetition = record.get("repetition")
        if phase not in ("warmup", "measured") or isinstance(repetition, bool) or not isinstance(repetition, int):
            raise ParameterScreenError(f"record {trial_id} has invalid phase/repetition")
        geometry[(str(workload_name), str(candidate_name), str(phase))].append(repetition)

        _validate_scientific_gates(record, phase, trial_id)
        logical_protocol = _mapping(
            logical.get("protocol"), f"record {trial_id} logical protocol"
        )
        manifest_sha = logical_protocol.get("validation_manifest_sha256")
        if not _is_sha256(manifest_sha):
            raise ParameterScreenError(f"record {trial_id} lacks correctness-manifest SHA")
        validation = _mapping(
            record.get("validation_evidence"), f"record {trial_id} validation evidence"
        )
        if validation.get("sha256") != manifest_sha:
            raise ParameterScreenError(f"record {trial_id} validation SHA differs")
        validation_shas.add(str(manifest_sha))

        if phase == "measured":
            wall = _positive_float(record.get("wall_time_s"), f"record {trial_id} wall time")
            solver_time = _positive_float(
                record.get("solver_time_s"), f"record {trial_id} solver time"
            )
            measured.append(
                {
                    **{key: expected_workload[key] for key in ("family_id", "molecule", "basis", "problem_instance", "n_configurations")},
                    "candidate_name": expected_candidate["name"],
                    **{
                        key: expected_candidate[key]
                        for key in ("backend", "cpu_threads", "bit_length", "shuffle")
                    },
                    "input_sha256": input_sha,
                    "trial_id": trial_id,
                    "repetition": repetition,
                    "wall_time_s": wall,
                    "solver_time_s": solver_time,
                }
            )

    if len(sweep_names) != 1:
        raise ParameterScreenError("records do not share one timing sweep name")
    if len(validation_shas) != 1:
        raise ParameterScreenError("records do not share one correctness-manifest SHA")
    for workload in EXPECTED_WORKLOADS:
        for candidate in EXPECTED_CANDIDATES:
            for phase, expected_repetitions in (
                ("warmup", EXPECTED_WARMUP_REPETITIONS),
                ("measured", EXPECTED_MEASURED_REPETITIONS),
            ):
                actual = tuple(sorted(geometry.get((workload["problem_instance"], candidate["name"], phase), ())))
                if actual != expected_repetitions:
                    raise ParameterScreenError(
                        "incomplete repetition geometry for "
                        f"{workload['problem_instance']}/{candidate['name']}/{phase}: "
                        f"expected {expected_repetitions}, found {actual}"
                    )

    measured.sort(key=_measurement_sort_key)
    return measured, {
        "timing_sweep_name": next(iter(sweep_names)),
        "correctness_manifest_sha256": next(iter(validation_shas)),
        "official_upstream_url": UPSTREAM_URL,
        "official_upstream_commit": UPSTREAM_COMMIT,
    }


def _validate_scientific_gates(record: Mapping[str, Any], phase: str, trial_id: str) -> None:
    for field in ("process_success", "scientific_success", "correct"):
        if record.get(field) is not True:
            raise ParameterScreenError(f"record {trial_id} failed {field} gate")
    if record.get("status") != "success":
        raise ParameterScreenError(f"record {trial_id} is not successful")
    if record.get("project_git_dirty") is not False:
        raise ParameterScreenError(f"record {trial_id} used a dirty project")
    expected_eligible = phase == "measured"
    if record.get("timing_eligible") is not expected_eligible:
        raise ParameterScreenError(f"record {trial_id} timing eligibility differs")
    protocol = _mapping(record.get("protocol"), f"record {trial_id} protocol")
    if protocol.get("purpose") != "pilot":
        raise ParameterScreenError(f"record {trial_id} is not from the Phase C pilot")
    if protocol.get("warmups") != 1 or protocol.get("repetitions") != 1:
        raise ParameterScreenError(f"record {trial_id} protocol geometry differs")
    if protocol.get("correctness_validated") is not True:
        raise ParameterScreenError(f"record {trial_id} predates correctness validation")
    validation = _mapping(
        record.get("validation_evidence"), f"record {trial_id} validation evidence"
    )
    if validation.get("required") is not True or validation.get("valid") is not True:
        raise ParameterScreenError(f"record {trial_id} correctness evidence is invalid")
    if validation.get("errors") != []:
        raise ParameterScreenError(f"record {trial_id} correctness evidence has errors")


def _workload_results(measurements: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in measurements:
        grouped[str(row["problem_instance"])].append(row)
    results: list[dict[str, Any]] = []
    for workload in EXPECTED_WORKLOADS:
        members = sorted(
            grouped[workload["problem_instance"]], key=_measurement_sort_key
        )
        if len(members) != len(EXPECTED_CANDIDATES):
            raise ParameterScreenError(f"workload {workload['problem_instance']} lacks candidates")
        wall_minimum = min(float(row["wall_time_s"]) for row in members)
        solver_minimum = min(float(row["solver_time_s"]) for row in members)
        wall_winners = sorted(
            (str(row["candidate_name"]) for row in members if row["wall_time_s"] == wall_minimum),
            key=_candidate_name_sort_key,
        )
        solver_winners = sorted(
            (str(row["candidate_name"]) for row in members if row["solver_time_s"] == solver_minimum),
            key=_candidate_name_sort_key,
        )
        enriched: list[dict[str, Any]] = []
        for row in members:
            item = dict(row)
            item.update(
                {
                    "wall_rank": 1 + sum(other["wall_time_s"] < row["wall_time_s"] for other in members),
                    "solver_rank": 1 + sum(other["solver_time_s"] < row["solver_time_s"] for other in members),
                    "wall_regret_over_oracle": float(row["wall_time_s"]) / wall_minimum,
                    "solver_regret_over_oracle": float(row["solver_time_s"]) / solver_minimum,
                    "wall_oracle_winner": row["candidate_name"] in wall_winners,
                    "solver_oracle_winner": row["candidate_name"] in solver_winners,
                }
            )
            enriched.append(item)
        results.append(
            {
                **dict(workload),
                "wall_oracle_time_s": wall_minimum,
                "wall_oracle_candidates": wall_winners,
                "solver_oracle_time_s": solver_minimum,
                "solver_oracle_candidates": solver_winners,
                "candidates": enriched,
            }
        )
    return results


def _paired_effects(measurements: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    lookup = {
        (
            str(row["problem_instance"]),
            str(row["backend"]),
            int(row["bit_length"]),
            bool(row["shuffle"]),
        ): row
        for row in measurements
    }
    effects: list[dict[str, Any]] = []
    for workload in EXPECTED_WORKLOADS:
        name = workload["problem_instance"]
        for bit_length in (20, 48):
            for shuffle in (False, True):
                effects.append(
                    _effect_row(
                        workload,
                        "backend",
                        "cpu",
                        "gpu",
                        {"bit_length": bit_length, "shuffle": shuffle},
                        lookup[(name, "cpu", bit_length, shuffle)],
                        lookup[(name, "gpu", bit_length, shuffle)],
                    )
                )
        for backend in ("cpu", "gpu"):
            for shuffle in (False, True):
                effects.append(
                    _effect_row(
                        workload,
                        "bit_length",
                        20,
                        48,
                        {"backend": backend, "shuffle": shuffle},
                        lookup[(name, backend, 20, shuffle)],
                        lookup[(name, backend, 48, shuffle)],
                    )
                )
        for backend in ("cpu", "gpu"):
            for bit_length in (20, 48):
                effects.append(
                    _effect_row(
                        workload,
                        "shuffle",
                        False,
                        True,
                        {"backend": backend, "bit_length": bit_length},
                        lookup[(name, backend, bit_length, False)],
                        lookup[(name, backend, bit_length, True)],
                    )
                )
    effects.sort(key=_effect_sort_key)
    if len(effects) != len(EXPECTED_WORKLOADS) * 12:
        raise ParameterScreenError("paired-effect geometry differs from 108")
    return effects


def _effect_row(
    workload: Mapping[str, Any],
    factor: str,
    left_level: Any,
    right_level: Any,
    fixed_factors: Mapping[str, Any],
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **{key: workload[key] for key in ("family_id", "problem_instance", "n_configurations")},
        "factor": factor,
        "left_level": left_level,
        "right_level": right_level,
        "fixed_factors": dict(sorted(fixed_factors.items())),
        "left_candidate": left["candidate_name"],
        "right_candidate": right["candidate_name"],
        "wall_ratio_left_over_right": float(left["wall_time_s"]) / float(right["wall_time_s"]),
        "solver_ratio_left_over_right": float(left["solver_time_s"]) / float(right["solver_time_s"]),
        "wall_winner": _winner(left, right, "wall_time_s"),
        "solver_winner": _winner(left, right, "solver_time_s"),
    }


def _winner(left: Mapping[str, Any], right: Mapping[str, Any], metric: str) -> str:
    if left[metric] < right[metric]:
        return "left"
    if right[metric] < left[metric]:
        return "right"
    return "tie"


def _summaries(
    workload_results: Sequence[Mapping[str, Any]],
    paired_effects: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    enriched = [candidate for workload in workload_results for candidate in workload["candidates"]]
    candidate_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    family_candidate_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    size_candidate_groups: dict[tuple[int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in enriched:
        candidate_groups[str(row["candidate_name"])].append(row)
        family_candidate_groups[(str(row["family_id"]), str(row["candidate_name"]))].append(row)
        size_candidate_groups[
            (int(row["n_configurations"]), str(row["candidate_name"]))
        ].append(row)

    per_candidate = [
        _timing_summary("all", None, candidate, candidate_groups[candidate["name"]])
        for candidate in EXPECTED_CANDIDATES
    ]
    per_family_candidate = [
        _timing_summary(
            "family",
            family_id,
            candidate,
            family_candidate_groups[(family_id, candidate["name"])],
        )
        for family_id in ("fe4s4", "n2", "h2o")
        for candidate in EXPECTED_CANDIDATES
    ]
    per_size_candidate: list[dict[str, Any]] = []
    for n_configurations in sorted(
        {int(workload["n_configurations"]) for workload in EXPECTED_WORKLOADS}
    ):
        for candidate in EXPECTED_CANDIDATES:
            summary = _timing_summary(
                "size",
                None,
                candidate,
                size_candidate_groups[(n_configurations, candidate["name"])],
            )
            summary["n_configurations"] = n_configurations
            per_size_candidate.append(summary)

    factor_groups: dict[tuple[str | None, str], list[Mapping[str, Any]]] = defaultdict(list)
    for effect in paired_effects:
        factor_groups[(None, str(effect["factor"]))].append(effect)
        factor_groups[(str(effect["family_id"]), str(effect["factor"]))].append(effect)
    per_factor = [
        _factor_summary("all", None, factor, factor_groups[(None, factor)])
        for factor in ("backend", "bit_length", "shuffle")
    ]
    per_family_factor = [
        _factor_summary("family", family_id, factor, factor_groups[(family_id, factor)])
        for family_id in ("fe4s4", "n2", "h2o")
        for factor in ("backend", "bit_length", "shuffle")
    ]
    return {
        "per_candidate": per_candidate,
        "per_family_candidate": per_family_candidate,
        "per_size_candidate": per_size_candidate,
        "per_factor": per_factor,
        "per_family_factor": per_family_factor,
    }


def _timing_summary(
    scope: str,
    family_id: str | None,
    candidate: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "scope": scope,
        "family_id": family_id,
        **dict(candidate),
        "count": len(rows),
        "wall_time_s": summarize_values([float(row["wall_time_s"]) for row in rows]),
        "solver_time_s": summarize_values([float(row["solver_time_s"]) for row in rows]),
        "wall_oracle_win_count": sum(row["wall_oracle_winner"] is True for row in rows),
        "solver_oracle_win_count": sum(row["solver_oracle_winner"] is True for row in rows),
    }


def _factor_summary(
    scope: str,
    family_id: str | None,
    factor: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    wall_counts = Counter(str(row["wall_winner"]) for row in rows)
    solver_counts = Counter(str(row["solver_winner"]) for row in rows)
    return {
        "scope": scope,
        "family_id": family_id,
        "factor": factor,
        "left_level": rows[0]["left_level"],
        "right_level": rows[0]["right_level"],
        "count": len(rows),
        "wall_ratio_left_over_right": summarize_values(
            [float(row["wall_ratio_left_over_right"]) for row in rows]
        ),
        "solver_ratio_left_over_right": summarize_values(
            [float(row["solver_ratio_left_over_right"]) for row in rows]
        ),
        "wall_wins": {key: wall_counts[key] for key in ("left", "right", "tie")},
        "solver_wins": {key: solver_counts[key] for key in ("left", "right", "tie")},
    }


def _csv_rows(
    measurements: Sequence[Mapping[str, Any]],
    paired_effects: Sequence[Mapping[str, Any]],
    summaries: Mapping[str, Any],
) -> list[dict[str, Any]]:
    workload_results = _workload_results(measurements)
    enriched = [candidate for workload in workload_results for candidate in workload["candidates"]]
    rows: list[dict[str, Any]] = []
    for row in enriched:
        rows.append({"row_type": "measurement", "scope": "workload_candidate", **row})
    for row in paired_effects:
        rows.append({"row_type": "paired_effect", "scope": "workload", **row})
    for row in summaries["per_candidate"]:
        rows.append(
            {
                "row_type": "candidate_summary",
                "candidate_name": row["name"],
                "wall_time_summary": row["wall_time_s"],
                "solver_time_summary": row["solver_time_s"],
                **{key: value for key, value in row.items() if key not in ("name", "wall_time_s", "solver_time_s")},
            }
        )
    for row in summaries["per_family_candidate"]:
        rows.append(
            {
                "row_type": "family_candidate_summary",
                "candidate_name": row["name"],
                "wall_time_summary": row["wall_time_s"],
                "solver_time_summary": row["solver_time_s"],
                **{key: value for key, value in row.items() if key not in ("name", "wall_time_s", "solver_time_s")},
            }
        )
    for row in summaries["per_size_candidate"]:
        rows.append(
            {
                "row_type": "size_candidate_summary",
                "candidate_name": row["name"],
                "wall_time_summary": row["wall_time_s"],
                "solver_time_summary": row["solver_time_s"],
                **{
                    key: value
                    for key, value in row.items()
                    if key not in ("name", "wall_time_s", "solver_time_s")
                },
            }
        )
    for key, row_type in (("per_factor", "factor_summary"), ("per_family_factor", "family_factor_summary")):
        for row in summaries[key]:
            rows.append(
                {
                    "row_type": row_type,
                    "wall_ratio_summary": row["wall_ratio_left_over_right"],
                    "solver_ratio_summary": row["solver_ratio_left_over_right"],
                    "wall_left_wins": row["wall_wins"]["left"],
                    "wall_right_wins": row["wall_wins"]["right"],
                    "wall_ties": row["wall_wins"]["tie"],
                    "solver_left_wins": row["solver_wins"]["left"],
                    "solver_right_wins": row["solver_wins"]["right"],
                    "solver_ties": row["solver_wins"]["tie"],
                    **{
                        field: value
                        for field, value in row.items()
                        if field not in ("wall_ratio_left_over_right", "solver_ratio_left_over_right", "wall_wins", "solver_wins")
                    },
                }
            )
    return rows


def _validate_output(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise ParameterScreenError("parameter-screen output must be an object")
    if value.get("schema_version") != PARAMETER_SCREEN_SCHEMA_VERSION:
        raise ParameterScreenError("parameter-screen output schema differs")
    if value.get("analysis_type") != PARAMETER_SCREEN_ANALYSIS_TYPE:
        raise ParameterScreenError("parameter-screen output type differs")
    design = _mapping(value.get("design"), "parameter-screen design")
    if design.get("measurement_count") != 72 or design.get("paired_effect_count") != 108:
        raise ParameterScreenError("parameter-screen output geometry differs")
    measurements = value.get("measurements")
    paired_effects = value.get("paired_effects")
    if not isinstance(measurements, list) or len(measurements) != 72:
        raise ParameterScreenError("parameter-screen measurement rows differ")
    if not isinstance(paired_effects, list) or len(paired_effects) != 108:
        raise ParameterScreenError("parameter-screen output rows differ")
    boundary = _mapping(value.get("analysis_boundary"), "analysis boundary")
    expected_boundary = {
        "descriptive_observed_measurements_only": True,
        "missing_measurements_imputed": False,
        "configuration_pruning_performed": False,
        "model_fitting_performed": False,
        "statistical_significance_claimed": False,
    }
    if boundary != expected_boundary:
        raise ParameterScreenError("analysis boundary differs")
    try:
        expected_workloads = _workload_results(measurements)
        expected_effects = _paired_effects(measurements)
        expected_summaries = _summaries(expected_workloads, expected_effects)
        expected_csv_rows = _csv_rows(
            measurements, expected_effects, expected_summaries
        )
    except (AnalysisError, KeyError, TypeError, ValueError) as error:
        raise ParameterScreenError(
            f"cannot recompute parameter-screen output: {error}"
        ) from error
    for field, expected in (
        ("workload_results", expected_workloads),
        ("paired_effects", expected_effects),
        ("summaries", expected_summaries),
        ("csv_rows", expected_csv_rows),
    ):
        if canonical_json(value.get(field)) != canonical_json(expected):
            raise ParameterScreenError(
                f"parameter-screen {field} differs from deterministic recomputation"
            )
    csv_rows = value.get("csv_rows")
    if not isinstance(csv_rows, list) or len(csv_rows) != 272:
        raise ParameterScreenError("unified CSV row geometry differs")
    try:
        canonical_json(value)
    except (RecordError, TypeError, ValueError) as error:
        raise ParameterScreenError(f"parameter-screen output is not strict JSON: {error}") from error


def _validate_command_parameter(command: Any, flag: str, expected: str, trial_id: str) -> None:
    if not isinstance(command, list) or not all(isinstance(value, str) for value in command):
        raise ParameterScreenError(f"record {trial_id} command is invalid")
    positions = [index for index, value in enumerate(command) if value == flag]
    if len(positions) != 1 or positions[0] + 1 >= len(command) or command[positions[0] + 1] != expected:
        raise ParameterScreenError(f"record {trial_id} command {flag} differs")


def _measurement_sort_key(row: Mapping[str, Any]) -> tuple[int, int, int]:
    return (
        _WORKLOAD_ORDER[str(row["problem_instance"])],
        _CANDIDATE_ORDER[str(row["candidate_name"])],
        int(row["repetition"]),
    )


def _candidate_name_sort_key(name: str) -> int:
    return _CANDIDATE_ORDER[name]


def _effect_sort_key(row: Mapping[str, Any]) -> tuple[int, int, str]:
    return (
        _PAIR_FACTOR_ORDER[str(row["factor"])],
        _WORKLOAD_ORDER[str(row["problem_instance"])],
        canonical_json(row["fixed_factors"]),
    )


def _positive_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParameterScreenError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ParameterScreenError(f"{label} must be finite and positive")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ParameterScreenError(f"{label} must be an object")
    return value


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _load_strict_object(path: Path, label: str) -> dict[str, Any]:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ParameterScreenError(f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ParameterScreenError(f"{label} contains non-finite JSON value {value}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=invalid_constant,
        )
    except ParameterScreenError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ParameterScreenError(f"cannot load {label}: {error}") from error
    if not isinstance(value, dict):
        raise ParameterScreenError(f"{label} must be a JSON object")
    return value


def _file_claim(path: Path, root: Path, *, trial_id: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }
    if trial_id is not None:
        result["trial_id"] = trial_id
    return result


def _regular_file_inside(path: str | os.PathLike[str], root: Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    _reject_symlink_components(candidate, root, label)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ParameterScreenError(f"{label} must be a regular file inside repository") from error
    if not resolved.is_file() or resolved.is_symlink():
        raise ParameterScreenError(f"{label} must be a regular non-symlink file")
    return resolved


def _directory_inside(path: str | os.PathLike[str], root: Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    _reject_symlink_components(candidate, root, label)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ParameterScreenError(f"{label} must be inside repository") from error
    if not resolved.is_dir() or resolved.is_symlink():
        raise ParameterScreenError(f"{label} must be a non-symlink directory")
    return resolved


def _reject_symlink_components(path: Path, root: Path, label: str) -> None:
    try:
        relative = path.absolute().relative_to(root)
    except ValueError as error:
        raise ParameterScreenError(f"{label} must be inside repository") from error
    cursor = root
    for component in relative.parts:
        cursor = cursor / component
        if cursor.is_symlink():
            raise ParameterScreenError(f"{label} path must not use symlinks")


def _render_csv(rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(_CSV_FIELDS), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        extra = set(row).difference(_CSV_FIELDS)
        if extra:
            raise ParameterScreenError(f"CSV row has unsupported fields: {sorted(extra)}")
        writer.writerow(
            {
                field: json.dumps(row.get(field), sort_keys=True, allow_nan=False)
                if isinstance(row.get(field), (dict, list))
                else row.get(field)
                for field in _CSV_FIELDS
            }
        )
    return stream.getvalue().encode("utf-8")


def _atomic_write_changed(path: Path, payload: bytes) -> bool:
    if path.is_symlink():
        raise ParameterScreenError(f"output must not be a symlink: {path}")
    if path.exists():
        if not path.is_file() or path.is_symlink():
            raise ParameterScreenError(f"output is not a regular file: {path}")
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


__all__ = [
    "EXPECTED_CANDIDATES",
    "EXPECTED_MEASURED_REPETITIONS",
    "EXPECTED_WARMUP_REPETITIONS",
    "EXPECTED_WORKLOADS",
    "ParameterScreenError",
    "analyze_and_write_parameter_screen",
    "build_parameter_screen_analysis",
    "write_parameter_screen_outputs",
]
