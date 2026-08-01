"""Deterministic trial identities and immutable JSON record handling."""

from __future__ import annotations

import hashlib
import fcntl
import json
import math
import os
import re
import socket
import tempfile
from collections.abc import Mapping
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 3
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2, SCHEMA_VERSION})
SHA256_RE = re.compile(r"[0-9a-f]{64}")
FAMILY_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "trial_id",
        "logical_trial_id",
        "attempt_index",
        "timestamp_utc",
        "finished_timestamp_utc",
        "hostname",
        "project_git_commit",
        "upstream_url",
        "upstream_git_commit",
        "build_id",
        "compiler_and_flags",
        "gpu_name",
        "driver_version",
        "cuda_toolkit_version",
        "cpu_model",
        "physical_cores",
        "problem_family",
        "problem_instance",
        "input_sha256",
        "seed",
        "n_orbitals",
        "n_spin_orbitals",
        "n_alpha_strings",
        "n_beta_strings",
        "n_configurations",
        "estimated_work",
        "estimated_cache_bytes",
        "backend",
        "cpu_threads",
        "mpi_ranks",
        "bit_length",
        "shuffle",
        "cache_mode",
        "decomposition",
        "warmup_or_measured",
        "repetition",
        "command",
        "wall_time_s",
        "initialization_time_s",
        "solver_time_s",
        "matvec_time_s",
        "transfer_time_s",
        "iterations",
        "energy_or_eigenvalue",
        "reference_value",
        "relative_error",
        "correct",
        "peak_host_rss_mb",
        "peak_gpu_memory_mb",
        "timeout",
        "oom",
        "exit_code",
        "stdout_log",
        "stderr_log",
        "notes",
        "status",
        "failure_kind",
        "parse_error",
        "skip_reason",
        "process_success",
        "scientific_success",
        "timing_eligible",
        "input_files",
        "environment_overrides",
        "preflight",
        "resource_monitoring",
    }
)
V2_REQUIRED_FIELDS = REQUIRED_FIELDS | frozenset({"logical_identity"})
V3_REQUIRED_FIELDS = V2_REQUIRED_FIELDS | frozenset(
    {"family_id", "molecule", "basis"}
)

VALID_STATUSES = frozenset(
    {
        "success",
        "failed",
        "timeout",
        "oom",
        "skipped_invalid",
        "skipped_memory",
        "deferred_gpu_busy",
    }
)
VALID_BACKENDS = frozenset({"cpu", "gpu", "mock"})
VALID_MEASUREMENT_KINDS = frozenset({"warmup", "measured", "correctness", "test"})


class RecordError(ValueError):
    """Base exception for invalid or conflicting trial records."""


class RecordExistsError(RecordError):
    """Raised when an immutable record path already exists."""


class ClaimExistsError(RecordError):
    """Raised when another process already owns a trial launch claim."""


