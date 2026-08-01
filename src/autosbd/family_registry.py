"""Strict external family metadata for immutable Stage 4 Fe4S4 evidence.

The frozen Stage 4 raw records predate explicit chemistry-family fields.  This
module verifies their existing evidence chain and builds a separate registry;
it never rewrites or supplements a raw record in place.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from .records import RecordError, canonical_json, validate_record


REGISTRY_SCHEMA_VERSION = 1
REGISTRY_TYPE = "autosbd_external_family_registry"
EXPECTED_COMPLETION_PATH = "reports/stage4_completion.json"
EXPECTED_COMPLETION_SHA256 = (
    "7fefb110d29b0bfae2ece24a3506bd6fa53e6e81257f57779ce2067e9910ee36"
)
EXPECTED_COMPLETION_SIZE_BYTES = 72_167
EXPECTED_AGGREGATE_PATH = "results/processed/stage4_final.json"
EXPECTED_AGGREGATE_SHA256 = (
    "58c6b6bc2454de9237a102a3d3d6b3628d0bb98b0f0758cf0353d9edc64885aa"
)
EXPECTED_AGGREGATE_SIZE_BYTES = 265_132
EXPECTED_RAW_DIRECTORY = "results/raw"
EXPECTED_UPSTREAM_URL = "https://github.com/AMD-HPC/amd-sbd"
EXPECTED_UPSTREAM_COMMIT = "729cfa3a5011fb805eb9e686a7711f6919836dcb"
EXPECTED_FCIDUMP_PATH = (
    "external/amd-sbd/samples/selected_basis_diagonalization/"
    "fcidump_Fe4S4.txt"
)
FAMILY_ID = "fe4s4"
MOLECULE = "Fe4S4"
BASIS_STATUS = "upstream_not_reported"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_INSTANCE_RE = re.compile(r"fe4s4-prefix-[0-9]{4}")
_WORKLOAD_ENTRY_KEYS = frozenset(
    {
        "entry_id",
        "family_id",
        "molecule",
        "basis",
        "basis_status",
        "problem_instance",
        "input_sha256",
        "n_alpha_strings",
        "n_beta_strings",
        "n_configurations",
        "components",
        "source_record_count",
        "source_record_ids",
    }
)
_RECORD_MAPPING_KEYS = frozenset(
    {
        "entry_id",
        "trial_id",
        "logical_trial_id",
        "problem_instance",
        "input_sha256",
        "raw_record",
    }
)


class FamilyRegistryError(ValueError):
    """Raised when the registry or its immutable sources fail validation."""


def sha256_path(path: Path) -> str:
    """Hash one regular file without changing it."""

    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
    except OSError as error:
        raise FamilyRegistryError(f"cannot hash evidence file {path}: {error}") from error
    return digest.hexdigest()


def build_fe4s4_family_registry(
    completion_path: Path,
    aggregate_path: Path,
    raw_directory: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Verify frozen Stage 4 evidence and derive its external family registry."""

    root = _root(repository_root)
    completion_file = _exact_file(
        root, completion_path, EXPECTED_COMPLETION_PATH, "Stage 4 completion"
    )
    aggregate_file = _exact_file(
        root, aggregate_path, EXPECTED_AGGREGATE_PATH, "Stage 4 aggregate"
    )
    raw_dir = _exact_directory(
        root, raw_directory, EXPECTED_RAW_DIRECTORY, "Stage 4 raw directory"
    )
    completion_description = _fixed_description(
        completion_file,
        root,
        expected_sha256=EXPECTED_COMPLETION_SHA256,
        expected_size=EXPECTED_COMPLETION_SIZE_BYTES,
        label="Stage 4 completion",
    )
    aggregate_description = _fixed_description(
        aggregate_file,
        root,
        expected_sha256=EXPECTED_AGGREGATE_SHA256,
        expected_size=EXPECTED_AGGREGATE_SIZE_BYTES,
        label="Stage 4 aggregate",
    )
    completion = _load_strict_object(completion_file, "Stage 4 completion")
    aggregate = _load_strict_object(aggregate_file, "Stage 4 aggregate")
    _validate_completion_header(completion, aggregate_description)
    _validate_aggregate_header(aggregate)

    completion_records = _object_list(completion.get("records"), "completion records")
    aggregate_rows = _object_list(aggregate.get("rows"), "aggregate rows")
    completion_by_id = _unique_by_digest(
        completion_records, "trial_id", "completion records"
    )
    aggregate_by_id = _unique_by_digest(aggregate_rows, "trial_id", "aggregate rows")
    input_ids = _digest_list(aggregate.get("input_record_ids"), "aggregate input IDs")
    if set(completion_by_id) != set(aggregate_by_id) or set(input_ids) != set(
        completion_by_id
    ):
        raise FamilyRegistryError(
            "completion records, aggregate rows, and aggregate input IDs disagree"
        )

    raw_by_id: dict[str, dict[str, Any]] = {}
    raw_descriptions: dict[str, dict[str, Any]] = {}
    component_files: dict[str, dict[str, Any]] = {}
    semantics_by_id: dict[str, dict[str, Any]] = {}
    for trial_id in sorted(completion_by_id):
        trace = completion_by_id[trial_id]
        raw_claim = _mapping(trace.get("raw_record"), f"raw claim {trial_id}")
        expected_raw_path = f"{EXPECTED_RAW_DIRECTORY}/{trial_id}.json"
        if raw_claim.get("path") != expected_raw_path:
            raise FamilyRegistryError(f"raw path disagrees with trial ID {trial_id}")
        raw_path = _resolve_claimed_file(root, raw_claim, f"raw record {trial_id}")
        if raw_path.parent != raw_dir:
            raise FamilyRegistryError(f"raw record is outside the exact raw directory: {trial_id}")
        raw = _load_strict_object(raw_path, f"raw record {trial_id}")
        try:
            validate_record(raw)
        except RecordError as error:
            raise FamilyRegistryError(f"invalid raw record {trial_id}: {error}") from error
        if raw.get("schema_version") != 2:
            raise FamilyRegistryError(f"raw record is not immutable schema-v2: {trial_id}")
        _crosscheck_trace_raw(trace, raw, trial_id)
        semantics = _raw_semantics(raw, trial_id)
        _crosscheck_aggregate_row(aggregate_by_id[trial_id], trace, raw, semantics)
        for component in semantics["components"].values():
            path = str(component["path"])
            previous = component_files.setdefault(path, dict(component))
            if previous != component:
                raise FamilyRegistryError(
                    f"component claim differs across raw records: {path}"
                )
        raw_by_id[trial_id] = raw
        raw_descriptions[trial_id] = dict(raw_claim)
        semantics_by_id[trial_id] = semantics

    for component in component_files.values():
        _resolve_claimed_file(root, component, f"input component {component['path']}")

    workloads = _derive_workloads(aggregate, semantics_by_id)
    record_mappings: list[dict[str, Any]] = []
    entry_id_by_key = {
        (entry["problem_instance"], entry["input_sha256"]): entry["entry_id"]
        for entry in workloads
    }
    for trial_id in sorted(raw_by_id):
        semantics = semantics_by_id[trial_id]
        key = (semantics["problem_instance"], semantics["input_sha256"])
        entry_id = entry_id_by_key.get(key)
        if entry_id is None:
            raise FamilyRegistryError(f"raw record has no workload mapping: {trial_id}")
        record_mappings.append(
            {
                "entry_id": entry_id,
                "trial_id": trial_id,
                "logical_trial_id": raw_by_id[trial_id]["logical_trial_id"],
                "problem_instance": key[0],
                "input_sha256": key[1],
                "raw_record": raw_descriptions[trial_id],
            }
        )

    registry: dict[str, Any] = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "registry_type": REGISTRY_TYPE,
        "status": "complete",
        "augmentation_contract": _augmentation_contract(),
        "sources": {
            "stage4_completion": completion_description,
            "stage4_aggregate": aggregate_description,
            "raw_directory": EXPECTED_RAW_DIRECTORY,
        },
        "family": _family_metadata(),
        "record_counts": {
            "workload_entries": len(workloads),
            "raw_records": len(record_mappings),
        },
        "workloads": workloads,
        "records": record_mappings,
    }
    registry["registry_id"] = _registry_id(registry)
    validate_family_registry(registry)
    return registry


