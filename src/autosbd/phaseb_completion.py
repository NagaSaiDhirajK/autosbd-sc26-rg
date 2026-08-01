"""Fail-closed completion attestation for the Phase B final timing campaign."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any

from .analysis import AnalysisError, aggregate_records
from .config import ConfigError, SweepConfig, TrialTemplate, load_sweep_config
from .records import RecordError, canonical_json, load_record


COMPLETION_SCHEMA_VERSION = 1
COMPLETION_TYPE = "autosbd_phaseb_final_completion"
EXPECTED_EXPERIMENT_NAME = "phaseb-amd-n2-h2o-grid-final-v1"
EXPECTED_UPSTREAM_URL = "https://github.com/AMD-HPC/amd-sbd"
EXPECTED_UPSTREAM_COMMIT = "729cfa3a5011fb805eb9e686a7711f6919836dcb"
EXPECTED_PROTOCOL_PATH = "reports/phaseb_final_protocol.json"
EXPECTED_PROTOCOL_SHA256 = (
    "bf5b27d5213e02b08c5836e7a91da4702431d7c6ee9b01c58d76d660add73e98"
)
EXPECTED_AGGREGATE_PATH = "results/processed/phaseb_n2_h2o_grid_final.json"
EXPECTED_AGGREGATE_SHA256 = (
    "f7deacc86e923614fded5f8e6bdfa7206fe8339e3a4d035d6db7ee967212768d"
)
EXPECTED_CORRECTNESS_PATH = (
    "reports/phaseb_n2_h2o_grid_correctness_manifest.json"
)
EXPECTED_CORRECTNESS_SHA256 = (
    "ba6bf82b63c9a8bdf2a5a513df914a9f1446605a0d4939cb53f7921527222829"
)
EXPECTED_RAW_DIRECTORY = "results/raw"
EXPECTED_COUNTS = {"records": 104, "warmup": 20, "measured": 84}
EXPECTED_CONFIGS = (
    (
        "crossover",
        "configs/phaseb_n2_h2o_final_crossover.yaml",
        "f9aedb1eb33d419f7a7ff0103e284259926aa522e139845a11b3d4a68abcd990",
        48,
    ),
    (
        "broad",
        "configs/phaseb_n2_h2o_final_broad.yaml",
        "755ccfa48ae7830d494d6b0c0a3617df82eb5a86c79fae6a0deb00c0c6425398",
        32,
    ),
    (
        "headline",
        "configs/phaseb_n2_h2o_final_headline.yaml",
        "1807f183eab5d4732ae28ef8a7c3bf9becb17013870246e4d03eda9969519c2e",
        24,
    ),
)
EXPECTED_BINARIES = {
    "amd-cpu-16": (
        "build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu",
        "190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07",
        "cpu",
        16,
    ),
    "amd-l4-default": (
        "build/upstream/amd-729cfa3a-nvhpc-26.5/diag_gpu",
        "8f1481b6bcb4ddf3326453fd3a7c03dc36e29034629f46c5e982a4c17e43bc07",
        "gpu",
        1,
    ),
}


class PhaseBCompletionError(RuntimeError):
    """Raised when the Phase B evidence chain is incomplete or inconsistent."""


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as error:
        raise PhaseBCompletionError(f"cannot hash {path}: {error}") from error
    return digest.hexdigest()


def build_phaseb_final_completion(
    protocol_path: str | os.PathLike[str],
    aggregate_path: str | os.PathLike[str],
    raw_directory: str | os.PathLike[str],
    *,
    repository_root: str | os.PathLike[str],
) -> dict[str, Any]:
    """Validate the exact campaign and return its deterministic attestation."""

    root = Path(repository_root).resolve(strict=True)
    protocol_file = _exact_file(
        root,
        protocol_path,
        EXPECTED_PROTOCOL_PATH,
        EXPECTED_PROTOCOL_SHA256,
        "Phase B final protocol",
    )
    aggregate_file = _exact_file(
        root,
        aggregate_path,
        EXPECTED_AGGREGATE_PATH,
        EXPECTED_AGGREGATE_SHA256,
        "Phase B final aggregate",
    )
    raw_dir = _exact_directory(
        root, raw_directory, EXPECTED_RAW_DIRECTORY, "raw directory"
    )
    protocol = _load_json_object(protocol_file, "Phase B final protocol")
    aggregate = _load_json_object(aggregate_file, "Phase B final aggregate")
    _validate_protocol(protocol)
    _validate_aggregate_header(aggregate)

    correctness_file = _exact_file(
        root,
        EXPECTED_CORRECTNESS_PATH,
        EXPECTED_CORRECTNESS_PATH,
        EXPECTED_CORRECTNESS_SHA256,
        "Phase B correctness manifest",
    )
    configs, expected_templates, config_descriptions = _load_configs(root)
    binary_descriptions = _validate_binaries(root)

    input_ids = _digest_list(aggregate.get("input_record_ids"), "aggregate IDs")
    if len(input_ids) != EXPECTED_COUNTS["records"]:
        raise PhaseBCompletionError("aggregate must name exactly 104 raw records")
    raw_paths: list[Path] = []
    records: list[dict[str, Any]] = []
    raw_descriptions: dict[str, dict[str, Any]] = {}
    for trial_id in input_ids:
        path = raw_dir / f"{trial_id}.json"
        if path.is_symlink():
            raise PhaseBCompletionError(f"raw record must not be a symlink: {path}")
        path = _regular_file(path, f"raw record {trial_id}")
        if path.parent != raw_dir or path.stem != trial_id:
            raise PhaseBCompletionError(f"raw filename differs from trial ID {trial_id}")
        try:
            record = load_record(path)
        except (OSError, UnicodeError, json.JSONDecodeError, RecordError) as error:
            raise PhaseBCompletionError(
                f"invalid raw record {trial_id}: {error}"
            ) from error
        if record.get("trial_id") != trial_id:
            raise PhaseBCompletionError(f"raw record content differs from {trial_id}")
        raw_paths.append(path)
        records.append(record)
        raw_descriptions[trial_id] = _file_description(path, root)

    try:
        recomputed = aggregate_records(raw_paths)
    except AnalysisError as error:
        raise PhaseBCompletionError(f"cannot recompute final aggregate: {error}") from error
    if canonical_json(recomputed) != canonical_json(aggregate):
        raise PhaseBCompletionError(
            "aggregate differs from deterministic recomputation of its raw IDs"
        )

    owners = _validate_records(records, expected_templates)
    ordered = sorted(records, key=_record_sort_key)
    temporal = _temporal_summary(ordered)
    views = _analysis_views(ordered)
    record_traces = [
        _record_trace(record, raw_descriptions[record["trial_id"]], owners, views)
        for record in ordered
    ]
    phase_counts = Counter(record["warmup_or_measured"] for record in records)
    candidate_counts = Counter(_candidate_name(record) for record in records)
    family_counts = Counter(record["family_id"] for record in records)
    raw_inventory = [
        {"trial_id": trial_id, **raw_descriptions[trial_id]}
        for trial_id in sorted(raw_descriptions)
    ]
    raw_chain = hashlib.sha256(
        canonical_json(raw_inventory).encode("utf-8")
    ).hexdigest()
    project_commit = _single_text(records, "project_git_commit")
    harness_sha256 = _single_text(records, "harness_sha256")
    rate = float(protocol["projection"]["rate_usd_per_hour"])

    completion: dict[str, Any] = {
        "schema_version": COMPLETION_SCHEMA_VERSION,
        "attestation_type": COMPLETION_TYPE,
        "status": "complete",
        "experiment": {
            "name": EXPECTED_EXPERIMENT_NAME,
            "purpose": "final",
            "upstream_url": EXPECTED_UPSTREAM_URL,
            "upstream_git_commit": EXPECTED_UPSTREAM_COMMIT,
            "families": ["n2", "h2o"],
            "candidates": sorted(EXPECTED_BINARIES),
            "authorization": {
                "status": "explicit_user_approval_obtained_before_launch",
                "scope": "frozen 104-record Phase B final campaign",
            },
        },
        "source_artifacts": {
            "protocol": _file_description(protocol_file, root),
            "aggregate": _file_description(aggregate_file, root),
            "correctness_manifest": _file_description(correctness_file, root),
            "configs": config_descriptions,
            "candidate_artifacts": binary_descriptions,
            "raw_directory": EXPECTED_RAW_DIRECTORY,
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
            "by_candidate": dict(sorted(candidate_counts.items())),
            "by_family": dict(sorted(family_counts.items())),
            "by_shard": dict(sorted(Counter(owners.values()).items())),
        },
        "consistency": {
            "project_git_commit": project_commit,
            "project_git_dirty": False,
            "harness_sha256": harness_sha256,
            "official_upstream_only": True,
        },
        "temporal_integrity": temporal,
        "resources": _resource_summary(records),
        "cost": {
            "rate_usd_per_hour": rate,
            "rate_source": protocol["projection"]["rate_note"],
            "campaign_span_cost_usd": temporal["campaign_span_s"] * rate / 3600.0,
        },
        "analysis_views": views,
        "raw_evidence": {
            "records": len(raw_inventory),
            "total_size_bytes": sum(item["size_bytes"] for item in raw_inventory),
            "chain_definition": (
                "sha256(canonical JSON of trial-id-sorted "
                "[{trial_id,path,size_bytes,sha256}])"
            ),
            "chain_sha256": raw_chain,
        },
        "records": record_traces,
    }
    validate_phaseb_final_completion(completion)
    canonical_json(completion)
    return completion


def validate_phaseb_final_completion(completion: Mapping[str, Any]) -> None:
    """Validate the closed shape and internally linked completion summary."""

    if not isinstance(completion, Mapping):
        raise PhaseBCompletionError("completion must be an object")
    if completion.get("schema_version") != COMPLETION_SCHEMA_VERSION:
        raise PhaseBCompletionError("completion schema version differs")
    if completion.get("attestation_type") != COMPLETION_TYPE:
        raise PhaseBCompletionError("completion attestation type differs")
    if completion.get("status") != "complete":
        raise PhaseBCompletionError("completion status is not complete")
    counts = _mapping(completion.get("campaign_counts"), "campaign counts")
    for key, value in {
        "records": 104,
        "unique_trial_ids": 104,
        "unique_logical_trial_ids": 104,
        "warmup": 20,
        "measured": 84,
        "timing_eligible": 84,
        "success": 104,
        "correct": 104,
    }.items():
        if counts.get(key) != value:
            raise PhaseBCompletionError(f"completion count differs: {key}")
    views = _mapping(completion.get("analysis_views"), "analysis views")
    balanced = _mapping(views.get("balanced_broad"), "balanced view")
    balanced_ids = _digest_list(balanced.get("record_ids"), "balanced record IDs")
    if len(balanced_ids) != 60:
        raise PhaseBCompletionError("balanced view must contain exactly 60 IDs")
    traces = _object_list(completion.get("records"), "completion record traces")
    if len(traces) != 104:
        raise PhaseBCompletionError("completion must trace exactly 104 records")
    trace_ids = [_digest(item.get("trial_id"), "trace trial ID") for item in traces]
    if len(set(trace_ids)) != 104:
        raise PhaseBCompletionError("completion trace IDs are not unique")
    if not set(balanced_ids).issubset(trace_ids):
        raise PhaseBCompletionError("balanced view references unknown trace IDs")
    temporal = _mapping(completion.get("temporal_integrity"), "temporal integrity")
    if temporal.get("sequential_no_overlap") is not True:
        raise PhaseBCompletionError("completion does not attest sequential execution")
    canonical_json(completion)


def write_phaseb_final_completion(
    completion: Mapping[str, Any],
    output_path: str | os.PathLike[str],
    *,
    repository_root: str | os.PathLike[str],
) -> bool:
    """Atomically write deterministic bytes, refusing any raw-directory output."""

    validate_phaseb_final_completion(completion)
    root = Path(repository_root).resolve(strict=True)
    output = Path(output_path)
    if not output.is_absolute():
        output = root / output
    output = output.absolute()
    try:
        output.relative_to(root)
    except ValueError as error:
        raise PhaseBCompletionError("completion output must remain inside repository") from error
    raw_dir = (root / EXPECTED_RAW_DIRECTORY).resolve(strict=True)
    try:
        output.relative_to(raw_dir)
    except ValueError:
        pass
    else:
        raise PhaseBCompletionError("completion output is forbidden inside raw directory")
    if output.is_symlink():
        raise PhaseBCompletionError("completion output must not be a symlink")
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
    return _atomic_write_changed(output, payload)


def build_and_write_phaseb_final_completion(
    protocol_path: str | os.PathLike[str],
    aggregate_path: str | os.PathLike[str],
    raw_directory: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    repository_root: str | os.PathLike[str],
) -> dict[str, Any]:
    completion = build_phaseb_final_completion(
        protocol_path,
        aggregate_path,
        raw_directory,
        repository_root=repository_root,
    )
    changed = write_phaseb_final_completion(
        completion, output_path, repository_root=repository_root
    )
    return {
        "status": "complete",
        "changed": changed,
        "output": str(output_path),
        "records": completion["campaign_counts"]["records"],
        "balanced_records": len(
            completion["analysis_views"]["balanced_broad"]["record_ids"]
        ),
    }


def _validate_protocol(protocol: Mapping[str, Any]) -> None:
    if (
        protocol.get("schema_version") != 1
        or protocol.get("name") != EXPECTED_EXPERIMENT_NAME
        or protocol.get("status") != "frozen_before_measurement"
    ):
        raise PhaseBCompletionError("frozen protocol identity/status differs")
    expected = protocol.get("expected_campaign_records")
    if expected != {"measured": 84, "total": 104, "warmup": 20}:
        raise PhaseBCompletionError("frozen protocol campaign counts differ")
    scope = _mapping(protocol.get("scope"), "protocol scope")
    if (
        scope.get("upstream_url") != EXPECTED_UPSTREAM_URL
        or scope.get("upstream_git_commit") != EXPECTED_UPSTREAM_COMMIT
        or scope.get("official_primary_only") is not True
    ):
        raise PhaseBCompletionError("frozen protocol upstream scope differs")
    gate = _mapping(protocol.get("correctness_gate"), "correctness gate")
    if (
        gate.get("path") != EXPECTED_CORRECTNESS_PATH
        or gate.get("sha256") != EXPECTED_CORRECTNESS_SHA256
        or gate.get("validated_inputs") != 10
    ):
        raise PhaseBCompletionError("frozen correctness gate differs")
    shards = _object_list(protocol.get("shards"), "protocol shards")
    expected_shards = {
        path: (role, digest, total)
        for role, path, digest, total in EXPECTED_CONFIGS
    }
    if len(shards) != len(expected_shards):
        raise PhaseBCompletionError("frozen protocol shard count differs")
    for shard in shards:
        path = shard.get("path")
        if path not in expected_shards:
            raise PhaseBCompletionError(f"unexpected frozen shard {path!r}")
        role, digest, total = expected_shards[str(path)]
        if (
            shard.get("role") != role
            or shard.get("sha256") != digest
            or shard.get("expected_total_records") != total
        ):
            raise PhaseBCompletionError(f"frozen shard claim differs: {path}")


def _validate_aggregate_header(aggregate: Mapping[str, Any]) -> None:
    if (
        aggregate.get("schema_version") != 2
        or aggregate.get("analysis_type") != "autosbd_timing_aggregation"
        or aggregate.get("record_schema_version") != 3
    ):
        raise PhaseBCompletionError("final aggregate identity differs")
    if aggregate.get("record_counts") != {
        "input": 104,
        "included": 84,
        "excluded": 20,
    }:
        raise PhaseBCompletionError("final aggregate record counts differ")
    families = _object_list(aggregate.get("families"), "aggregate families")
    if {item.get("family_id") for item in families} != {"n2", "h2o"}:
        raise PhaseBCompletionError("final aggregate family set differs")
    if len(_object_list(aggregate.get("workloads"), "aggregate workloads")) != 10:
        raise PhaseBCompletionError("final aggregate must contain ten workloads")


def _load_configs(
    root: Path,
) -> tuple[
    dict[str, SweepConfig],
    dict[tuple[str, str, str, int], tuple[str, SweepConfig, TrialTemplate]],
    list[dict[str, Any]],
]:
    configs: dict[str, SweepConfig] = {}
    expected: dict[
        tuple[str, str, str, int], tuple[str, SweepConfig, TrialTemplate]
    ] = {}
    descriptions: list[dict[str, Any]] = []
    for role, relative, digest, total in EXPECTED_CONFIGS:
        path = _exact_file(root, relative, relative, digest, f"{role} config")
        try:
            config = load_sweep_config(path)
        except ConfigError as error:
            raise PhaseBCompletionError(f"invalid {role} config: {error}") from error
        if config.name != EXPECTED_EXPERIMENT_NAME:
            raise PhaseBCompletionError(f"{role} config sweep name differs")
        templates = config.trial_templates(randomize=False)
        if len(templates) != total:
            raise PhaseBCompletionError(f"{role} config trial count differs")
        configs[role] = config
        descriptions.append({"role": role, **_file_description(path, root)})
        for template in templates:
            key = template.semantic_key
            if key in expected:
                raise PhaseBCompletionError(f"duplicate trial template across shards: {key}")
            expected[key] = (role, config, template)
    if len(expected) != EXPECTED_COUNTS["records"]:
        raise PhaseBCompletionError("combined final configs do not define 104 trials")
    return configs, expected, descriptions


def _validate_binaries(root: Path) -> list[dict[str, Any]]:
    descriptions: list[dict[str, Any]] = []
    for name, (relative, digest, backend, threads) in sorted(EXPECTED_BINARIES.items()):
        path = _exact_file(root, relative, relative, digest, f"{name} executable")
        descriptions.append(
            {
                "candidate_name": name,
                "backend": backend,
                "cpu_threads": threads,
                **_file_description(path, root),
            }
        )
    return descriptions


def _validate_records(
    records: Sequence[Mapping[str, Any]],
    expected_templates: Mapping[
        tuple[str, str, str, int], tuple[str, SweepConfig, TrialTemplate]
    ],
) -> dict[str, str]:
    if len(records) != 104:
        raise PhaseBCompletionError("record collection must contain 104 records")
    seen_trials: set[str] = set()
    seen_logical: set[str] = set()
    seen_keys: set[tuple[str, str, str, int]] = set()
    owners: dict[str, str] = {}
    for record in records:
        trial_id = _digest(record.get("trial_id"), "trial ID")
        logical_id = _digest(record.get("logical_trial_id"), "logical trial ID")
        if trial_id in seen_trials or logical_id in seen_logical:
            raise PhaseBCompletionError("duplicate physical or logical trial identity")
        seen_trials.add(trial_id)
        seen_logical.add(logical_id)
        candidate_name = _candidate_name(record)
        key = (
            _text(record.get("problem_instance"), "problem_instance"),
            candidate_name,
            _text(record.get("warmup_or_measured"), "phase"),
            _nonnegative_int(record.get("repetition"), "repetition"),
        )
        match = expected_templates.get(key)
        if match is None or key in seen_keys:
            raise PhaseBCompletionError(f"missing/duplicate configured trial key: {key}")
        seen_keys.add(key)
        role, config, template = match
        owners[trial_id] = role
        candidate = _mapping(
            _mapping(record.get("logical_identity"), "logical identity").get(
                "candidate"
            ),
            "logical candidate",
        )
        expected_binary = EXPECTED_BINARIES[candidate_name]
        if (
            candidate.get("backend") != template.candidate.backend
            or candidate.get("threads") != template.candidate.threads
            or candidate.get("mpi_ranks") != template.candidate.mpi_ranks
            or candidate.get("artifact_sha256") != expected_binary[1]
            or record.get("backend") != template.candidate.backend
            or record.get("cpu_threads") != template.candidate.threads
            or record.get("mpi_ranks") != template.candidate.mpi_ranks
        ):
            raise PhaseBCompletionError(f"candidate identity differs for {trial_id}")
        workload = template.workload
        if (
            record.get("schema_version") != 3
            or record.get("problem_family") != EXPECTED_EXPERIMENT_NAME
            or record.get("family_id") != workload.family_id
            or record.get("molecule") != workload.molecule
            or record.get("basis") != workload.basis
        ):
            raise PhaseBCompletionError(f"family/workload identity differs for {trial_id}")
        protocol = _mapping(record.get("protocol"), "record protocol")
        if (
            protocol.get("purpose") != "final"
            or protocol.get("warmups") != config.protocol.warmups
            or protocol.get("repetitions") != config.protocol.repetitions
            or float(protocol.get("timeout_s", -1)) != config.protocol.timeout_s
            or protocol.get("correctness_validated") is not True
        ):
            raise PhaseBCompletionError(f"record protocol differs for {trial_id}")
        validation = _mapping(record.get("validation_evidence"), "validation evidence")
        if (
            validation.get("valid") is not True
            or validation.get("required") is not True
            or validation.get("errors") != []
            or validation.get("path") != EXPECTED_CORRECTNESS_PATH
            or validation.get("sha256") != EXPECTED_CORRECTNESS_SHA256
        ):
            raise PhaseBCompletionError(f"validation evidence differs for {trial_id}")
        artifact = _mapping(record.get("build_artifact"), "build artifact")
        if artifact.get("path") != expected_binary[0] or artifact.get("sha256") != expected_binary[1]:
            raise PhaseBCompletionError(f"build artifact differs for {trial_id}")
        phase = record["warmup_or_measured"]
        eligible = phase == "measured"
        if (
            record.get("attempt_index") != 0
            or record.get("project_git_dirty") is not False
            or record.get("upstream_url") != EXPECTED_UPSTREAM_URL
            or record.get("upstream_git_commit") != EXPECTED_UPSTREAM_COMMIT
            or record.get("status") != "success"
            or record.get("process_success") is not True
            or record.get("scientific_success") is not True
            or record.get("correct") is not True
            or record.get("timing_eligible") is not eligible
            or record.get("timeout") is not False
            or record.get("oom") is not False
            or record.get("exit_code") != 0
        ):
            raise PhaseBCompletionError(f"terminal/timing gates failed for {trial_id}")
        preflight = _mapping(record.get("preflight"), "preflight")
        if (
            preflight.get("gpu_idle") is not True
            or preflight.get("gpu_process_query_ok") is not True
            or preflight.get("gpu_compute_processes") != []
            or preflight.get("input_unchanged_before_launch") is not True
        ):
            raise PhaseBCompletionError(f"preflight gate failed for {trial_id}")
        monitoring = _mapping(record.get("resource_monitoring"), "monitoring")
        if monitoring.get("host_complete") is not True:
            raise PhaseBCompletionError(f"host monitoring incomplete for {trial_id}")
        if record["backend"] == "gpu" and (
            monitoring.get("gpu_complete") is not True
            or monitoring.get("gpu_process_observed") is not True
            or not isinstance(record.get("peak_gpu_memory_mb"), (int, float))
            or float(record["peak_gpu_memory_mb"]) <= 0
        ):
            raise PhaseBCompletionError(f"GPU monitoring incomplete for {trial_id}")
        integrity = _mapping(record.get("input_integrity"), "input integrity")
        if not (
            integrity.get("initial")
            == integrity.get("before_launch")
            == integrity.get("after_run")
        ):
            raise PhaseBCompletionError(f"input bytes changed for {trial_id}")
        estimates = _mapping(record.get("source_memory_estimate"), "memory estimate")
        if int(estimates.get("host_guard_bytes", -1)) > int(
            preflight.get("host_memory_cap_bytes", -1)
        ):
            raise PhaseBCompletionError(f"host guard exceeded cap for {trial_id}")
        if record["backend"] == "gpu" and (
            int(estimates.get("gpu_guard_bytes", -1))
            > int(preflight.get("gpu_memory_cap_bytes", -1))
            or int(estimates.get("gpu_host_guard_bytes", -1))
            > int(preflight.get("host_memory_cap_bytes", -1))
        ):
            raise PhaseBCompletionError(f"GPU guard exceeded cap for {trial_id}")
    if seen_keys != set(expected_templates):
        raise PhaseBCompletionError("raw records do not cover every configured trial")
    return owners


def _analysis_views(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    measured = [record for record in records if record["warmup_or_measured"] == "measured"]
    balanced = sorted(
        record["trial_id"] for record in measured if int(record["repetition"]) in (0, 1, 2)
    )
    crossover = sorted(
        record["trial_id"]
        for record in measured
        if record["problem_instance"].endswith(("-0055", "-0100"))
    )
    headline = sorted(
        record["trial_id"]
        for record in measured
        if record["problem_instance"] in {"n2-prefix-0239", "h2o-prefix-0275"}
    )
    extras = sorted(
        record["trial_id"] for record in measured if int(record["repetition"]) in (3, 4)
    )
    if (len(balanced), len(crossover), len(headline), len(extras)) != (60, 40, 20, 24):
        raise PhaseBCompletionError("derived Phase B analysis-view counts differ")
    return {
        "balanced_broad": {
            "description": "Measured repetitions 0, 1, and 2 for every workload/candidate.",
            "record_ids": balanced,
        },
        "crossover": {
            "description": "All measured repetitions at 55/100 half determinants.",
            "record_ids": crossover,
        },
        "headline": {
            "description": "All measured repetitions at both full-list inputs.",
            "record_ids": headline,
        },
        "extra_repetition_sensitivity": {
            "description": "Measured repetitions 3 and 4; excluded from balanced training.",
            "record_ids": extras,
        },
        "no_double_count": (
            "A raw trial ID may appear in multiple views but at most once in any "
            "one statistic, model input, policy row, table, or plotted value."
        ),
    }


def _temporal_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    intervals = [
        (
            _parse_timestamp(record["timestamp_utc"]),
            _parse_timestamp(record["finished_timestamp_utc"]),
            record["trial_id"],
        )
        for record in records
    ]
    for start, finish, trial_id in intervals:
        if finish < start:
            raise PhaseBCompletionError(f"negative trial interval: {trial_id}")
    overlaps: list[list[str]] = []
    for previous, current in zip(intervals, intervals[1:]):
        if current[0] < previous[1]:
            overlaps.append([previous[2], current[2]])
    if overlaps:
        raise PhaseBCompletionError(f"trial intervals overlap: {overlaps[0]}")
    first = intervals[0][0]
    last = intervals[-1][1]
    return {
        "first_start_utc": records[0]["timestamp_utc"],
        "last_finish_utc": records[-1]["finished_timestamp_utc"],
        "campaign_span_s": (last - first).total_seconds(),
        "process_wall_sum_s": sum(float(record["wall_time_s"]) for record in records),
        "sequential_no_overlap": True,
        "overlap_count": 0,
    }


def _resource_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    gpu_peaks = [
        float(record["peak_gpu_memory_mb"])
        for record in records
        if record.get("peak_gpu_memory_mb") is not None
    ]
    preflights = [_mapping(record["preflight"], "preflight") for record in records]
    gpu_states = [_mapping(item.get("gpu"), "preflight GPU") for item in preflights]
    estimates = [
        _mapping(record["source_memory_estimate"], "memory estimate")
        for record in records
    ]
    return {
        "peak_host_rss_mb": max(float(record["peak_host_rss_mb"]) for record in records),
        "peak_gpu_memory_mb": max(gpu_peaks),
        "minimum_preflight_free_gpu_memory_mib": min(
            int(item["memory_free_mib"]) for item in gpu_states
        ),
        "maximum_preflight_temperature_c": max(
            int(item["temperature_c"]) for item in gpu_states
        ),
        "maximum_gpu_guard_bytes": max(
            int(item["gpu_guard_bytes"]) for item in estimates
        ),
    }


def _record_trace(
    record: Mapping[str, Any],
    raw_description: Mapping[str, Any],
    owners: Mapping[str, str],
    views: Mapping[str, Any],
) -> dict[str, Any]:
    memberships = [
        name
        for name, view in views.items()
        if isinstance(view, Mapping) and record["trial_id"] in view.get("record_ids", [])
    ]
    return {
        "trial_id": record["trial_id"],
        "logical_trial_id": record["logical_trial_id"],
        "shard_role": owners[record["trial_id"]],
        "family_id": record["family_id"],
        "problem_instance": record["problem_instance"],
        "input_sha256": record["input_sha256"],
        "candidate_name": _candidate_name(record),
        "phase": record["warmup_or_measured"],
        "repetition": record["repetition"],
        "timing_eligible": record["timing_eligible"],
        "analysis_views": sorted(memberships),
        "raw_record": dict(raw_description),
    }


def _record_sort_key(record: Mapping[str, Any]) -> tuple[str, str]:
    return (str(record["timestamp_utc"]), str(record["trial_id"]))


def _candidate_name(record: Mapping[str, Any]) -> str:
    logical = _mapping(record.get("logical_identity"), "logical identity")
    candidate = _mapping(logical.get("candidate"), "logical candidate")
    name = _text(candidate.get("name"), "candidate name")
    if name not in EXPECTED_BINARIES:
        raise PhaseBCompletionError(f"unexpected candidate {name!r}")
    return name


def _single_text(records: Sequence[Mapping[str, Any]], field: str) -> str:
    values = {_text(record.get(field), field) for record in records}
    if len(values) != 1:
        raise PhaseBCompletionError(f"records do not share one {field}")
    return next(iter(values))


def _parse_timestamp(value: Any) -> datetime:
    text = _text(value, "timestamp")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise PhaseBCompletionError(f"invalid timestamp {text!r}") from error


def _exact_file(
    root: Path,
    supplied: str | os.PathLike[str],
    expected_relative: str,
    expected_sha256: str,
    label: str,
) -> Path:
    expected = (root / expected_relative).resolve(strict=True)
    path = Path(supplied)
    if not path.is_absolute():
        path = root / path
    if path.is_symlink():
        raise PhaseBCompletionError(f"{label} must not be a symlink")
    path = _regular_file(path.resolve(strict=True), label)
    if path != expected:
        raise PhaseBCompletionError(f"{label} path differs from {expected_relative}")
    if sha256_path(path) != expected_sha256:
        raise PhaseBCompletionError(f"{label} SHA-256 mismatch")
    return path


def _exact_directory(
    root: Path,
    supplied: str | os.PathLike[str],
    expected_relative: str,
    label: str,
) -> Path:
    expected = (root / expected_relative).resolve(strict=True)
    path = Path(supplied)
    if not path.is_absolute():
        path = root / path
    if path.is_symlink():
        raise PhaseBCompletionError(f"{label} must not be a symlink")
    path = path.resolve(strict=True)
    if path != expected or not path.is_dir():
        raise PhaseBCompletionError(f"{label} path differs from {expected_relative}")
    return path


def _regular_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise PhaseBCompletionError(f"{label} is not a regular file: {path}")
    return path


def _file_description(path: Path, root: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as error:
        raise PhaseBCompletionError(f"artifact is outside repository: {path}") from error
    return {
        "path": relative,
        "sha256": sha256_path(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PhaseBCompletionError(f"duplicate JSON key in {label}: {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PhaseBCompletionError(f"cannot load {label}: {error}") from error
    if not isinstance(value, dict):
        raise PhaseBCompletionError(f"{label} must be a JSON object")
    canonical_json(value)
    return value


def _atomic_write_changed(path: Path, payload: bytes) -> bool:
    try:
        if path.exists() and path.read_bytes() == payload:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
    except OSError as error:
        raise PhaseBCompletionError(f"cannot write completion {path}: {error}") from error
    return True


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PhaseBCompletionError(f"{label} must be an object")
    return value


def _object_list(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise PhaseBCompletionError(f"{label} must be a list of objects")
    return list(value)


def _digest_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise PhaseBCompletionError(f"{label} must be a list")
    values = [_digest(item, label) for item in value]
    if len(values) != len(set(values)):
        raise PhaseBCompletionError(f"{label} contains duplicates")
    return values


def _digest(value: Any, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise PhaseBCompletionError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PhaseBCompletionError(f"{label} must be a nonempty trimmed string")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PhaseBCompletionError(f"{label} must be a nonnegative integer")
    return value