def canonical_json(value: Any) -> str:
    """Return a stable JSON encoding suitable for hashing."""

    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def make_trial_id(identity: Mapping[str, Any]) -> str:
    """Hash all execution-defining fields into a deterministic trial ID."""

    if not identity:
        raise RecordError("Trial identity must not be empty")
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def validate_record(record: Mapping[str, Any]) -> None:
    """Validate the mandatory Stage 2 record contract."""

    schema_version = record.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version not in SUPPORTED_SCHEMA_VERSIONS
    ):
        raise RecordError(f"Unsupported schema_version: {schema_version!r}")

    required_fields = {
        1: REQUIRED_FIELDS,
        2: V2_REQUIRED_FIELDS,
        3: V3_REQUIRED_FIELDS,
    }[schema_version]
    missing = sorted(required_fields.difference(record))
    if missing:
        raise RecordError(f"Missing required record fields: {', '.join(missing)}")

    if not isinstance(record["trial_id"], str) or not SHA256_RE.fullmatch(record["trial_id"]):
        raise RecordError("trial_id must be a lowercase SHA-256 hex digest")
    if not isinstance(record["logical_trial_id"], str) or not SHA256_RE.fullmatch(
        record["logical_trial_id"]
    ):
        raise RecordError("logical_trial_id must be a lowercase SHA-256 hex digest")

    attempt_index = record["attempt_index"]
    if (
        isinstance(attempt_index, bool)
        or not isinstance(attempt_index, int)
        or attempt_index < 0
    ):
        raise RecordError("attempt_index must be a nonnegative integer")

    if schema_version in {2, 3}:
        logical_identity = record["logical_identity"]
        if not isinstance(logical_identity, Mapping):
            raise RecordError("logical_identity must be an object")
        expected_logical_trial_id = make_trial_id(logical_identity)
        if record["logical_trial_id"] != expected_logical_trial_id:
            raise RecordError("logical_trial_id does not match logical_identity")
        expected_trial_id = make_trial_id(
            {
                "logical_trial_id": record["logical_trial_id"],
                "attempt_index": attempt_index,
            }
        )
        if record["trial_id"] != expected_trial_id:
            raise RecordError("trial_id does not match logical_trial_id and attempt_index")

    if schema_version == 3:
        logical_identity = record["logical_identity"]
        assert isinstance(logical_identity, Mapping)
        metadata: dict[str, str] = {}
        for field in ("family_id", "molecule", "basis"):
            value = record[field]
            if not isinstance(value, str) or not value:
                raise RecordError(f"{field} must be a nonempty string")
            if value != value.strip():
                raise RecordError(f"{field} must not contain surrounding whitespace")
            metadata[field] = value
            if logical_identity.get(field) != value:
                raise RecordError(f"{field} does not match logical_identity")
        if FAMILY_ID_RE.fullmatch(metadata["family_id"]) is None:
            raise RecordError("family_id must be a lowercase ASCII slug")
        if logical_identity.get("schema_version") != 3:
            raise RecordError("logical_identity schema_version must be 3")
        if logical_identity.get("workload") != record["problem_instance"]:
            raise RecordError("problem_instance does not match logical_identity workload")
        if logical_identity.get("sweep_name") != record["problem_family"]:
            raise RecordError("problem_family does not match logical_identity sweep_name")

    if record["status"] not in VALID_STATUSES:
        raise RecordError(f"Invalid status: {record['status']!r}")
    if record["backend"] not in VALID_BACKENDS:
        raise RecordError(f"Invalid backend: {record['backend']!r}")
    if record["warmup_or_measured"] not in VALID_MEASUREMENT_KINDS:
        raise RecordError(
            f"Invalid warmup_or_measured value: {record['warmup_or_measured']!r}"
        )

    command = record["command"]
    if not isinstance(command, list) or not command or not all(
        isinstance(argument, str) for argument in command
    ):
        raise RecordError("command must be a nonempty list of strings")

    for field in ("timeout", "oom"):
        if not isinstance(record[field], bool):
            raise RecordError(f"{field} must be boolean")
    if record["correct"] is not None and not isinstance(record["correct"], bool):
        raise RecordError("correct must be boolean or null")
    if record["timeout"] != (record["status"] == "timeout"):
        raise RecordError("timeout must agree with status")
    if record["oom"] != (record["status"] == "oom"):
        raise RecordError("oom must agree with status")
    if record["status"] == "success" and record["exit_code"] != 0:
        raise RecordError("successful records must have exit_code 0")
    for field in ("process_success", "scientific_success", "timing_eligible"):
        if not isinstance(record[field], bool):
            raise RecordError(f"{field} must be boolean")
    if record["process_success"] != (record["exit_code"] == 0 and not record["timeout"]):
        raise RecordError("process_success must agree with exit_code and timeout")
    if record["status"] == "success" and not record["scientific_success"]:
        raise RecordError("success status requires scientific_success")
    if record["timing_eligible"] and record["status"] != "success":
        raise RecordError("only successful trials can be timing eligible")
    if record["failure_kind"] is not None and not isinstance(record["failure_kind"], str):
        raise RecordError("failure_kind must be a string or null")
    if record["parse_error"] is not None and not isinstance(record["parse_error"], str):
        raise RecordError("parse_error must be a string or null")
    if record["skip_reason"] is not None and not isinstance(record["skip_reason"], str):
        raise RecordError("skip_reason must be a string or null")
    if not isinstance(record["notes"], list) or not all(
        isinstance(note, str) for note in record["notes"]
    ):
        raise RecordError("notes must be a list of strings")
    if not isinstance(record["input_files"], list):
        raise RecordError("input_files must be a list")
    if not isinstance(record["environment_overrides"], Mapping):
        raise RecordError("environment_overrides must be an object")
    if not isinstance(record["preflight"], Mapping):
        raise RecordError("preflight must be an object")
    if not isinstance(record["resource_monitoring"], Mapping):
        raise RecordError("resource_monitoring must be an object")

    for field in (
        "physical_cores",
        "n_alpha_strings",
        "n_beta_strings",
        "n_configurations",
        "estimated_cache_bytes",
        "cpu_threads",
        "mpi_ranks",
        "repetition",
    ):
        value = record[field]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise RecordError(f"{field} must be an integer or null")
        if isinstance(value, int) and value < 0:
            raise RecordError(f"{field} must be nonnegative")

    _validate_finite_numbers(record)
    canonical_json(record)