def resolve_family_entry(
    registry: Mapping[str, Any],
    *,
    problem_instance: str,
    input_sha256: str,
    fcidump_sha256: str,
    alpha_determinant_sha256: str,
    beta_determinant_sha256: str,
    n_configurations: int,
) -> dict[str, Any]:
    """Resolve one exact mapping and reject unknown, ambiguous, or stale inputs."""

    validate_family_registry(registry)
    entries = _object_list(registry.get("workloads"), "registry workloads")
    instance_matches = [
        entry for entry in entries if entry.get("problem_instance") == problem_instance
    ]
    matches = [
        entry
        for entry in instance_matches
        if entry.get("input_sha256") == input_sha256
    ]
    if not matches:
        if instance_matches:
            raise FamilyRegistryError(
                f"instance/hash disagreement for {problem_instance!r}"
            )
        hash_matches = [entry for entry in entries if entry.get("input_sha256") == input_sha256]
        if hash_matches:
            raise FamilyRegistryError(
                f"instance/hash disagreement for input {input_sha256}"
            )
        raise FamilyRegistryError(
            f"unknown family mapping: {(problem_instance, input_sha256)!r}"
        )
    if len(matches) != 1:
        raise FamilyRegistryError(
            f"ambiguous family mapping: {(problem_instance, input_sha256)!r}"
        )
    entry = matches[0]
    expected = {
        "fcidump_sha256": fcidump_sha256,
        "alpha_determinant_sha256": alpha_determinant_sha256,
        "beta_determinant_sha256": beta_determinant_sha256,
        "n_configurations": n_configurations,
    }
    components = _mapping(entry.get("components"), "workload components")
    observed = {
        "fcidump_sha256": _mapping(components.get("fcidump"), "FCIDUMP").get(
            "sha256"
        ),
        "alpha_determinant_sha256": _mapping(
            components.get("alpha_determinants"), "alpha determinants"
        ).get("sha256"),
        "beta_determinant_sha256": _mapping(
            components.get("beta_determinants"), "beta determinants"
        ).get("sha256"),
        "n_configurations": entry.get("n_configurations"),
    }
    for field, value in expected.items():
        if observed[field] != value:
            raise FamilyRegistryError(f"component-hash disagreement: {field}")
    return dict(entry)


