"""Fail-closed attestation for the frozen AutoSBD Stage 4 campaign.

The completion manifest is deliberately separate from the immutable measurement
protocol.  It consumes one explicit protocol, one explicit aggregate, and the
raw directory containing exactly named records from the aggregate.  It never
discovers records with a glob.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .analysis import AnalysisError, aggregate_records
from .config import ConfigError, SweepConfig, load_sweep_config
from .records import RecordError, canonical_json, validate_record


COMPLETION_SCHEMA_VERSION = 1
COMPLETION_TYPE = "autosbd_stage4_completion"
EXPECTED_EXPERIMENT_NAME = "stage4-amd-fe4s4-final-v1"
OFFICIAL_UPSTREAM_URL = "https://github.com/AMD-HPC/amd-sbd"
OFFICIAL_UPSTREAM_COMMIT = "729cfa3a5011fb805eb9e686a7711f6919836dcb"
EXPECTED_CANDIDATES = {
    "amd-cpu-16": ("cpu", 16, 1),
    "amd-l4-default": ("gpu", 1, 1),
}
EXPECTED_SHARD_ROLES = ("crossover", "mid", "large")
EXPECTED_COUNTS = {"warmup": 10, "measured": 38, "total": 48}
EXPECTED_VIEW_COUNTS = {
    "primary_final": 38,
    "balanced_broad_sensitivity": 30,
    "crossover": 20,
}
EXPECTED_CROSSOVER_WORKLOADS = frozenset(
    {"fe4s4-prefix-0032", "fe4s4-prefix-0055"}
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
NVHPC_COMPILER_PREFIX = "/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/compilers/bin/nvc++:"
NVHPC_COMPILER_MARKER = "nvc++ 26.5-0"
SOLVER_FIELDS = (
    "method",
    "iteration",
    "block",
    "tolerance",
    "max_time",
    "bit_length",
    "shuffle",
    "carryover_ratio",
    "rdm",
    "adet_comm_size",
    "bdet_comm_size",
    "task_comm_size",
)
WORKLOAD_FIELDS = (
    "n_orbitals",
    "n_spin_orbitals",
    "n_alpha_strings",
    "n_beta_strings",
    "n_configurations",
    "estimated_work",
    "estimated_cache_bytes",
)


class CompletionError(RuntimeError):
    """Raised when Stage 4 evidence cannot support a completion attestation."""


@dataclass(frozen=True)
class _ProtocolContext:
    repository_root: Path
    name: str
    protocol_description: dict[str, object]
    aggregate_description: dict[str, object]
    correctness_description: dict[str, object]
    pruning_description: dict[str, object]
    config_descriptions: tuple[dict[str, object], ...]
    candidate_artifacts: Mapping[str, dict[str, object]]
    validated_inputs: Mapping[str, Mapping[str, Any]]
    expected_trials: Mapping[tuple[str, str, str, int], Mapping[str, Any]]
    analysis_view_descriptions: Mapping[str, str]


def build_stage4_completion(
    protocol_path: str | os.PathLike[str],
    aggregate_path: str | os.PathLike[str],
    raw_dir: str | os.PathLike[str],
    *,
    repository_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Validate and describe one complete frozen Stage 4 campaign.

    Raw record paths are derived only from the aggregate's explicit
    ``input_record_ids``.  Additional files in ``raw_dir`` are ignored.
    """

    root = _repository_root(repository_root)
    protocol_file = _regular_file(Path(protocol_path), "protocol")
    aggregate_file = _regular_file(Path(aggregate_path), "aggregate")
    raw_directory = _directory(Path(raw_dir), "raw directory")

    protocol = _load_json_object(protocol_file, "protocol")
    aggregate = _load_json_object(aggregate_file, "aggregate")
    aggregate_description = _file_description(aggregate_file, root)
    _validate_aggregate_shape(aggregate)

    context = _validate_protocol(
        protocol,
        protocol_file,
        aggregate_description,
        root,
    )
    input_record_ids = tuple(aggregate["input_record_ids"])
    raw_paths: list[Path] = []
    records: list[Mapping[str, Any]] = []
    record_descriptions: dict[str, dict[str, object]] = {}
    for trial_id in input_record_ids:
        raw_path = raw_directory / f"{trial_id}.json"
        if raw_path.is_symlink():
            raise CompletionError(f"raw record must not be a symlink: {raw_path}")
        raw_path = _regular_file(raw_path, f"raw record {trial_id}")
        if raw_path.stem != trial_id or raw_path.parent.resolve() != raw_directory:
            raise CompletionError(f"raw filename does not match trial ID {trial_id}")
        record = _load_json_object(raw_path, f"raw record {trial_id}")
        try:
            validate_record(record)
        except RecordError as error:
            raise CompletionError(
                f"raw record {trial_id} is invalid: {error}"
            ) from error
        if record.get("trial_id") != trial_id:
            raise CompletionError(
                f"raw filename/trial ID mismatch for {raw_path.name}"
            )
        raw_paths.append(raw_path)
        records.append(record)
        record_descriptions[trial_id] = _file_description(raw_path, root)

    _validate_records(records, context)
    try:
        recomputed = aggregate_records(raw_paths)
    except AnalysisError as error:
        raise CompletionError(
            f"cannot recompute Stage 4 aggregate from explicit raw IDs: {error}"
        ) from error
    if canonical_json(recomputed) != canonical_json(aggregate):
        raise CompletionError(
            "aggregate does not exactly match deterministic recomputation from raw IDs"
        )

    ordered_records = sorted(records, key=_record_sort_key)
    views = _build_analysis_views(ordered_records, context.analysis_view_descriptions)
    trace = [
        _trace_record(record, record_descriptions[record["trial_id"]], views)
        for record in ordered_records
    ]
    project_commit = _single_value(records, "project_git_commit")
    harness_sha256 = _single_value(records, "harness_sha256")
    machine_fingerprint = _single_value(records, "machine_fingerprint")
    hostname = _single_value(records, "hostname")
    compiler_identity = _single_value(records, "compiler_identity")
    build_ids = {
        backend: sorted(
            {
                str(record["build_id"])
                for record in records
                if record["backend"] == backend
            }
        )
        for backend in ("cpu", "gpu")
    }
    for backend, values in build_ids.items():
        if len(values) != 1:
            raise CompletionError(
                f"records do not share one {backend} build_id: {values}"
            )

    phase_counts = Counter(str(record["warmup_or_measured"]) for record in records)
    backend_counts = Counter(str(record["backend"]) for record in records)
    workload_counts = Counter(str(record["problem_instance"]) for record in records)
    completion = {
        "schema_version": COMPLETION_SCHEMA_VERSION,
        "attestation_type": COMPLETION_TYPE,
        "status": "complete",
        "experiment": {
            "name": context.name,
            "purpose": "final",
            "problem_family": context.name,
            "upstream_url": OFFICIAL_UPSTREAM_URL,
            "upstream_git_commit": OFFICIAL_UPSTREAM_COMMIT,
            "compiler_identity": compiler_identity,
            "candidates": [
                {
                    "name": name,
                    "backend": values[0],
                    "cpu_threads": values[1],
                    "mpi_ranks": values[2],
                    "build_id": build_ids[values[0]][0],
                }
                for name, values in sorted(EXPECTED_CANDIDATES.items())
            ],
        },
        "source_artifacts": {
            "protocol": context.protocol_description,
            "aggregate": context.aggregate_description,
            "correctness_manifest": context.correctness_description,
            "candidate_pruning_evidence": context.pruning_description,
            "configs": list(context.config_descriptions),
            "candidate_artifacts": [
                {"backend": backend, **context.candidate_artifacts[backend]}
                for backend in sorted(context.candidate_artifacts)
            ],
        },
        "campaign_counts": {
            "records": len(records),
            "unique_trial_ids": len({record["trial_id"] for record in records}),
            "unique_logical_trial_ids": len(
                {record["logical_trial_id"] for record in records}
            ),
            "warmup": phase_counts["warmup"],
            "measured": phase_counts["measured"],
            "timing_eligible": sum(
                record["timing_eligible"] is True for record in records
            ),
            "success": sum(record["status"] == "success" for record in records),
            "correct": sum(record["correct"] is True for record in records),
            "by_backend": dict(sorted(backend_counts.items())),
            "by_workload": dict(sorted(workload_counts.items())),
        },
        "consistency": {
            "project_git_commit": project_commit,
            "project_git_dirty": False,
            "harness_sha256": harness_sha256,
            "machine_fingerprint": machine_fingerprint,
            "hostname": hostname,
        },
        "analysis_views": views,
        "records": trace,
    }
    canonical_json(completion)
    return completion