def _validate_finite_numbers(value: Any, path: str = "record") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise RecordError(f"Non-finite number at {path}")
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _validate_finite_numbers(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_finite_numbers(nested, f"{path}[{index}]")


def write_immutable_json(path: Path, record: Mapping[str, Any]) -> None:
    """Atomically create a JSON record without ever replacing an existing path."""

    validate_record(record)
    payload = (json.dumps(record, allow_nan=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RecordExistsError(f"Refusing to overwrite immutable record: {path}")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError as error:
            raise RecordExistsError(f"Refusing to overwrite immutable record: {path}") from error
        _fsync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def load_record(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        record = json.load(stream)
    if not isinstance(record, dict):
        raise RecordError(f"Record root must be an object: {path}")
    validate_record(record)
    if path.stem != record["trial_id"]:
        raise RecordError(
            f"Record filename does not match embedded trial_id: {path.name}"
        )
    return record


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class TrialClaim(AbstractContextManager["TrialClaim"]):
    """Exclusive per-trial claim preventing duplicate concurrent launches."""

    def __init__(self, record_path: Path, metadata: Mapping[str, Any]) -> None:
        self.path = record_path.with_suffix(record_path.suffix + ".claim")
        self.metadata = dict(metadata)
        self.acquired = False
        self._stream: Any = None
        self._inode: tuple[int, int] | None = None

    def __enter__(self) -> "TrialClaim":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            **self.metadata,
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "process_start_ticks": _process_start_ticks(os.getpid()),
            "claimed_at_utc": utc_now(),
        }
        if payload["process_start_ticks"] is None:
            raise RecordError("Cannot read this process's /proc start time for trial claim")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor: int | None = None
        for attempt in range(2):
            try:
                descriptor = os.open(self.path, flags, 0o644)
                break
            except FileExistsError as error:
                if attempt == 0 and self._remove_stale_claim():
                    continue
                raise ClaimExistsError(f"Trial already claimed: {self.path}") from error
        if descriptor is None:  # Defensive: the loop either opens or raises.
            raise ClaimExistsError(f"Trial already claimed: {self.path}")
        try:
            stat_result = os.fstat(descriptor)
            self._inode = (stat_result.st_dev, stat_result.st_ino)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._stream = os.fdopen(descriptor, "w", encoding="utf-8")
            descriptor = None
            self._stream.write(
                json.dumps(payload, allow_nan=False, indent=2, sort_keys=True)
            )
            self._stream.write("\n")
            self._stream.flush()
            os.fsync(self._stream.fileno())
            _fsync_directory(self.path.parent)
            self.acquired = True
            return self
        except BaseException:
            self._unlink_if_owned()
            if descriptor is not None:
                os.close(descriptor)
            if self._stream is not None:
                self._stream.close()
                self._stream = None
            raise

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if self.acquired:
            self._unlink_if_owned()
            if self._stream is not None:
                self._stream.close()
                self._stream = None
            self.acquired = False

    def _remove_stale_claim(self) -> bool:
        """Remove a provably stale same-host claim while holding its inode lock."""

        read_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            read_flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, read_flags)
        except FileNotFoundError:
            return True
        try:
            stat_result = os.fstat(descriptor)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            try:
                with os.fdopen(os.dup(descriptor), "r", encoding="utf-8") as stream:
                    existing = json.load(stream)
            except (OSError, UnicodeError, json.JSONDecodeError):
                return False
            if not isinstance(existing, dict):
                return False
            if existing.get("hostname") != socket.gethostname():
                return False
            pid = existing.get("pid")
            claimed_start_ticks = existing.get("process_start_ticks")
            if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
                return False
            if (
                isinstance(claimed_start_ticks, bool)
                or not isinstance(claimed_start_ticks, int)
                or claimed_start_ticks < 0
            ):
                return False
            observed_start_ticks = _process_start_ticks(pid)
            if (
                observed_start_ticks is not None
                and observed_start_ticks == claimed_start_ticks
            ):
                return False
            expected_inode = (stat_result.st_dev, stat_result.st_ino)
            if not _unlink_matching_inode(self.path, expected_inode):
                return False
            _fsync_directory(self.path.parent)
            return True
        finally:
            os.close(descriptor)

    def _unlink_if_owned(self) -> None:
        if self._inode is not None and _unlink_matching_inode(self.path, self._inode):
            _fsync_directory(self.path.parent)
        self._inode = None


def _process_start_ticks(pid: int) -> int | None:
    """Return Linux /proc field 22 for *pid*, or ``None`` if it is gone."""

    try:
        stat_line = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None
    closing_parenthesis = stat_line.rfind(")")
    if closing_parenthesis < 0:
        return None
    fields_after_command = stat_line[closing_parenthesis + 1 :].split()
    if len(fields_after_command) <= 19:
        return None
    try:
        return int(fields_after_command[19])
    except ValueError:
        return None


def _unlink_matching_inode(path: Path, expected_inode: tuple[int, int]) -> bool:
    """Unlink *path* only when it still names the expected device/inode pair."""

    try:
        stat_result = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    if (stat_result.st_dev, stat_result.st_ino) != expected_inode:
        return False
    path.unlink()
    return True