def validate_family_registry(registry: Mapping[str, Any]) -> None:
    """Validate registry structure, unique mapping keys, IDs, and record links."""

    if not isinstance(registry, Mapping):
        raise FamilyRegistryError("family registry must be an object")
    required = {
        "schema_version",
        "registry_type",
        "status",
        "registry_id",
        "augmentation_contract",
        "sources",
        "family",
        "record_counts",
        "workloads",
        "records",
    }
    if set(registry) != required:
        raise FamilyRegistryError("family registry top-level fields differ from contract")
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise FamilyRegistryError("family registry schema version differs")
    if registry.get("registry_type") != REGISTRY_TYPE or registry.get("status") != "complete":
        raise FamilyRegistryError("family registry identity/status differs")
    if registry.get("registry_id") != _registry_id(registry):
        raise FamilyRegistryError("family registry ID mismatch")
    if registry.get("augmentation_contract") != _augmentation_contract():
        raise FamilyRegistryError("family registry augmentation contract differs")
    sources = _mapping(registry.get("sources"), "registry sources")
    expected_sources = {
        "stage4_completion": {
            "path": EXPECTED_COMPLETION_PATH,
            "sha256": EXPECTED_COMPLETION_SHA256,
            "size_bytes": EXPECTED_COMPLETION_SIZE_BYTES,
        },
        "stage4_aggregate": {
            "path": EXPECTED_AGGREGATE_PATH,
            "sha256": EXPECTED_AGGREGATE_SHA256,
            "size_bytes": EXPECTED_AGGREGATE_SIZE_BYTES,
        },
        "raw_directory": EXPECTED_RAW_DIRECTORY,
    }
    if dict(sources) != expected_sources:
        raise FamilyRegistryError("family registry source path/SHA/size differs")
    family = _mapping(registry.get("family"), "family metadata")
    if family != _family_metadata():
        raise FamilyRegistryError("family metadata differs from registered Fe4S4 metadata")

    entries = _object_list(registry.get("workloads"), "registry workloads")
    entry_by_id: dict[str, Mapping[str, Any]] = {}
    seen_keys: set[tuple[str, str]] = set()
    for entry in entries:
        if set(entry) != _WORKLOAD_ENTRY_KEYS:
            raise FamilyRegistryError(
                "workload entry fields differ from exact registry contract"
            )
        entry_id = _digest(entry.get("entry_id"), "entry ID")
        key = (
            _text(entry.get("problem_instance"), "problem_instance"),
            _digest(entry.get("input_sha256"), "input_sha256"),
        )
        if key in seen_keys:
            raise FamilyRegistryError(f"ambiguous duplicate workload mapping: {key!r}")
        if entry_id in entry_by_id:
            raise FamilyRegistryError(f"duplicate entry ID: {entry_id}")
        seen_keys.add(key)
        entry_by_id[entry_id] = entry
        if entry.get("family_id") != FAMILY_ID or entry.get("molecule") != MOLECULE:
            raise FamilyRegistryError(f"workload family metadata differs: {key!r}")
        if entry.get("basis") is not None or entry.get("basis_status") != BASIS_STATUS:
            raise FamilyRegistryError(f"workload basis metadata differs: {key!r}")
        if entry_id != _entry_id(entry):
            raise FamilyRegistryError(f"workload entry ID mismatch: {key!r}")
        _positive_int(entry.get("n_configurations"), "n_configurations")
        _positive_int(entry.get("n_alpha_strings"), "n_alpha_strings")
        _positive_int(entry.get("n_beta_strings"), "n_beta_strings")
        components = _mapping(entry.get("components"), "components")
        if set(components) != {
            "fcidump",
            "alpha_determinants",
            "beta_determinants",
        }:
            raise FamilyRegistryError("workload component roles differ")
        for name, component in components.items():
            _validate_file_claim(_mapping(component, name), name)
        source_ids = _digest_list(entry.get("source_record_ids"), "source record IDs")
        if entry.get("source_record_count") != len(source_ids):
            raise FamilyRegistryError("workload source-record count differs")
    if len(entries) != 5:
        raise FamilyRegistryError("Fe4S4 registry must contain exactly five workloads")

    records = _object_list(registry.get("records"), "registry records")
    seen_trials: set[str] = set()
    linked: dict[str, set[str]] = defaultdict(set)
    for record in records:
        if set(record) != _RECORD_MAPPING_KEYS:
            raise FamilyRegistryError(
                "record mapping fields differ from exact registry contract"
            )
        trial_id = _digest(record.get("trial_id"), "record trial ID")
        if trial_id in seen_trials:
            raise FamilyRegistryError(f"duplicate registry record mapping: {trial_id}")
        seen_trials.add(trial_id)
        _digest(record.get("logical_trial_id"), "record logical trial ID")
        entry_id = _digest(record.get("entry_id"), "record entry ID")
        entry = entry_by_id.get(entry_id)
        if entry is None:
            raise FamilyRegistryError(f"record references unknown entry ID: {entry_id}")
        if (
            record.get("problem_instance") != entry.get("problem_instance")
            or record.get("input_sha256") != entry.get("input_sha256")
        ):
            raise FamilyRegistryError(f"record/entry mapping disagreement: {trial_id}")
        raw_claim = _mapping(record.get("raw_record"), "record raw claim")
        _validate_file_claim(raw_claim, "record raw claim")
        if raw_claim.get("path") != f"{EXPECTED_RAW_DIRECTORY}/{trial_id}.json":
            raise FamilyRegistryError(f"record raw path disagrees: {trial_id}")
        linked[entry_id].add(trial_id)
    for entry_id, entry in entry_by_id.items():
        if linked[entry_id] != set(entry["source_record_ids"]):
            raise FamilyRegistryError(f"workload/record links disagree: {entry_id}")
    counts = _mapping(registry.get("record_counts"), "record counts")
    if counts != {"workload_entries": len(entries), "raw_records": len(records)}:
        raise FamilyRegistryError("registry record counts differ")
    _strict_bytes(registry)