def write_completion_manifest(
    completion: Mapping[str, Any], output_path: str | os.PathLike[str]
) -> bool:
    """Atomically write deterministic JSON, replacing only changed bytes."""

    if not isinstance(completion, Mapping):
        raise CompletionError("completion manifest must be an object")
    if completion.get("schema_version") != COMPLETION_SCHEMA_VERSION:
        raise CompletionError("completion manifest has an invalid schema_version")
    if completion.get("attestation_type") != COMPLETION_TYPE:
        raise CompletionError("completion manifest has an invalid attestation_type")
    if completion.get("status") != "complete":
        raise CompletionError("completion manifest status must be complete")
    try:
        canonical_json(completion)
        payload = (
            json.dumps(
                completion,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CompletionError(f"completion manifest is not canonical JSON: {error}") from error
    return _atomic_write_changed(Path(output_path), payload)


def build_and_write_stage4_completion(
    protocol_path: str | os.PathLike[str],
    aggregate_path: str | os.PathLike[str],
    raw_dir: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    repository_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Build, write, and return a compact deterministic CLI status."""

    root = _repository_root(repository_root)
    protected = {
        _regular_file(Path(protocol_path), "protocol").resolve(),
        _regular_file(Path(aggregate_path), "aggregate").resolve(),
    }
    output = Path(output_path).resolve()
    if output in protected:
        raise CompletionError("completion output must differ from every input")
    completion = build_stage4_completion(
        protocol_path,
        aggregate_path,
        raw_dir,
        repository_root=root,
    )
    changed = write_completion_manifest(completion, output)
    description = _file_description(_regular_file(output, "completion output"), root)
    counts = completion["campaign_counts"]
    return {
        "changed": changed,
        "output": description,
        "records": counts["records"],
        "warmup": counts["warmup"],
        "measured": counts["measured"],
        "timing_eligible": counts["timing_eligible"],
        "status": completion["status"],
    }


def _validate_protocol(
    protocol: Mapping[str, Any],
    protocol_path: Path,
    aggregate_description: dict[str, object],
    root: Path,
) -> _ProtocolContext:
    if protocol.get("schema_version") != 1:
        raise CompletionError("protocol schema_version must be 1")
    if protocol.get("status") != "frozen_before_measurement":
        raise CompletionError("protocol must remain frozen_before_measurement")
    if protocol.get("name") != EXPECTED_EXPERIMENT_NAME:
        raise CompletionError("protocol experiment name is not the frozen Stage 4 name")
    scope = _mapping(protocol.get("scope"), "protocol scope")
    expected_scope = {
        "upstream_url": OFFICIAL_UPSTREAM_URL,
        "upstream_git_commit": OFFICIAL_UPSTREAM_COMMIT,
        "toolchain": "NVIDIA HPC SDK 26.5",
        "problem_family_count": 1,
        "distinct_chemical_families": False,
        "purpose": "final",
        "sequential_execution_required": True,
        "default_seeded_candidate_randomization_required": True,
    }
    for key, expected in expected_scope.items():
        if scope.get(key) != expected:
            raise CompletionError(
                f"protocol scope {key} differs: expected {expected!r}, "
                f"got {scope.get(key)!r}"
            )

    protocol_rules = _mapping(protocol.get("protocol"), "protocol rules")
    if protocol_rules.get("warmups_per_workload_candidate") != 1:
        raise CompletionError("protocol must use one warmup per workload/candidate")
    if protocol_rules.get("timeout_s") != 300:
        raise CompletionError("protocol timeout must be 300 seconds")
    if protocol_rules.get("seed") != 1729:
        raise CompletionError("protocol seed must be 1729")
    if protocol_rules.get("correctness_validated") is not True:
        raise CompletionError("protocol correctness gate is not enabled")
    if protocol_rules.get("primary_metric") != "end_to_end_wall_time_s":
        raise CompletionError("protocol primary metric is not end-to-end wall time")
    if protocol_rules.get("summary_statistics") != ["median", "q1", "q3", "iqr"]:
        raise CompletionError("protocol summary statistics differ from the frozen set")
    if protocol.get("expected_campaign_records") != EXPECTED_COUNTS:
        raise CompletionError("protocol campaign counts differ from 10/38/48")

    correctness_description = _verify_link(
        protocol.get("correctness_gate"), "correctness gate", root
    )
    correctness = _load_json_object(
        root / str(correctness_description["path"]), "correctness manifest"
    )
    candidate_artifacts, validated_inputs = _validate_correctness_manifest(
        correctness, correctness_description, root
    )
    pruning_description = _verify_link(
        protocol.get("candidate_pruning_evidence"),
        "candidate pruning evidence",
        root,
    )
    pruning = _mapping(
        protocol.get("candidate_pruning_evidence"),
        "candidate pruning evidence",
    )
    if set(pruning.get("retained_candidates", ())) != set(EXPECTED_CANDIDATES):
        raise CompletionError("protocol retained-candidate set differs")
    if set(pruning.get("pruned_candidates", ())) != {
        "amd-cpu-1",
        "amd-cpu-4",
        "amd-cpu-8",
    }:
        raise CompletionError("protocol pruned-candidate set differs")

    shards = protocol.get("shards")
    if not isinstance(shards, list) or len(shards) != 3:
        raise CompletionError("protocol must contain exactly three shards")
    if tuple(shard.get("role") for shard in shards if isinstance(shard, Mapping)) != EXPECTED_SHARD_ROLES:
        raise CompletionError("protocol shard roles/order differ from crossover/mid/large")

    expected_trials: dict[tuple[str, str, str, int], Mapping[str, Any]] = {}
    config_descriptions: list[dict[str, object]] = []
    all_workloads: set[str] = set()
    for shard in shards:
        shard = _mapping(shard, "protocol shard")
        role = _nonempty_string(shard.get("role"), "shard role")
        config_description = _verify_link(shard, f"{role} configuration", root)
        config_path = root / str(config_description["path"])
        try:
            config = load_sweep_config(config_path)
        except (ConfigError, OSError) as error:
            raise CompletionError(
                f"cannot load frozen {role} configuration: {error}"
            ) from error
        _validate_config(
            config,
            shard,
            correctness_description,
            candidate_artifacts,
            root,
        )
        shard_workloads = {workload.name for workload in config.workloads}
        if all_workloads.intersection(shard_workloads):
            raise CompletionError("workloads overlap across Stage 4 shards")
        all_workloads.update(shard_workloads)
        for template in config.trial_templates(randomize=True):
            key = template.semantic_key
            if key in expected_trials:
                raise CompletionError(f"duplicate semantic trial across shards: {key}")
            expected_trials[key] = {
                "config": config,
                "candidate": template.candidate,
                "workload": template.workload,
                "solver": template.solver,
                "role": role,
            }
        config_descriptions.append(
            {
                "role": role,
                **config_description,
                "workloads": sorted(shard_workloads),
                "expected_total_records": shard.get("expected_total_records"),
            }
        )

    if len(all_workloads) != 5 or set(validated_inputs) != all_workloads:
        raise CompletionError(
            "protocol/config/correctness workload sets do not match exactly"
        )
    phases = Counter(key[2] for key in expected_trials)
    if len(expected_trials) != 48 or phases != Counter(warmup=10, measured=38):
        raise CompletionError("expanded configurations do not contain exact 10/38/48 trials")

    analysis_views = _mapping(protocol.get("analysis_views"), "analysis views")
    required_views = {
        "primary_final",
        "balanced_broad_sensitivity",
        "crossover",
        "no_double_count",
    }
    if set(analysis_views) != required_views:
        raise CompletionError("protocol analysis-view definitions differ")
    view_descriptions = {
        name: _nonempty_string(analysis_views.get(name), f"analysis view {name}")
        for name in sorted(required_views)
    }
    claim_boundary = _mapping(protocol.get("claim_boundary"), "claim boundary")
    if claim_boundary.get("pilot_records_are_final_evidence") is not False:
        raise CompletionError("protocol must exclude pilot records from final evidence")
    if claim_boundary.get("profiled_records_are_timing_evidence") is not False:
        raise CompletionError("protocol must exclude profiled records from timing evidence")
    if claim_boundary.get("one_family_generalization_claim_allowed") is not False:
        raise CompletionError("protocol must forbid one-family generalization claims")

    return _ProtocolContext(
        repository_root=root,
        name=EXPECTED_EXPERIMENT_NAME,
        protocol_description=_file_description(protocol_path, root),
        aggregate_description=aggregate_description,
        correctness_description=correctness_description,
        pruning_description=pruning_description,
        config_descriptions=tuple(config_descriptions),
        candidate_artifacts=candidate_artifacts,
        validated_inputs=validated_inputs,
        expected_trials=expected_trials,
        analysis_view_descriptions=view_descriptions,
    )


def _validate_config(
    config: SweepConfig,
    shard: Mapping[str, Any],
    correctness_description: Mapping[str, object],
    candidate_artifacts: Mapping[str, Mapping[str, object]],
    root: Path,
) -> None:
    role = str(shard["role"])
    if config.name != EXPECTED_EXPERIMENT_NAME:
        raise CompletionError(f"{role} configuration experiment name differs")
    protocol = config.protocol
    if (
        protocol.purpose != "final"
        or not protocol.correctness_validated
        or protocol.warmups != 1
        or protocol.seed != 1729
        or protocol.timeout_s != 300
    ):
        raise CompletionError(f"{role} configuration protocol differs")
    if protocol.repetitions != shard.get("measured_repetitions"):
        raise CompletionError(f"{role} measured repetition count differs")
    if protocol.validation_manifest is None:
        raise CompletionError(f"{role} configuration lacks correctness manifest")
    if protocol.validation_manifest.resolve() != (
        root / str(correctness_description["path"])
    ).resolve():
        raise CompletionError(f"{role} correctness-manifest path differs")
    if _sha256_file(protocol.validation_manifest) != correctness_description["sha256"]:
        raise CompletionError(f"{role} correctness-manifest SHA-256 differs")

    candidates = {
        candidate.name: (candidate.backend, candidate.threads, candidate.mpi_ranks)
        for candidate in config.candidates
    }
    if candidates != EXPECTED_CANDIDATES:
        raise CompletionError(f"{role} candidate set differs from frozen candidates")
    for candidate in config.candidates:
        if candidate.executable is None:
            raise CompletionError(f"{role} candidate {candidate.name} has no executable")
        observed = _file_description(candidate.executable, root)
        expected = candidate_artifacts[candidate.backend]
        if _artifact_key(observed) != _artifact_key(expected):
            raise CompletionError(
                f"{role} {candidate.backend} executable differs from correctness artifact"
            )

    workloads = [workload.name for workload in config.workloads]
    if workloads != shard.get("workloads"):
        raise CompletionError(f"{role} workload order/set differs")
    templates = config.trial_templates(randomize=True)
    warmups = sum(template.phase == "warmup" for template in templates)
    measured = sum(template.phase == "measured" for template in templates)
    if warmups != shard.get("expected_warmup_records"):
        raise CompletionError(f"{role} warmup count differs")
    if measured != shard.get("expected_measured_records"):
        raise CompletionError(f"{role} measured count differs")
    if len(templates) != shard.get("expected_total_records"):
        raise CompletionError(f"{role} total trial count differs")


def _validate_correctness_manifest(
    manifest: Mapping[str, Any],
    description: Mapping[str, object],
    root: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, Mapping[str, Any]]]:
    if manifest.get("schema_version") != 2 or manifest.get("passed") is not True:
        raise CompletionError("correctness manifest is not a passing schema-v2 manifest")
    if manifest.get("upstream_url") != OFFICIAL_UPSTREAM_URL:
        raise CompletionError("correctness manifest upstream URL differs")
    if manifest.get("upstream_git_commit") != OFFICIAL_UPSTREAM_COMMIT:
        raise CompletionError("correctness manifest upstream commit differs")
    upstream = _mapping(manifest.get("upstream"), "correctness upstream")
    if upstream.get("url") != OFFICIAL_UPSTREAM_URL or upstream.get(
        "commit"
    ) != OFFICIAL_UPSTREAM_COMMIT:
        raise CompletionError("correctness nested upstream identity differs")
    scope = _mapping(manifest.get("scope"), "correctness scope")
    if scope.get("correctness_only") is not True or scope.get(
        "timing_evidence_used"
    ) is not False:
        raise CompletionError("correctness manifest scope differs")

    artifacts = manifest.get("candidate_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise CompletionError("correctness manifest must describe CPU and GPU artifacts")
    by_backend: dict[str, dict[str, object]] = {}
    for value in artifacts:
        value = _mapping(value, "correctness candidate artifact")
        backend = _nonempty_string(value.get("backend"), "artifact backend")
        if backend not in {"cpu", "gpu"} or backend in by_backend:
            raise CompletionError("correctness artifact backends must be unique CPU/GPU")
        # Records intentionally omit ``backend`` inside build_artifact.  Compare
        # only this normalized three-field description under the record backend.
        by_backend[backend] = _verify_claim(
            value, f"correctness {backend} artifact", root
        )
    if set(by_backend) != {"cpu", "gpu"}:
        raise CompletionError("correctness manifest artifact backends differ")

    inputs = manifest.get("validated_inputs")
    if not isinstance(inputs, list) or len(inputs) != 5:
        raise CompletionError("correctness manifest must contain five validated inputs")
    by_instance: dict[str, Mapping[str, Any]] = {}
    for value in inputs:
        value = _mapping(value, "validated input")
        instance = _nonempty_string(value.get("problem_instance"), "problem instance")
        input_sha256 = value.get("input_sha256")
        if not isinstance(input_sha256, str) or not SHA256_RE.fullmatch(input_sha256):
            raise CompletionError(f"validated input {instance} has invalid input SHA-256")
        if instance in by_instance:
            raise CompletionError(f"duplicate validated input {instance}")
        _mapping(value.get("workload"), f"validated input {instance} workload")
        _mapping(value.get("solver"), f"validated input {instance} solver")
        by_instance[instance] = value
    if description.get("sha256") != _sha256_file(
        root / str(description["path"])
    ):
        raise CompletionError("correctness manifest changed during validation")
    return by_backend, by_instance


def _validate_aggregate_shape(aggregate: Mapping[str, Any]) -> None:
    if aggregate.get("schema_version") != 1:
        raise CompletionError("aggregate schema_version must be 1")
    if aggregate.get("analysis_type") != "autosbd_timing_aggregation":
        raise CompletionError("aggregate analysis_type differs")
    if aggregate.get("record_counts") != {
        "input": 48,
        "included": 38,
        "excluded": 10,
    }:
        raise CompletionError("aggregate record counts differ from 48/38/10")
    ids = aggregate.get("input_record_ids")
    if not isinstance(ids, list) or len(ids) != 48:
        raise CompletionError("aggregate must contain exactly 48 input IDs")
    if not all(isinstance(value, str) and SHA256_RE.fullmatch(value) for value in ids):
        raise CompletionError("aggregate contains an invalid input record ID")
    if len(set(ids)) != 48:
        raise CompletionError("aggregate contains duplicate input record IDs")
    if ids != sorted(ids):
        raise CompletionError("aggregate input record IDs must be sorted")
    rows = aggregate.get("rows")
    if not isinstance(rows, list) or len(rows) != 48:
        raise CompletionError("aggregate must contain exactly 48 rows")
    row_ids = [row.get("trial_id") for row in rows if isinstance(row, Mapping)]
    if len(row_ids) != 48 or len(set(row_ids)) != 48 or set(row_ids) != set(ids):
        raise CompletionError("aggregate rows do not map one-to-one to input IDs")
    if sum(row.get("included") is True for row in rows) != 38:
        raise CompletionError("aggregate must include exactly 38 measured rows")


def _validate_records(
    records: Sequence[Mapping[str, Any]], context: _ProtocolContext
) -> None:
    if len(records) != 48:
        raise CompletionError("completion requires exactly 48 raw records")
    trial_ids = [record["trial_id"] for record in records]
    logical_ids = [record["logical_trial_id"] for record in records]
    if len(set(trial_ids)) != 48:
        raise CompletionError("raw records contain duplicate trial IDs")
    if len(set(logical_ids)) != 48:
        raise CompletionError("raw records contain duplicate logical trial IDs")

    observed_semantics: set[tuple[str, str, str, int]] = set()
    for record in records:
        trial_id = str(record["trial_id"])
        logical = _mapping(record.get("logical_identity"), f"record {trial_id} identity")
        candidate_identity = _mapping(
            logical.get("candidate"), f"record {trial_id} candidate identity"
        )
        candidate_name = _nonempty_string(
            candidate_identity.get("name"), f"record {trial_id} candidate name"
        )
        key = (
            str(record.get("problem_instance")),
            candidate_name,
            str(record.get("warmup_or_measured")),
            record.get("repetition"),
        )
        if key in observed_semantics:
            raise CompletionError(f"duplicate semantic Stage 4 record: {key}")
        expected = context.expected_trials.get(key)
        if expected is None:
            raise CompletionError(f"record {trial_id} is outside frozen Stage 4: {key}")
        observed_semantics.add(key)
        _validate_record_evidence(record, logical, candidate_identity, expected, context)
    if observed_semantics != set(context.expected_trials):
        missing = sorted(set(context.expected_trials).difference(observed_semantics))
        raise CompletionError(f"raw records omit frozen Stage 4 trials: {missing}")

    for field in (
        "project_git_commit",
        "harness_sha256",
        "machine_fingerprint",
        "hostname",
        "compiler_identity",
    ):
        _single_value(records, field)
    project_commit = _single_value(records, "project_git_commit")
    if not isinstance(project_commit, str) or not GIT_COMMIT_RE.fullmatch(project_commit):
        raise CompletionError("project commit is not a full lowercase Git SHA")
    for field in ("harness_sha256", "machine_fingerprint"):
        value = _single_value(records, field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            raise CompletionError(f"{field} is not a lowercase SHA-256")
    compiler = _single_value(records, "compiler_identity")
    if not isinstance(compiler, str) or not compiler.startswith(
        NVHPC_COMPILER_PREFIX
    ) or NVHPC_COMPILER_MARKER not in compiler:
        raise CompletionError("records do not use the exact NVIDIA HPC SDK 26.5 compiler")


def _validate_record_evidence(
    record: Mapping[str, Any],
    logical: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
    expected: Mapping[str, Any],
    context: _ProtocolContext,
) -> None:
    trial_id = str(record["trial_id"])
    phase = str(record["warmup_or_measured"])
    if record.get("schema_version") != 2 or record.get("attempt_index") != 0:
        raise CompletionError(f"record {trial_id} is not a schema-v2 attempt-0 record")
    required_outcome = {
        "status": "success",
        "exit_code": 0,
        "process_success": True,
        "scientific_success": True,
        "correct": True,
        "timeout": False,
        "oom": False,
        "failure_kind": None,
        "parse_error": None,
        "skip_reason": None,
    }
    for field, value in required_outcome.items():
        if record.get(field) != value:
            raise CompletionError(
                f"record {trial_id} outcome {field} differs from {value!r}"
            )
    for optional_failure in ("launch_error", "termination_signal"):
        if record.get(optional_failure) is not None:
            raise CompletionError(f"record {trial_id} has {optional_failure}")
    expected_eligible = phase == "measured"
    if record.get("timing_eligible") is not expected_eligible:
        raise CompletionError(
            f"record {trial_id} timing eligibility does not match phase {phase}"
        )
    if record.get("official_upstream_primary") is not True:
        raise CompletionError(f"record {trial_id} is not marked official upstream")
    if record.get("project_git_dirty") is not False:
        raise CompletionError(f"record {trial_id} project tree was dirty")
    if record.get("upstream_url") != OFFICIAL_UPSTREAM_URL:
        raise CompletionError(f"record {trial_id} upstream URL differs")
    if record.get("upstream_git_commit") != OFFICIAL_UPSTREAM_COMMIT:
        raise CompletionError(f"record {trial_id} upstream commit differs")
    if record.get("problem_family") != context.name:
        raise CompletionError(f"record {trial_id} problem family differs")

    config = expected["config"]
    candidate = expected["candidate"]
    workload = expected["workload"]
    solver = expected["solver"]
    if record.get("problem_instance") != workload.name:
        raise CompletionError(f"record {trial_id} workload differs")
    if record.get("backend") != candidate.backend:
        raise CompletionError(f"record {trial_id} backend differs")
    if record.get("cpu_threads") != candidate.threads:
        raise CompletionError(f"record {trial_id} thread count differs")
    if record.get("mpi_ranks") != candidate.mpi_ranks:
        raise CompletionError(f"record {trial_id} MPI rank count differs")
    if record.get("seed") != config.protocol.seed:
        raise CompletionError(f"record {trial_id} seed differs")

    validated = context.validated_inputs[workload.name]
    if record.get("input_sha256") != validated.get("input_sha256"):
        raise CompletionError(f"record {trial_id} input SHA differs from correctness gate")
    expected_workload = _mapping(
        validated.get("workload"), f"validated workload {workload.name}"
    )
    for field in WORKLOAD_FIELDS:
        if record.get(field) != expected_workload.get(field):
            raise CompletionError(f"record {trial_id} workload field {field} differs")
    if record.get("reference_value") != validated.get("reference_value"):
        raise CompletionError(f"record {trial_id} reference value differs")

    expected_solver = {field: getattr(solver, field) for field in SOLVER_FIELDS}
    if logical.get("solver") != expected_solver:
        raise CompletionError(f"record {trial_id} solver identity differs")
    if logical.get("schema_version") != 2:
        raise CompletionError(f"record {trial_id} logical schema differs")
    if logical.get("sweep_name") != context.name or logical.get(
        "workload"
    ) != workload.name:
        raise CompletionError(f"record {trial_id} logical experiment identity differs")
    for logical_field, record_field in (
        ("input_sha256", "input_sha256"),
        ("phase", "warmup_or_measured"),
        ("repetition", "repetition"),
        ("project_commit", "project_git_commit"),
        ("project_dirty", "project_git_dirty"),
        ("harness_sha256", "harness_sha256"),
        ("upstream_commit", "upstream_git_commit"),
        ("machine_fingerprint", "machine_fingerprint"),
        ("reference_value", "reference_value"),
    ):
        if logical.get(logical_field) != record.get(record_field):
            raise CompletionError(
                f"record {trial_id} logical {logical_field} disagrees with record"
            )
    if logical.get("command") != record.get("command"):
        raise CompletionError(f"record {trial_id} logical command differs")
    if logical.get("environment_overrides") != record.get("environment_overrides"):
        raise CompletionError(f"record {trial_id} logical environment differs")

    expected_logical_protocol = {
        "purpose": "final",
        "warmups": 1,
        "repetitions": config.protocol.repetitions,
        "seed": 1729,
        "timeout_s": 300.0,
        "correctness_validated": True,
        "validation_manifest_sha256": context.correctness_description["sha256"],
    }
    if logical.get("protocol") != expected_logical_protocol:
        raise CompletionError(f"record {trial_id} logical protocol differs")
    expected_record_protocol = {
        "purpose": "final",
        "warmups": 1,
        "repetitions": config.protocol.repetitions,
        "timeout_s": 300.0,
        "correctness_validated": True,
    }
    if record.get("protocol") != expected_record_protocol:
        raise CompletionError(f"record {trial_id} protocol differs")

    expected_candidate = {
        "name": candidate.name,
        "backend": candidate.backend,
        "threads": candidate.threads,
        "mpi_ranks": candidate.mpi_ranks,
        "compiler_flags": list(candidate.compiler_flags),
    }
    for field, value in expected_candidate.items():
        if candidate_identity.get(field) != value:
            raise CompletionError(f"record {trial_id} candidate {field} differs")
    if candidate_identity.get("build_id") != record.get("build_id"):
        raise CompletionError(f"record {trial_id} build ID differs")
    if candidate_identity.get("compiler_identity") != record.get("compiler_identity"):
        raise CompletionError(f"record {trial_id} compiler identity differs")
    compiler_identity = record.get("compiler_identity")
    if not isinstance(compiler_identity, str) or not compiler_identity.startswith(
        NVHPC_COMPILER_PREFIX
    ) or NVHPC_COMPILER_MARKER not in compiler_identity:
        raise CompletionError(f"record {trial_id} is not an NVHPC 26.5 build")
    compiler_and_flags = record.get("compiler_and_flags")
    if not isinstance(compiler_and_flags, str) or not compiler_and_flags.startswith(
        compiler_identity + ";"
    ):
        raise CompletionError(f"record {trial_id} compiler/flags description differs")

    backend = candidate.backend
    build_claim = _claim_description(
        record.get("build_artifact"),
        f"record {trial_id} build artifact",
        context.repository_root,
    )
    expected_artifact = context.candidate_artifacts[backend]
    if _artifact_key(build_claim) != _artifact_key(expected_artifact):
        raise CompletionError(
            f"record {trial_id} {backend} build artifact differs from correctness manifest"
        )
    if candidate_identity.get("artifact_sha256") != expected_artifact["sha256"]:
        raise CompletionError(f"record {trial_id} logical artifact SHA differs")

    evidence = _mapping(
        record.get("validation_evidence"), f"record {trial_id} validation evidence"
    )
    expected_evidence = {
        "required": True,
        "valid": True,
        "path": context.correctness_description["path"],
        "sha256": context.correctness_description["sha256"],
        "size_bytes": context.correctness_description["size_bytes"],
        "errors": [],
    }
    if evidence != expected_evidence:
        raise CompletionError(f"record {trial_id} correctness evidence differs")
    integrity = _mapping(record.get("input_integrity"), f"record {trial_id} integrity")
    if integrity.get("unchanged_before_launch") is not True or integrity.get(
        "unchanged_after_run"
    ) is not True or integrity.get("rehash_error") is not None:
        raise CompletionError(f"record {trial_id} input integrity failed")
    monitoring = _mapping(
        record.get("resource_monitoring"), f"record {trial_id} monitoring"
    )
    if monitoring.get("host_complete") is not True:
        raise CompletionError(f"record {trial_id} host monitoring is incomplete")
    if backend == "gpu" and (
        monitoring.get("gpu_complete") is not True
        or monitoring.get("gpu_process_observed") is not True
    ):
        raise CompletionError(f"record {trial_id} GPU monitoring is incomplete")


def _build_analysis_views(
    records: Sequence[Mapping[str, Any]], descriptions: Mapping[str, str]
) -> dict[str, Any]:
    primary = [record for record in records if record["warmup_or_measured"] == "measured"]
    balanced = [record for record in primary if int(record["repetition"]) <= 2]
    crossover = [
        record
        for record in primary
        if record["problem_instance"] in EXPECTED_CROSSOVER_WORKLOADS
    ]
    selected = {
        "primary_final": primary,
        "balanced_broad_sensitivity": balanced,
        "crossover": crossover,
    }
    result: dict[str, Any] = {}
    for name, view_records in selected.items():
        ids = [record["trial_id"] for record in view_records]
        if len(ids) != EXPECTED_VIEW_COUNTS[name] or len(ids) != len(set(ids)):
            raise CompletionError(f"analysis view {name} has an invalid record set")
        result[name] = {
            "description": descriptions[name],
            "record_count": len(ids),
            "record_ids": ids,
        }
    result["no_double_count"] = {
        "description": descriptions["no_double_count"],
        "validated_within_each_view": True,
    }
    return result


def _trace_record(
    record: Mapping[str, Any],
    description: Mapping[str, object],
    views: Mapping[str, Any],
) -> dict[str, Any]:
    trial_id = record["trial_id"]
    memberships = [
        name
        for name in ("primary_final", "balanced_broad_sensitivity", "crossover")
        if trial_id in views[name]["record_ids"]
    ]
    candidate = _mapping(record["logical_identity"], "logical identity")["candidate"]
    return {
        "trial_id": trial_id,
        "logical_trial_id": record["logical_trial_id"],
        "attempt_index": record["attempt_index"],
        "raw_record": dict(description),
        "problem_instance": record["problem_instance"],
        "input_sha256": record["input_sha256"],
        "candidate": {
            "name": candidate["name"],
            "backend": record["backend"],
            "cpu_threads": record["cpu_threads"],
        },
        "phase": record["warmup_or_measured"],
        "repetition": record["repetition"],
        "status": record["status"],
        "correct": record["correct"],
        "timing_eligible": record["timing_eligible"],
        "wall_time_s": record["wall_time_s"],
        "peak_host_rss_mb": record["peak_host_rss_mb"],
        "peak_gpu_memory_mb": record["peak_gpu_memory_mb"],
        "build_artifact": {
            key: record["build_artifact"][key]
            for key in ("path", "sha256", "size_bytes")
        },
        "analysis_views": memberships,
    }


def _record_sort_key(record: Mapping[str, Any]) -> tuple[object, ...]:
    candidate = _mapping(record["logical_identity"], "logical identity")["candidate"]
    phase_order = 0 if record["warmup_or_measured"] == "warmup" else 1
    return (
        record["problem_instance"],
        candidate["name"],
        phase_order,
        record["repetition"],
        record["trial_id"],
    )


def _verify_link(value: object, label: str, root: Path) -> dict[str, object]:
    claim = _mapping(value, label)
    expected_sha256 = claim.get("sha256")
    if not isinstance(expected_sha256, str) or not SHA256_RE.fullmatch(expected_sha256):
        raise CompletionError(f"{label} has an invalid SHA-256")
    path = _resolve_repo_file(claim.get("path"), label, root)
    description = _file_description(path, root)
    if description["sha256"] != expected_sha256:
        raise CompletionError(f"{label} SHA-256 mismatch")
    return description


def _verify_claim(value: object, label: str, root: Path) -> dict[str, object]:
    claim = _claim_description(value, label, root)
    path = root / str(claim["path"])
    actual = _file_description(path, root)
    if _artifact_key(claim) != _artifact_key(actual):
        raise CompletionError(f"{label} path/SHA-256/size mismatch")
    return actual


def _claim_description(value: object, label: str, root: Path) -> dict[str, object]:
    claim = _mapping(value, label)
    path = _resolve_repo_file(claim.get("path"), label, root)
    sha256 = claim.get("sha256")
    size = claim.get("size_bytes")
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        raise CompletionError(f"{label} has an invalid SHA-256")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise CompletionError(f"{label} has an invalid size_bytes")
    return {"path": _display_path(path, root), "sha256": sha256, "size_bytes": size}


def _artifact_key(value: Mapping[str, object]) -> tuple[object, object, object]:
    return value["path"], value["sha256"], value["size_bytes"]


def _repository_root(value: str | os.PathLike[str] | None) -> Path:
    root = Path(value) if value is not None else Path(__file__).resolve().parents[2]
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise CompletionError(f"cannot resolve repository root {root}: {error}") from error
    if not resolved.is_dir():
        raise CompletionError(f"repository root is not a directory: {resolved}")
    return resolved


def _resolve_repo_file(value: object, label: str, root: Path) -> Path:
    if not isinstance(value, str) or not value:
        raise CompletionError(f"{label} path must be a nonempty string")
    path = Path(value)
    if path.is_absolute():
        raise CompletionError(f"{label} path must be repository-relative")
    try:
        resolved = (root / path).resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise CompletionError(f"cannot resolve {label} inside repository: {error}") from error
    if not resolved.is_file():
        raise CompletionError(f"{label} is not a regular file: {resolved}")
    return resolved


def _regular_file(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise CompletionError(f"cannot resolve {label} {path}: {error}") from error
    if not resolved.is_file():
        raise CompletionError(f"{label} is not a regular file: {resolved}")
    return resolved


def _directory(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise CompletionError(f"cannot resolve {label} {path}: {error}") from error
    if not resolved.is_dir():
        raise CompletionError(f"{label} is not a directory: {resolved}")
    return resolved


def _file_description(path: Path, root: Path) -> dict[str, object]:
    path = _regular_file(path, "evidence file")
    return {
        "path": _display_path(path, root),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _display_path(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return str(resolved)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise CompletionError(f"cannot hash evidence file {path}: {error}") from error
    return digest.hexdigest()


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
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
            object_pairs_hook=unique_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise CompletionError(f"cannot load {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise CompletionError(f"{label} must be a JSON object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CompletionError(f"{label} must be an object")
    return value


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CompletionError(f"{label} must be a nonempty string")
    return value


def _single_value(records: Sequence[Mapping[str, Any]], field: str) -> object:
    values = {canonical_json(record.get(field)) for record in records}
    if len(values) != 1:
        raise CompletionError(f"records disagree on {field}")
    return records[0].get(field)


def _atomic_write_changed(path: Path, payload: bytes) -> bool:
    parent = path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise CompletionError(f"output must not be a symlink: {path}")
        if path.exists():
            if not path.is_file() or path.is_symlink():
                raise CompletionError(f"output is not a regular file: {path}")
            if path.read_bytes() == payload:
                return False
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o644)
            os.replace(temporary, path)
            directory_fd = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary.exists():
                temporary.unlink()
    except CompletionError:
        raise
    except OSError as error:
        raise CompletionError(f"cannot atomically write {path}: {error}") from error
    return True