def write_family_registry(
    registry: Mapping[str, Any],
    output_path: Path,
    *,
    check: bool = False,
    forbidden_directory: Path | None = None,
) -> bool:
    """Atomically write changed output, or verify exact bytes in check mode."""

    validate_family_registry(registry)
    output = Path(output_path)
    if forbidden_directory is not None:
        forbidden = Path(forbidden_directory).resolve()
        try:
            output.resolve().relative_to(forbidden)
        except ValueError:
            pass
        else:
            raise FamilyRegistryError("registry output must not be inside results/raw")
    if output.is_symlink():
        raise FamilyRegistryError(f"registry output must not be a symlink: {output}")
    payload = _strict_bytes(registry)
    if check:
        if not output.is_file() or output.is_symlink() or output.read_bytes() != payload:
            raise FamilyRegistryError("family registry check failed")
        return False
    if output.exists():
        if not output.is_file():
            raise FamilyRegistryError(f"registry output is not a file: {output}")
        if output.read_bytes() == payload:
            return False
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
        directory_descriptor = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True


def _validate_completion_header(
    completion: Mapping[str, Any], aggregate_description: Mapping[str, Any]
) -> None:
    if (
        completion.get("schema_version") != 1
        or completion.get("attestation_type") != "autosbd_stage4_completion"
        or completion.get("status") != "complete"
    ):
        raise FamilyRegistryError("Stage 4 completion identity/status differs")
    counts = _mapping(completion.get("campaign_counts"), "completion campaign counts")
    for key, expected in {
        "records": 48,
        "unique_trial_ids": 48,
        "unique_logical_trial_ids": 48,
        "warmup": 10,
        "measured": 38,
        "timing_eligible": 38,
    }.items():
        if counts.get(key) != expected:
            raise FamilyRegistryError(f"completion campaign count differs: {key}")
    source = _mapping(completion.get("source_artifacts"), "completion sources")
    claimed_aggregate = _mapping(source.get("aggregate"), "completion aggregate claim")
    if dict(claimed_aggregate) != dict(aggregate_description):
        raise FamilyRegistryError("completion aggregate path/SHA/size disagreement")


def _validate_aggregate_header(aggregate: Mapping[str, Any]) -> None:
    if (
        aggregate.get("schema_version") != 1
        or aggregate.get("analysis_type") != "autosbd_timing_aggregation"
    ):
        raise FamilyRegistryError("Stage 4 aggregate identity differs")
    if aggregate.get("record_counts") != {"input": 48, "included": 38, "excluded": 10}:
        raise FamilyRegistryError("Stage 4 aggregate counts differ")
    workloads = aggregate.get("workloads")
    if not isinstance(workloads, list) or len(workloads) != 5:
        raise FamilyRegistryError("Stage 4 aggregate must contain five workloads")


def _crosscheck_trace_raw(
    trace: Mapping[str, Any], raw: Mapping[str, Any], trial_id: str
) -> None:
    fields = (
        "trial_id",
        "logical_trial_id",
        "problem_instance",
        "input_sha256",
        "attempt_index",
        "repetition",
        "status",
        "correct",
        "timing_eligible",
    )
    for field in fields:
        if trace.get(field) != raw.get(field):
            raise FamilyRegistryError(f"completion/raw {field} disagreement: {trial_id}")
    phase = trace.get("phase")
    if phase != raw.get("warmup_or_measured"):
        raise FamilyRegistryError(f"completion/raw phase disagreement: {trial_id}")


def _raw_semantics(raw: Mapping[str, Any], trial_id: str) -> dict[str, Any]:
    instance = _text(raw.get("problem_instance"), f"problem_instance {trial_id}")
    if _INSTANCE_RE.fullmatch(instance) is None:
        raise FamilyRegistryError(f"unexpected Fe4S4 instance namespace: {instance}")
    input_sha = _digest(raw.get("input_sha256"), f"input_sha256 {trial_id}")
    logical = _mapping(raw.get("logical_identity"), f"logical identity {trial_id}")
    if (
        logical.get("workload") != instance
        or logical.get("input_sha256") != input_sha
        or logical.get("sweep_name") != raw.get("problem_family")
    ):
        raise FamilyRegistryError(f"raw/logical workload identity disagreement: {trial_id}")
    if (
        raw.get("upstream_url") != EXPECTED_UPSTREAM_URL
        or raw.get("upstream_git_commit") != EXPECTED_UPSTREAM_COMMIT
        or logical.get("upstream_commit") != EXPECTED_UPSTREAM_COMMIT
    ):
        raise FamilyRegistryError(f"raw upstream identity differs: {trial_id}")

    features = _mapping(raw.get("input_features"), f"input features {trial_id}")
    if features.get("combined_input_sha256") != input_sha:
        raise FamilyRegistryError(f"combined input hash disagreement: {trial_id}")
    alpha = _mapping(features.get("alpha"), f"alpha features {trial_id}")
    beta = _mapping(features.get("beta"), f"beta features {trial_id}")
    fcidump = _mapping(features.get("fcidump"), f"FCIDUMP features {trial_id}")
    n_alpha = _positive_int(alpha.get("count"), f"alpha count {trial_id}")
    n_beta = _positive_int(beta.get("count"), f"beta count {trial_id}")
    n_configurations = _positive_int(
        features.get("n_configurations"), f"n_configurations {trial_id}"
    )
    if n_configurations != n_alpha * n_beta:
        raise FamilyRegistryError(f"configuration product disagreement: {trial_id}")
    for field, expected in (
        ("n_alpha_strings", n_alpha),
        ("n_beta_strings", n_beta),
        ("n_configurations", n_configurations),
    ):
        if raw.get(field) != expected:
            raise FamilyRegistryError(f"raw/feature {field} disagreement: {trial_id}")
    if features.get("beta_reuses_alpha") is not True:
        raise FamilyRegistryError(f"Fe4S4 beta-reuse evidence differs: {trial_id}")

    claims = _object_list(raw.get("input_files"), f"input files {trial_id}")
    by_role: dict[str, Mapping[str, Any]] = {}
    for claim in claims:
        role = _text(claim.get("role"), f"input role {trial_id}")
        if role in by_role:
            raise FamilyRegistryError(f"duplicate input role {role}: {trial_id}")
        by_role[role] = claim
    if set(by_role) != {"alpha", "beta", "fcidump"}:
        raise FamilyRegistryError(f"input roles differ: {trial_id}")
    components: dict[str, dict[str, Any]] = {}
    feature_by_role = {"alpha": alpha, "beta": beta, "fcidump": fcidump}
    output_names = {
        "alpha": "alpha_determinants",
        "beta": "beta_determinants",
        "fcidump": "fcidump",
    }
    for role, claim in by_role.items():
        if set(claim) != {"path", "sha256", "size_bytes", "role"}:
            raise FamilyRegistryError(
                f"{role} input claim fields differ from role-tagged contract"
            )
        _validate_file_claim(
            {key: claim[key] for key in ("path", "sha256", "size_bytes")},
            f"{role} input claim",
        )
        feature = feature_by_role[role]
        if (
            claim.get("sha256") != feature.get("sha256")
            or claim.get("size_bytes") != feature.get("file_bytes")
        ):
            raise FamilyRegistryError(f"component-hash disagreement: {trial_id}/{role}")
        components[output_names[role]] = {
            "path": claim["path"],
            "sha256": claim["sha256"],
            "size_bytes": claim["size_bytes"],
        }
    if components["fcidump"]["path"] != EXPECTED_FCIDUMP_PATH:
        raise FamilyRegistryError(f"unexpected Fe4S4 FCIDUMP path: {trial_id}")
    if components["alpha_determinants"] != components["beta_determinants"]:
        raise FamilyRegistryError(f"alpha/beta reuse claim differs: {trial_id}")
    integrity = _mapping(raw.get("input_integrity"), f"input integrity {trial_id}")
    if (
        integrity.get("unchanged_before_launch") is not True
        or integrity.get("unchanged_after_run") is not True
        or integrity.get("rehash_error") is not None
    ):
        raise FamilyRegistryError(f"input integrity failed: {trial_id}")
    canonical_claims = canonical_json(claims)
    for stage in ("initial", "before_launch", "after_run"):
        if canonical_json(integrity.get(stage)) != canonical_claims:
            raise FamilyRegistryError(f"input integrity snapshot differs: {trial_id}/{stage}")
    return {
        "problem_instance": instance,
        "input_sha256": input_sha,
        "n_alpha_strings": n_alpha,
        "n_beta_strings": n_beta,
        "n_configurations": n_configurations,
        "components": components,
    }


def _crosscheck_aggregate_row(
    row: Mapping[str, Any],
    trace: Mapping[str, Any],
    raw: Mapping[str, Any],
    semantics: Mapping[str, Any],
) -> None:
    trial_id = str(raw["trial_id"])
    for field in ("trial_id", "logical_trial_id", "problem_instance", "input_sha256"):
        if row.get(field) != raw.get(field):
            raise FamilyRegistryError(f"aggregate/raw {field} disagreement: {trial_id}")
    if (
        row.get("phase") != raw.get("warmup_or_measured")
        or row.get("repetition") != raw.get("repetition")
        or row.get("included") != (raw.get("timing_eligible") is True)
    ):
        raise FamilyRegistryError(f"aggregate/raw phase or eligibility disagreement: {trial_id}")
    features = _mapping(row.get("features"), f"aggregate features {trial_id}")
    raw_features = _mapping(raw.get("input_features"), f"raw features {trial_id}")
    checks = (
        (features.get("combined_input_sha256"), semantics["input_sha256"]),
        (features.get("n_configurations"), semantics["n_configurations"]),
        (_mapping(features.get("alpha"), "aggregate alpha").get("sha256"),
         semantics["components"]["alpha_determinants"]["sha256"]),
        (_mapping(features.get("beta"), "aggregate beta").get("sha256"),
         semantics["components"]["beta_determinants"]["sha256"]),
        (_mapping(features.get("fcidump"), "aggregate FCIDUMP").get("sha256"),
         semantics["components"]["fcidump"]["sha256"]),
    )
    if any(left != right for left, right in checks):
        raise FamilyRegistryError(f"aggregate component-hash disagreement: {trial_id}")
    if canonical_json(features) != canonical_json(raw_features):
        raise FamilyRegistryError(f"aggregate/raw full feature disagreement: {trial_id}")
    if trace.get("input_sha256") != semantics["input_sha256"]:
        raise FamilyRegistryError(f"completion/semantics hash disagreement: {trial_id}")


def _derive_workloads(
    aggregate: Mapping[str, Any], semantics_by_id: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    workload_objects = _object_list(aggregate.get("workloads"), "aggregate workloads")
    rows_by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for trial_id, semantics in semantics_by_id.items():
        rows_by_key[(semantics["problem_instance"], semantics["input_sha256"])].append(
            trial_id
        )
    seen_keys: set[tuple[str, str]] = set()
    entries: list[dict[str, Any]] = []
    for workload in workload_objects:
        instance = _text(workload.get("problem_instance"), "workload problem_instance")
        input_sha = _digest(workload.get("input_sha256"), "workload input_sha256")
        key = (instance, input_sha)
        if key in seen_keys:
            raise FamilyRegistryError(f"duplicate aggregate workload mapping: {key!r}")
        seen_keys.add(key)
        trial_ids = sorted(rows_by_key.get(key, []))
        if not trial_ids:
            if any(candidate[0] == instance for candidate in rows_by_key):
                raise FamilyRegistryError(f"instance/hash disagreement: {instance}")
            raise FamilyRegistryError(f"unknown aggregate workload mapping: {key!r}")
        first = semantics_by_id[trial_ids[0]]
        for trial_id in trial_ids[1:]:
            if canonical_json(semantics_by_id[trial_id]) != canonical_json(first):
                raise FamilyRegistryError(f"ambiguous workload semantics: {key!r}")
        entry: dict[str, Any] = {
            "family_id": FAMILY_ID,
            "molecule": MOLECULE,
            "basis": None,
            "basis_status": BASIS_STATUS,
            "problem_instance": instance,
            "input_sha256": input_sha,
            "n_alpha_strings": first["n_alpha_strings"],
            "n_beta_strings": first["n_beta_strings"],
            "n_configurations": first["n_configurations"],
            "components": first["components"],
            "source_record_count": len(trial_ids),
            "source_record_ids": trial_ids,
        }
        entry["entry_id"] = _entry_id(entry)
        entries.append(entry)
    if seen_keys != set(rows_by_key):
        raise FamilyRegistryError("aggregate workloads do not cover every raw record key")
    entries.sort(key=lambda item: (item["n_configurations"], item["problem_instance"]))
    return entries


def _family_metadata() -> dict[str, Any]:
    return {
        "family_id": FAMILY_ID,
        "molecule": MOLECULE,
        "basis": None,
        "basis_status": BASIS_STATUS,
        "basis_provenance": {
            "evidence_scope": "verified immutable Stage 4 completion, aggregate, and raw records",
            "reason": (
                "The verified Stage 4 evidence identifies the pinned upstream Fe4S4 "
                "sample but contains no basis-set label; null is retained rather than inferred."
            ),
            "upstream_url": EXPECTED_UPSTREAM_URL,
            "upstream_git_commit": EXPECTED_UPSTREAM_COMMIT,
        },
    }


def _augmentation_contract() -> dict[str, Any]:
    return {
        "mode": "external_metadata_only",
        "raw_records_modified": False,
        "raw_trial_ids_modified": False,
        "lookup_key": ["problem_instance", "input_sha256"],
        "component_crosscheck_fields": [
            "fcidump_sha256",
            "alpha_determinant_sha256",
            "beta_determinant_sha256",
            "n_configurations",
        ],
    }


def _entry_id(entry: Mapping[str, Any]) -> str:
    identity = {
        key: entry.get(key)
        for key in (
            "family_id",
            "molecule",
            "basis",
            "basis_status",
            "problem_instance",
            "input_sha256",
            "n_alpha_strings",
            "n_beta_strings",
            "n_configurations",
            "components",
        )
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()


def _registry_id(registry: Mapping[str, Any]) -> str:
    value = {key: item for key, item in registry.items() if key != "registry_id"}
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _fixed_description(
    path: Path,
    root: Path,
    *,
    expected_sha256: str,
    expected_size: int,
    label: str,
) -> dict[str, Any]:
    description = _description(path, root)
    if description["sha256"] != expected_sha256:
        raise FamilyRegistryError(f"{label} SHA-256 mismatch")
    if description["size_bytes"] != expected_size:
        raise FamilyRegistryError(f"{label} size mismatch")
    return description


def _description(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_path(path),
        "size_bytes": path.stat().st_size,
    }


def _resolve_claimed_file(
    root: Path, claim: Mapping[str, Any], label: str
) -> Path:
    _validate_file_claim(claim, label)
    relative = Path(str(claim["path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise FamilyRegistryError(f"{label} path must be repository-relative")
    candidate = root / relative
    if candidate.is_symlink():
        raise FamilyRegistryError(f"{label} must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise FamilyRegistryError(f"cannot resolve {label}: {error}") from error
    if not resolved.is_file():
        raise FamilyRegistryError(f"{label} is not a regular file")
    if resolved.stat().st_size != claim["size_bytes"]:
        raise FamilyRegistryError(f"{label} size mismatch")
    if sha256_path(resolved) != claim["sha256"]:
        raise FamilyRegistryError(f"{label} SHA-256 mismatch")
    return resolved


def _validate_file_claim(claim: Mapping[str, Any], label: str) -> None:
    if set(claim) != {"path", "sha256", "size_bytes"}:
        raise FamilyRegistryError(f"{label} fields differ from file-claim contract")
    _text(claim.get("path"), f"{label} path")
    _digest(claim.get("sha256"), f"{label} SHA-256")
    _positive_int(claim.get("size_bytes"), f"{label} size")


def _exact_file(root: Path, value: Path, expected: str, label: str) -> Path:
    path = _input_path(root, value)
    expected_path = (root / expected).resolve()
    if path != expected_path:
        raise FamilyRegistryError(f"{label} must be exact path {expected}")
    if (root / expected).is_symlink() or not path.is_file():
        raise FamilyRegistryError(f"{label} must be a nonsymlink regular file")
    return path


def _exact_directory(root: Path, value: Path, expected: str, label: str) -> Path:
    path = _input_path(root, value)
    expected_path = (root / expected).resolve()
    if path != expected_path:
        raise FamilyRegistryError(f"{label} must be exact path {expected}")
    if (root / expected).is_symlink() or not path.is_dir():
        raise FamilyRegistryError(f"{label} must be a nonsymlink directory")
    return path


def _input_path(root: Path, value: Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise FamilyRegistryError(f"cannot resolve repository evidence: {error}") from error
    return resolved


def _root(value: Path) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except OSError as error:
        raise FamilyRegistryError(f"cannot resolve repository root: {error}") from error
    if not root.is_dir():
        raise FamilyRegistryError("repository root must be a directory")
    return root


def _load_strict_object(path: Path, label: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_bytes().decode("utf-8", errors="strict"),
            parse_constant=reject_constant,
            object_pairs_hook=unique,
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise FamilyRegistryError(f"cannot load {label}: {error}") from error
    if not isinstance(value, dict):
        raise FamilyRegistryError(f"{label} must be an object")
    return value


def _unique_by_digest(
    values: Sequence[Mapping[str, Any]], field: str, label: str
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for value in values:
        key = _digest(value.get(field), f"{label} {field}")
        if key in result:
            raise FamilyRegistryError(f"duplicate {field} in {label}: {key}")
        result[key] = value
    return result


def _object_list(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise FamilyRegistryError(f"{label} must be a list of objects")
    return list(value)


def _digest_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise FamilyRegistryError(f"{label} must be a list")
    result = [_digest(item, label) for item in value]
    if len(result) != len(set(result)):
        raise FamilyRegistryError(f"{label} contains duplicates")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FamilyRegistryError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FamilyRegistryError(f"{label} must be nonempty trimmed text")
    return value


def _digest(value: Any, label: str) -> str:
    text = _text(value, label)
    if _SHA256_RE.fullmatch(text) is None:
        raise FamilyRegistryError(f"{label} must be lowercase SHA-256")
    return text


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FamilyRegistryError(f"{label} must be a positive integer")
    return value


def _strict_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise FamilyRegistryError(f"registry is not strict JSON: {error}") from error


__all__ = [
    "BASIS_STATUS",
    "EXPECTED_AGGREGATE_PATH",
    "EXPECTED_COMPLETION_PATH",
    "EXPECTED_RAW_DIRECTORY",
    "FAMILY_ID",
    "FamilyRegistryError",
    "build_fe4s4_family_registry",
    "resolve_family_entry",
    "sha256_path",
    "validate_family_registry",
    "write_family_registry",
]
