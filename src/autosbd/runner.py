"""Safe, immutable execution of one official AMD-HPC SBD trial."""

from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .config import CandidateConfig, SolverConfig, SweepConfig, TrialTemplate
from .features import (
    InputFeatures,
    SourceMemoryEstimate,
    estimate_source_memory,
    extract_input_features,
)
from .process import ExecutionResult, run_monitored
from .records import (
    SCHEMA_VERSION,
    TrialClaim,
    canonical_json,
    load_record,
    make_trial_id,
    utc_now,
    write_immutable_json,
)
from .sbd_output import ParsedSbdOutput, SbdParseError, parse_sbd_file
from .system import (
    artifact_description,
    describe_input_files,
    dynamic_preflight,
    git_state,
    sha256_file,
    static_system_snapshot,
)


OFFICIAL_UPSTREAM_URL = "https://github.com/AMD-HPC/amd-sbd"
OFFICIAL_UPSTREAM_COMMIT = "729cfa3a5011fb805eb9e686a7711f6919836dcb"
OFFICIAL_BUILD_SHA256 = {
    "cpu": "190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07",
    "gpu": "8f1481b6bcb4ddf3326453fd3a7c03dc36e29034629f46c5e982a4c17e43bc07",
}
OFFICIAL_BUILD_DIRECTORY_PREFIX = "amd-729cfa3a-"
DEFAULT_CONNECTIVITY_PAIR_LIMIT = 1_000_000
DEFAULT_REFERENCE_RTOL = 1.0e-10
_RECORD_SCHEMA_BY_CONFIG_SCHEMA = {1: 2, 2: SCHEMA_VERSION}
_REQUIRED_BUILD_FLAGS = {
    "cpu": frozenset({"-mp", "-DSBD_TRADMODE", "-DUSE_DET_CACHE_OMP"}),
    "gpu": frozenset(
        {
            "-mp=gpu",
            "-gpu=cc89",
            "-DSBD_TRADMODE",
            "-DUSE_GPU",
            "-DUSE_DET_CACHE_OMP",
            "-DUSE_HIJ_OMP_OFFLOAD",
        }
    ),
}
_SENSITIVE_ENV_RE = re.compile(
    r"(?:TOKEN|PASSWORD|PASSWD|SECRET|CREDENTIAL|PRIVATE|API[_-]?KEY)",
    re.IGNORECASE,
)
_OOM_RE = re.compile(
    rb"(?:out of memory|std::bad_alloc|cuda[^\n]{0,80}memory|"
    rb"hip[^\n]{0,80}memory|\boom\b)",
    re.IGNORECASE,
)


class RunnerError(RuntimeError):
    """Raised for harness/infrastructure faults, never solver outcomes."""


class NodeBusyError(RunnerError):
    """Raised when another AutoSBD process owns the node-wide run lock."""


@dataclass(frozen=True)
class TrialRunResult:
    record_path: Path
    record: dict[str, Any]
    launched: bool
    reused: bool


class NodeRunLock:
    """Process-lifetime advisory lock preventing overlapping benchmark trials."""

    def __init__(self, path: Path, metadata: Mapping[str, Any]) -> None:
        self.path = path
        self.metadata = dict(metadata)
        self._stream: Any = None

    def __enter__(self) -> "NodeRunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            stream.close()
            raise NodeBusyError(
                f"another AutoSBD trial owns node lock {self.path}"
            ) from error
        payload = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "acquired_at_utc": utc_now(),
            **self.metadata,
        }
        stream.seek(0)
        stream.truncate()
        json.dump(payload, stream, allow_nan=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
        self._stream = stream
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if self._stream is not None:
            fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
            self._stream.close()
            self._stream = None


class TrialRunner:
    """Execute sequential trials and atomically persist every terminal outcome."""

    def __init__(
        self,
        *,
        project_root: Path,
        results_dir: Path | None = None,
        logs_dir: Path | None = None,
        upstream_root: Path | None = None,
        connectivity_pair_limit: int = DEFAULT_CONNECTIVITY_PAIR_LIMIT,
        cuda_toolkit_version: str | None = None,
        compiler_identity: str | None = None,
        reference_rtol: float = DEFAULT_REFERENCE_RTOL,
    ) -> None:
        self.project_root = Path(project_root).resolve(strict=True)
        self.results_dir = (
            Path(results_dir).resolve()
            if results_dir is not None
            else self.project_root / "results" / "raw"
        )
        self.logs_dir = (
            Path(logs_dir).resolve()
            if logs_dir is not None
            else self.project_root / "logs" / "trials"
        )
        self.upstream_root = (
            Path(upstream_root).resolve(strict=True)
            if upstream_root is not None
            else (self.project_root / "external" / "amd-sbd").resolve(strict=True)
        )
        if connectivity_pair_limit < 0:
            raise RunnerError("connectivity_pair_limit must be nonnegative")
        if reference_rtol <= 0:
            raise RunnerError("reference_rtol must be positive")
        self.connectivity_pair_limit = connectivity_pair_limit
        self.reference_rtol = reference_rtol
        self.project_state = git_state(
            self.project_root,
            ignore_untracked_json_under=Path("results/raw"),
        )
        self.upstream_state = git_state(self.upstream_root)
        self._assert_official_upstream()
        self.cuda_toolkit_version = (
            cuda_toolkit_version or _detect_cuda_toolkit_version()
        )
        self.compiler_identity = (
            compiler_identity or _detect_nvhpc_compiler_identity()
        )
        self.system_snapshot = static_system_snapshot(self.cuda_toolkit_version)
        self.harness_sha256 = _harness_sha256(self.project_root)
        self.node_lock_path = self.project_root / ".autosbd" / "node-run.lock"

    def run(
        self,
        template: TrialTemplate,
        *,
        config: SweepConfig,
        attempt_index: int = 0,
        reference_value: float | None = None,
    ) -> TrialRunResult:
        """Run or reuse one deterministic trial from its owning sweep config."""

        self._validate_template_config(template, config)
        record_schema_version = _record_schema_version(config)
        if attempt_index < 0:
            raise RunnerError("attempt_index must be nonnegative")
        explicit_reference = reference_value is not None
        if reference_value is None:
            reference_value = template.workload.reference_value
        reference_source = (
            "cli:--reference-value"
            if explicit_reference
            else template.workload.reference_source
        )

        features = self._features(template)
        memory = estimate_source_memory(
            features,
            bit_length=template.solver.bit_length,
            max_block=template.solver.block,
            iterations=template.solver.iteration,
            method=template.solver.method,
            rdm=template.solver.rdm,
            alpha_comm_size=template.solver.adet_comm_size,
            beta_comm_size=template.solver.bdet_comm_size,
            task_comm_size=template.solver.task_comm_size,
        )
        command = self._command(template)
        environment_overrides = self._environment_overrides(template.candidate)
        build = self._build_description(template.candidate)
        input_files = self._input_files(template)
        if not _input_files_match_features(input_files, features):
            raise RunnerError("feature hashes disagree with initial input-file hashes")
        validation_evidence = self._validation_evidence(
            template, config, features, build
        )

        logical_identity = {
            "schema_version": record_schema_version,
            "sweep_name": template.sweep_name,
            "workload": template.workload.name,
            "input_sha256": features.combined_input_sha256,
            "candidate": {
                "name": template.candidate.name,
                "backend": template.candidate.backend,
                "threads": template.candidate.threads,
                "mpi_ranks": template.candidate.mpi_ranks,
                "build_id": build["build_id"],
                "artifact_sha256": build["artifact"].get("sha256"),
                "compiler_identity": build["compiler_identity"],
                "compiler_flags": list(template.candidate.compiler_flags),
            },
            "solver": _solver_identity(template.solver),
            "protocol": {
                "purpose": config.protocol.purpose,
                "warmups": config.protocol.warmups,
                "repetitions": config.protocol.repetitions,
                "seed": config.protocol.seed,
                "timeout_s": config.protocol.timeout_s,
                "correctness_validated": config.protocol.correctness_validated,
                "validation_manifest_sha256": validation_evidence.get("sha256"),
            },
            "phase": template.phase,
            "repetition": template.repetition,
            "reference_value": reference_value,
            "reference_source": reference_source,
            "command": command,
            "environment_overrides": _redact_environment(environment_overrides),
            "project_commit": self.project_state["commit"],
            "project_dirty": self.project_state["dirty"],
            "harness_sha256": self.harness_sha256,
            "upstream_commit": self.upstream_state["commit"],
            "machine_fingerprint": self.system_snapshot["machine_fingerprint"],
        }
        if record_schema_version == 3:
            logical_identity.update(
                {
                    "family_id": template.workload.family_id,
                    "molecule": template.workload.molecule,
                    "basis": template.workload.basis,
                }
            )
        logical_trial_id = make_trial_id(logical_identity)
        trial_id = make_trial_id(
            {"logical_trial_id": logical_trial_id, "attempt_index": attempt_index}
        )
        paths = self._artifact_paths(trial_id)
        record_path = paths["record"]
        if record_path.exists():
            record = _load_expected_record(
                record_path,
                trial_id,
                logical_trial_id,
                logical_identity,
                record_schema_version,
            )
            return TrialRunResult(record_path, record, False, True)

        claim_metadata = {
            "trial_id": trial_id,
            "logical_trial_id": logical_trial_id,
            "attempt_index": attempt_index,
        }
        with (
            TrialClaim(record_path, claim_metadata),
            NodeRunLock(self.node_lock_path, claim_metadata),
        ):
            if record_path.exists():
                record = _load_expected_record(
                    record_path,
                    trial_id,
                    logical_trial_id,
                    logical_identity,
                    record_schema_version,
                )
                return TrialRunResult(record_path, record, False, True)

            started_timestamp = utc_now()
            preflight = _safe_preflight()
            before_launch_files, input_rehash_error = self._rehash_inputs(template)
            input_unchanged_before = bool(
                before_launch_files is not None
                and _same_input_files(input_files, before_launch_files)
            )
            input_integrity: dict[str, Any] = {
                "initial": input_files,
                "before_launch": before_launch_files,
                "after_run": None,
                "unchanged_before_launch": input_unchanged_before,
                "unchanged_after_run": None,
                "rehash_error": input_rehash_error,
            }
            preflight["input_unchanged_before_launch"] = input_unchanged_before

            existing_artifacts = [
                name
                for name in ("stdout", "stderr", "resources")
                if paths[name].exists()
            ]
            execution: ExecutionResult | None = None
            parsed: ParsedSbdOutput | None = None
            parse_error: str | None = None
            skip_reason: str | None = None
            launched = False

            if existing_artifacts:
                _ensure_artifacts(paths)
                status = "failed"
                failure_kind = "orphaned_artifacts"
                skip_reason = (
                    "preserved artifacts without a record: "
                    + ", ".join(existing_artifacts)
                    + "; use a new attempt_index to retry"
                )
            elif not input_unchanged_before:
                _ensure_artifacts(paths)
                status = "skipped_invalid"
                failure_kind = "input_changed_before_launch"
                skip_reason = input_rehash_error or (
                    "input hashes changed between feature extraction and launch"
                )
            else:
                skip_status, skip_reason = self._admission_decision(
                    template.candidate, memory, preflight
                )
                if skip_status is not None:
                    _ensure_artifacts(paths)
                    status = skip_status
                    failure_kind = skip_status
                else:
                    launched = True
                    complete_environment = os.environ.copy()
                    complete_environment.update(environment_overrides)
                    execution = run_monitored(
                        command,
                        cwd=self.project_root,
                        environment=complete_environment,
                        stdout_path=paths["stdout"],
                        stderr_path=paths["stderr"],
                        resource_path=paths["resources"],
                        timeout_s=config.protocol.timeout_s,
                        monitor_gpu=template.candidate.backend == "gpu",
                    )
                    status, failure_kind = _process_status(
                        execution, paths["stderr"]
                    )
                    if status == "success":
                        try:
                            parsed = parse_sbd_file(
                                paths["stdout"],
                                residual_tolerance=template.solver.tolerance,
                                expected_orbitals=features.fcidump.n_orbitals,
                                require_device_assignment=(
                                    template.candidate.backend == "gpu"
                                ),
                            )
                        except (OSError, UnicodeError, SbdParseError) as error:
                            parse_error = f"{type(error).__name__}: {error}"
                            status = "failed"
                            failure_kind = "output_parse_error"
                        else:
                            if not parsed.converged:
                                status = "failed"
                                failure_kind = "not_converged"

            after_run_files, after_rehash_error = self._rehash_inputs(template)
            input_unchanged_after = bool(
                after_run_files is not None
                and _same_input_files(input_files, after_run_files)
            )
            input_integrity["after_run"] = after_run_files
            input_integrity["unchanged_after_run"] = input_unchanged_after
            if after_rehash_error is not None:
                input_integrity["rehash_error"] = after_rehash_error
            if launched and not input_unchanged_after:
                status = "failed"
                failure_kind = "input_changed_during_run"

            relative_error: float | None = None
            correct: bool | None = None
            if parsed is not None and reference_value is not None:
                relative_error = abs(parsed.energy - reference_value) / max(
                    abs(reference_value), 1.0e-300
                )
                correct = (
                    parsed.converged and relative_error <= self.reference_rtol
                )
                if not correct and status == "success":
                    status = "failed"
                    failure_kind = "reference_mismatch"

            process_success = bool(
                execution is not None
                and execution.exit_code == 0
                and not execution.timed_out
            )
            scientific_success = bool(
                status == "success" and parsed is not None and parsed.converged
            )
            monitoring_complete = bool(
                execution is not None
                and execution.resource_samples > 0
                and execution.host_monitor_complete
                and (
                    execution.gpu_monitor_complete is True
                    if template.candidate.backend == "gpu"
                    else True
                )
            )
            timing_eligible = bool(
                scientific_success
                and correct is True
                and template.phase == "measured"
                and config.protocol.purpose in {"pilot", "final"}
                and config.protocol.warmups > 0
                and config.protocol.correctness_validated
                and validation_evidence["valid"]
                and not self.project_state["dirty"]
                and monitoring_complete
                and input_unchanged_before
                and input_unchanged_after
            )
            run_artifacts = {
                name: artifact_description(paths[name], self.project_root)
                for name in ("stdout", "stderr", "resources")
            }
            record = self._record(
                template=template,
                config=config,
                record_schema_version=record_schema_version,
                trial_id=trial_id,
                logical_trial_id=logical_trial_id,
                logical_identity=logical_identity,
                attempt_index=attempt_index,
                started_timestamp=started_timestamp,
                command=command,
                environment_overrides=environment_overrides,
                build=build,
                input_files=input_files,
                input_integrity=input_integrity,
                features=features,
                memory=memory,
                validation_evidence=validation_evidence,
                preflight=preflight,
                paths=paths,
                run_artifacts=run_artifacts,
                execution=execution,
                parsed=parsed,
                status=status,
                failure_kind=failure_kind,
                parse_error=parse_error,
                skip_reason=skip_reason,
                reference_value=reference_value,
                reference_source=reference_source,
                relative_error=relative_error,
                correct=correct,
                process_success=process_success,
                scientific_success=scientific_success,
                timing_eligible=timing_eligible,
            )
            write_immutable_json(record_path, record)
            durable_record = _load_expected_record(
                record_path,
                trial_id,
                logical_trial_id,
                logical_identity,
                record_schema_version,
            )
            return TrialRunResult(record_path, durable_record, launched, False)

    def _assert_official_upstream(self) -> None:
        commit = self.upstream_state.get("commit")
        url = _normalize_repo_url(str(self.upstream_state.get("url", "")))
        if commit != OFFICIAL_UPSTREAM_COMMIT:
            raise RunnerError(
                f"official AMD pin required: {OFFICIAL_UPSTREAM_COMMIT}; got {commit}"
            )
        if url != _normalize_repo_url(OFFICIAL_UPSTREAM_URL):
            raise RunnerError(
                f"official AMD origin required: {OFFICIAL_UPSTREAM_URL}; got {url}"
            )
        if self.upstream_state.get("dirty") is not False:
            raise RunnerError("official AMD upstream worktree must be clean")

    def _validate_template_config(
        self, template: TrialTemplate, config: SweepConfig
    ) -> None:
        if template.sweep_name != config.name or template.solver != config.solver:
            raise RunnerError("trial template does not belong to the supplied sweep")
        if template.workload not in config.workloads:
            raise RunnerError("trial workload is absent from the supplied sweep")
        if template.candidate not in config.candidates:
            raise RunnerError("trial candidate is absent from the supplied sweep")

    def _features(self, template: TrialTemplate) -> InputFeatures:
        workload = template.workload
        beta = workload.bdetfile
        if beta is not None and beta.resolve() != workload.adetfile.resolve():
            if template.candidate.backend != "mock":
                raise RunnerError(
                    "the pinned AMD executable accepts only --adetfile; distinct "
                    "beta determinant files are unsupported by this harness"
                )
        return extract_input_features(
            workload.fcidump,
            workload.adetfile,
            beta,
            max_connectivity_pairs=self.connectivity_pair_limit,
        )

    def _input_files(self, template: TrialTemplate) -> list[dict[str, Any]]:
        workload = template.workload
        return describe_input_files(
            {
                "fcidump": workload.fcidump,
                "alpha": workload.adetfile,
                "beta": workload.bdetfile or workload.adetfile,
            },
            self.project_root,
        )

    def _rehash_inputs(
        self, template: TrialTemplate
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        try:
            return self._input_files(template), None
        except (OSError, RuntimeError, ValueError) as error:
            return None, f"{type(error).__name__}: {error}"

    def _command(self, template: TrialTemplate) -> list[str]:
        candidate = template.candidate
        if candidate.backend == "mock":
            return list(candidate.base_argv)
        workload = template.workload
        executable = str(candidate.base_argv[0])
        command = [executable]
        if candidate.mpi_ranks > 1:
            command = [
                _mpi_launcher(),
                "--bind-to",
                "core",
                "-np",
                str(candidate.mpi_ranks),
                executable,
            ]
        command.extend(
            [
                "--fcidump",
                str(workload.fcidump),
                "--adetfile",
                str(workload.adetfile),
                *template.solver.amd_cli_args(),
            ]
        )
        if "--init" in command or "--bdetfile" in command:
            raise RunnerError("internal error: unsupported AMD CLI option emitted")
        return command

    def _environment_overrides(
        self, candidate: CandidateConfig
    ) -> dict[str, str]:
        environment = dict(candidate.environment)
        environment.update(
            {
                "OMP_NUM_THREADS": str(candidate.threads),
                "OMP_PLACES": "cores",
                "OMP_PROC_BIND": "close",
                "OMP_DYNAMIC": "false",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "BLIS_NUM_THREADS": "1",
            }
        )
        if candidate.backend == "gpu":
            environment.update(
                {
                    "CUDA_VISIBLE_DEVICES": "0",
                    "OMP_TARGET_OFFLOAD": "MANDATORY",
                    "OMP_DISPLAY_ENV": "VERBOSE",
                }
            )
        elif candidate.backend == "cpu":
            environment.update(
                {
                    "OMP_TARGET_OFFLOAD": "DISABLED",
                    "OMP_DISPLAY_ENV": "VERBOSE",
                }
            )
        nvhpc_paths = _nvhpc_path_entries()
        if candidate.backend in {"cpu", "gpu"} and nvhpc_paths:
            inherited_path = os.environ.get("PATH", "")
            environment["PATH"] = os.pathsep.join(
                [*nvhpc_paths, inherited_path]
            )
        return environment

    def _build_description(self, candidate: CandidateConfig) -> dict[str, Any]:
        if candidate.backend == "mock":
            digest = hashlib.sha256(
                "\0".join(candidate.mock_argv).encode()
            ).hexdigest()
            return {
                "build_id": f"mock-{digest[:12]}",
                "compiler_identity": "CPython mock fixture",
                "compiler_and_flags": "CPython mock fixture; no compiled solver",
                "artifact": {
                    "path": candidate.mock_argv[0],
                    "sha256": digest,
                },
            }
        assert candidate.executable is not None
        artifact = artifact_description(candidate.executable, self.project_root)
        expected_sha = OFFICIAL_BUILD_SHA256[candidate.backend]
        if artifact["sha256"] != expected_sha:
            raise RunnerError(
                f"{candidate.backend} artifact hash is not the validated official build: "
                f"{artifact['sha256']} != {expected_sha}"
            )
        build_root = (self.project_root / "build" / "upstream").resolve()
        try:
            relative = candidate.executable.resolve().relative_to(build_root)
        except ValueError as error:
            raise RunnerError("official AMD executable must be under build/upstream") from error
        if not relative.parts or not relative.parts[0].startswith(
            OFFICIAL_BUILD_DIRECTORY_PREFIX
        ):
            raise RunnerError("official AMD executable build directory is not pinned")
        missing_flags = _REQUIRED_BUILD_FLAGS[candidate.backend].difference(
            candidate.compiler_flags
        )
        if missing_flags:
            raise RunnerError(
                f"{candidate.backend} build flags omit required values: "
                + ", ".join(sorted(missing_flags))
            )
        flags = " ".join(candidate.compiler_flags)
        return {
            "build_id": f"{candidate.name}-{artifact['sha256'][:12]}",
            "compiler_identity": self.compiler_identity,
            "compiler_and_flags": f"{self.compiler_identity}; {flags}",
            "artifact": artifact,
        }

    def _validation_evidence(
        self,
        template: TrialTemplate,
        config: SweepConfig,
        features: InputFeatures,
        build: Mapping[str, Any],
    ) -> dict[str, Any]:
        manifest_path = config.protocol.validation_manifest
        evidence: dict[str, Any] = {
            "required": config.protocol.correctness_validated,
            "valid": False,
            "path": None,
            "sha256": None,
            "errors": [],
        }
        if manifest_path is None:
            evidence["errors"] = ["no validation manifest configured"]
            return evidence
        description = artifact_description(manifest_path, self.project_root)
        evidence.update(description)
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            evidence["errors"] = [f"cannot parse manifest: {type(error).__name__}: {error}"]
            return evidence
        errors: list[str] = []
        if not isinstance(payload, dict) or payload.get("passed") is not True:
            errors.append("manifest does not state passed=true")
        if payload.get("upstream_url") != OFFICIAL_UPSTREAM_URL:
            errors.append("manifest upstream URL mismatch")
        if payload.get("upstream_git_commit") != OFFICIAL_UPSTREAM_COMMIT:
            errors.append("manifest upstream commit mismatch")
        schema_version = payload.get("schema_version", 1)
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            errors.append(f"unsupported manifest schema_version: {schema_version!r}")
        elif schema_version == 1:
            if payload.get("input_sha256") != features.combined_input_sha256:
                errors.append("manifest input hash mismatch")
            if payload.get("solver") != _solver_identity(template.solver):
                errors.append("manifest solver settings mismatch")
        elif schema_version in {2, 3}:
            validated_inputs = payload.get("validated_inputs")
            matching_inputs: list[Mapping[str, Any]] = []
            if isinstance(validated_inputs, list):
                matching_inputs = [
                    item
                    for item in validated_inputs
                    if isinstance(item, dict)
                    and item.get("input_sha256")
                    == features.combined_input_sha256
                ]
            else:
                errors.append("manifest validated_inputs must be a list")

            if not matching_inputs:
                errors.append("manifest has no matching validated input")
            elif len(matching_inputs) > 1:
                errors.append("manifest has duplicate matching validated inputs")
            else:
                matching_input = matching_inputs[0]
                if matching_input.get("solver") != _solver_identity(template.solver):
                    errors.append("manifest validated input solver settings mismatch")
                manifest_reference = matching_input.get("reference_value")
                reference_is_finite = False
                if (
                    not isinstance(manifest_reference, bool)
                    and isinstance(manifest_reference, (int, float))
                ):
                    try:
                        reference_is_finite = math.isfinite(float(manifest_reference))
                    except (OverflowError, ValueError):
                        reference_is_finite = False
                if not reference_is_finite:
                    errors.append(
                        "manifest validated input reference_value is missing or nonfinite"
                    )
                elif template.workload.reference_value is None:
                    errors.append("workload reference_value is missing")
                elif manifest_reference != template.workload.reference_value:
                    errors.append("manifest validated input reference_value mismatch")
                if schema_version == 3:
                    for field in ("family_id", "molecule", "basis"):
                        if matching_input.get(field) != getattr(
                            template.workload, field
                        ):
                            errors.append(
                                f"manifest validated input {field} mismatch"
                            )
        else:
            errors.append(f"unsupported manifest schema_version: {schema_version!r}")
        candidates = payload.get("candidate_artifacts")
        matching_candidate = False
        if isinstance(candidates, list):
            matching_candidate = any(
                isinstance(item, dict)
                and item.get("backend") == template.candidate.backend
                and item.get("sha256") == build["artifact"].get("sha256")
                for item in candidates
            )
        if not matching_candidate:
            errors.append("manifest has no matching backend artifact hash")
        evidence["errors"] = errors
        evidence["valid"] = not errors
        return evidence

    def _admission_decision(
        self,
        candidate: CandidateConfig,
        memory: SourceMemoryEstimate,
        preflight: Mapping[str, Any],
    ) -> tuple[str | None, str | None]:
        if candidate.backend == "mock":
            override = candidate.estimated_gpu_memory_override_bytes
            if override is None:
                return None, None
            cap = preflight.get("gpu_memory_cap_bytes")
            if not isinstance(cap, int) or override > cap:
                return (
                    "skipped_memory",
                    "mock GPU-memory estimate exceeds admission cap",
                )
            return None, None

        if preflight.get("gpu") is None:
            return "skipped_invalid", "GPU unavailable at preflight"
        if preflight.get("gpu_process_query_ok") is not True:
            return "skipped_invalid", "GPU process query failed at preflight"
        if preflight.get("gpu_idle") is not True:
            return (
                "deferred_gpu_busy",
                "unrelated GPU compute process present",
            )
        physical_cores = self.system_snapshot.get("physical_cores")
        requested_cores = candidate.threads * candidate.mpi_ranks
        if not isinstance(physical_cores, int) or requested_cores > physical_cores:
            return (
                "skipped_invalid",
                f"requested {requested_cores} CPU cores exceeds {physical_cores}",
            )
        host_cap = preflight.get("host_memory_cap_bytes")
        if not isinstance(host_cap, int):
            return "skipped_invalid", "host-memory preflight unavailable"
        required_host = (
            memory.gpu_host_guard_bytes
            if candidate.backend == "gpu"
            else memory.host_guard_bytes
        )
        if required_host > host_cap:
            return (
                "skipped_memory",
                f"host guard {required_host} exceeds admission cap {host_cap}",
            )
        if candidate.backend == "gpu":
            gpu_cap = preflight.get("gpu_memory_cap_bytes")
            if not isinstance(gpu_cap, int):
                return "skipped_invalid", "GPU-memory preflight unavailable"
            if memory.gpu_guard_bytes > gpu_cap:
                return (
                    "skipped_memory",
                    f"GPU guard {memory.gpu_guard_bytes} exceeds cap {gpu_cap}",
                )
        return None, None

    def _artifact_paths(self, trial_id: str) -> dict[str, Path]:
        return {
            "record": self.results_dir / f"{trial_id}.json",
            "stdout": self.logs_dir / f"{trial_id}.stdout.log",
            "stderr": self.logs_dir / f"{trial_id}.stderr.log",
            "resources": self.logs_dir / f"{trial_id}.resources.csv",
        }

    def _record(self, **values: Any) -> dict[str, Any]:
        template: TrialTemplate = values["template"]
        config: SweepConfig = values["config"]
        candidate = template.candidate
        features: InputFeatures = values["features"]
        memory: SourceMemoryEstimate = values["memory"]
        execution: ExecutionResult | None = values["execution"]
        parsed: ParsedSbdOutput | None = values["parsed"]
        paths: dict[str, Path] = values["paths"]
        build: dict[str, Any] = values["build"]
        gpu = self.system_snapshot.get("gpu") or {}
        notes = [
            "Official AMD-HPC/amd-sbd is the enforced primary implementation.",
            (
                "matvec_time_s is null because upstream 'Elapsed time for mult' "
                "is a post-solver matvec."
            ),
        ]
        if config.protocol.purpose in {"test", "correctness"}:
            notes.append(
                f"Protocol purpose is {config.protocol.purpose}; this is not final timing."
            )
        if parsed is not None and parsed.density_bracket_repaired:
            notes.append(
                "Parsed the pinned upstream's known single missing density bracket."
            )
        if values["reference_value"] is None:
            notes.append("No per-trial energy reference was supplied; correct is null.")
        record = {
            "schema_version": values["record_schema_version"],
            "trial_id": values["trial_id"],
            "logical_trial_id": values["logical_trial_id"],
            "logical_identity": values["logical_identity"],
            "attempt_index": values["attempt_index"],
            "timestamp_utc": values["started_timestamp"],
            "finished_timestamp_utc": utc_now(),
            "hostname": self.system_snapshot["hostname"],
            "project_git_commit": self.project_state["commit"],
            "upstream_url": OFFICIAL_UPSTREAM_URL,
            "upstream_git_commit": self.upstream_state["commit"],
            "build_id": build["build_id"],
            "compiler_and_flags": build["compiler_and_flags"],
            "gpu_name": gpu.get("name"),
            "driver_version": gpu.get("driver_version"),
            "cuda_toolkit_version": self.system_snapshot["cuda_toolkit_version"],
            "cpu_model": self.system_snapshot["cpu_model"],
            "physical_cores": self.system_snapshot["physical_cores"],
            "problem_family": template.sweep_name,
            "problem_instance": template.workload.name,
            "input_sha256": features.combined_input_sha256,
            "seed": config.protocol.seed,
            "n_orbitals": features.fcidump.n_orbitals,
            "n_spin_orbitals": 2 * features.fcidump.n_orbitals,
            "n_alpha_strings": features.alpha.count,
            "n_beta_strings": features.beta.count,
            "n_configurations": features.n_configurations,
            "estimated_work": features.method0_work_proxy,
            "estimated_cache_bytes": memory.determinant_cache_bytes,
            "backend": candidate.backend,
            "cpu_threads": candidate.threads,
            "mpi_ranks": candidate.mpi_ranks,
            "bit_length": template.solver.bit_length,
            "shuffle": bool(template.solver.shuffle),
            "cache_mode": _cache_mode(candidate),
            "decomposition": {
                "adet_comm_size": template.solver.adet_comm_size,
                "bdet_comm_size": template.solver.bdet_comm_size,
                "task_comm_size": template.solver.task_comm_size,
                "h_comm_size": template.solver.h_comm_size(candidate.mpi_ranks),
            },
            "warmup_or_measured": template.phase,
            "repetition": template.repetition,
            "command": values["command"],
            "wall_time_s": execution.wall_time_s if execution else None,
            "initialization_time_s": (
                parsed.initialization_time_s if parsed else None
            ),
            "solver_time_s": parsed.solver_time_s if parsed else None,
            "matvec_time_s": None,
            "transfer_time_s": None,
            "iterations": parsed.iteration_records if parsed else None,
            "energy_or_eigenvalue": parsed.energy if parsed else None,
            "reference_value": values["reference_value"],
            "relative_error": values["relative_error"],
            "correct": values["correct"],
            "peak_host_rss_mb": (
                execution.peak_host_rss_mb if execution else None
            ),
            "peak_gpu_memory_mb": (
                execution.peak_gpu_memory_mb if execution else None
            ),
            "timeout": values["status"] == "timeout",
            "oom": values["status"] == "oom",
            "exit_code": execution.exit_code if execution else None,
            "stdout_log": _display_path(paths["stdout"], self.project_root),
            "stderr_log": _display_path(paths["stderr"], self.project_root),
            "notes": notes,
            "status": values["status"],
            "failure_kind": values["failure_kind"],
            "parse_error": values["parse_error"],
            "skip_reason": values["skip_reason"],
            "process_success": values["process_success"],
            "scientific_success": values["scientific_success"],
            "timing_eligible": values["timing_eligible"],
            "input_files": values["input_files"],
            "environment_overrides": _redact_environment(
                values["environment_overrides"]
            ),
            "preflight": values["preflight"],
            "resource_monitoring": {
                "resource_log": _display_path(
                    paths["resources"], self.project_root
                ),
                "host_complete": (
                    execution.host_monitor_complete if execution else None
                ),
                "gpu_complete": (
                    execution.gpu_monitor_complete if execution else None
                ),
                "gpu_process_observed": (
                    execution.gpu_process_observed if execution else None
                ),
                "samples": execution.resource_samples if execution else 0,
                "term_sent": execution.term_sent if execution else False,
                "kill_sent": execution.kill_sent if execution else False,
            },
            "official_upstream_primary": True,
            "project_git_dirty": self.project_state["dirty"],
            "harness_sha256": self.harness_sha256,
            "machine_fingerprint": self.system_snapshot["machine_fingerprint"],
            "compiler_identity": build["compiler_identity"],
            "build_artifact": build["artifact"],
            "run_artifacts": values["run_artifacts"],
            "protocol": {
                "purpose": config.protocol.purpose,
                "warmups": config.protocol.warmups,
                "repetitions": config.protocol.repetitions,
                "timeout_s": config.protocol.timeout_s,
                "correctness_validated": config.protocol.correctness_validated,
            },
            "reference_source": values["reference_source"],
            "validation_evidence": values["validation_evidence"],
            "input_integrity": values["input_integrity"],
            "input_features": features.to_dict(),
            "source_memory_estimate": memory.to_dict(),
            "upstream_output": parsed.to_dict() if parsed else None,
            "launch_error": execution.launch_error if execution else None,
            "termination_signal": (
                execution.termination_signal if execution else None
            ),
        }
        if values["record_schema_version"] == 3:
            record.update(
                {
                    "family_id": template.workload.family_id,
                    "molecule": template.workload.molecule,
                    "basis": template.workload.basis,
                }
            )
        return record


def _process_status(
    execution: ExecutionResult, stderr_path: Path
) -> tuple[str, str | None]:
    if execution.launch_error is not None:
        return "failed", "launch_error"
    if execution.timed_out:
        return "timeout", "timeout"
    if execution.exit_code != 0:
        if _contains_oom_evidence(stderr_path):
            return "oom", "oom_evidence"
        if execution.termination_signal is not None:
            return "failed", f"signal_{execution.termination_signal}"
        return "failed", "nonzero_exit"
    return "success", None


def _contains_oom_evidence(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - (1 << 20)))
            return _OOM_RE.search(stream.read()) is not None
    except OSError:
        return False


def _ensure_artifacts(paths: Mapping[str, Path]) -> None:
    for name in ("stdout", "stderr"):
        path = paths[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            continue
        with path.open("xb") as stream:
            stream.flush()
            os.fsync(stream.fileno())
    resource_path = paths["resources"]
    resource_path.parent.mkdir(parents=True, exist_ok=True)
    if resource_path.exists():
        return
    with resource_path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "elapsed_s",
                "host_rss_mib",
                "gpu_memory_mib",
                "gpu_utilization_pct",
                "gpu_temperature_c",
                "gpu_power_w",
            ]
        )
        stream.flush()
        os.fsync(stream.fileno())


def _safe_preflight() -> dict[str, Any]:
    try:
        preflight = dynamic_preflight()
    except (OSError, RuntimeError, ValueError) as error:
        return {
            "error": f"{type(error).__name__}: {error}",
            "gpu": None,
            "gpu_process_query_ok": False,
            "gpu_compute_processes": None,
            "gpu_idle": None,
            "gpu_memory_cap_bytes": None,
            "host_memory_cap_bytes": None,
        }
    return preflight


def _input_files_match_features(
    input_files: list[dict[str, Any]], features: InputFeatures
) -> bool:
    by_role = {item.get("role"): item for item in input_files}
    expected = {
        "fcidump": (features.fcidump.sha256, features.fcidump.file_bytes),
        "alpha": (features.alpha.sha256, features.alpha.file_bytes),
        "beta": (features.beta.sha256, features.beta.file_bytes),
    }
    return all(
        role in by_role
        and by_role[role].get("sha256") == digest
        and by_role[role].get("size_bytes") == size
        for role, (digest, size) in expected.items()
    )


def _same_input_files(
    first: list[dict[str, Any]], second: list[dict[str, Any]]
) -> bool:
    def semantic(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            (
                {
                    "role": item.get("role"),
                    "sha256": item.get("sha256"),
                    "size_bytes": item.get("size_bytes"),
                }
                for item in items
            ),
            key=lambda item: str(item["role"]),
        )

    return semantic(first) == semantic(second)


def _load_expected_record(
    path: Path,
    trial_id: str,
    logical_trial_id: str,
    logical_identity: Mapping[str, Any],
    expected_schema_version: int,
) -> dict[str, Any]:
    record = load_record(path)
    if record.get("schema_version") != expected_schema_version:
        raise RunnerError(
            f"existing record at current trial ID uses an unexpected schema: {path}"
        )
    if record.get("trial_id") != trial_id:
        raise RunnerError(f"existing record trial_id does not match expectation: {path}")
    if record.get("logical_trial_id") != logical_trial_id:
        raise RunnerError(
            f"existing record logical_trial_id does not match expectation: {path}"
        )
    if canonical_json(record.get("logical_identity")) != canonical_json(
        logical_identity
    ):
        raise RunnerError(f"existing record logical identity does not match: {path}")
    return record


def _record_schema_version(config: SweepConfig) -> int:
    try:
        return _RECORD_SCHEMA_BY_CONFIG_SCHEMA[config.schema_version]
    except KeyError as error:  # pragma: no cover - SweepConfig rejects this first
        raise RunnerError(
            f"unsupported configuration schema_version={config.schema_version}"
        ) from error


def _redact_environment(environment: Mapping[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for name, value in sorted(environment.items()):
        if _SENSITIVE_ENV_RE.search(name):
            digest = hashlib.sha256(value.encode()).hexdigest()[:12]
            redacted[name] = f"<redacted:sha256:{digest}>"
        else:
            redacted[name] = value
    return redacted


def _cache_mode(candidate: CandidateConfig) -> str:
    flags = set(candidate.compiler_flags)
    if "-DUSE_DET_CACHE_OMP" in flags:
        return "persistent-determinant-cache"
    return "not-declared-by-build-flags"


def _solver_identity(solver: SolverConfig) -> dict[str, Any]:
    return {
        "method": solver.method,
        "iteration": solver.iteration,
        "block": solver.block,
        "tolerance": solver.tolerance,
        "max_time": solver.max_time,
        "bit_length": solver.bit_length,
        "shuffle": solver.shuffle,
        "carryover_ratio": solver.carryover_ratio,
        "rdm": solver.rdm,
        "adet_comm_size": solver.adet_comm_size,
        "bdet_comm_size": solver.bdet_comm_size,
        "task_comm_size": solver.task_comm_size,
    }


def _normalize_repo_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    if normalized.startswith("git@github.com:"):
        normalized = "https://github.com/" + normalized.removeprefix(
            "git@github.com:"
        )
    return normalized


def _harness_sha256(project_root: Path) -> str:
    digest = hashlib.sha256(b"autosbd-harness-v2\0")
    source_root = project_root / "src" / "autosbd"
    for path in sorted(source_root.glob("*.py")):
        digest.update(str(path.relative_to(project_root)).encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def _detect_cuda_toolkit_version() -> str | None:
    candidates = [
        Path("/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/cuda/13.2/bin/nvcc"),
        Path("/usr/local/cuda/bin/nvcc"),
    ]
    executable = next((path for path in candidates if path.is_file()), None)
    if executable is None:
        found = shutil.which("nvcc")
        executable = Path(found) if found else None
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"release\s+([0-9.]+)", result.stdout + result.stderr)
    return match.group(1) if match else None


def _detect_nvhpc_compiler_identity() -> str:
    executable = Path(
        "/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/compilers/bin/nvc++"
    )
    if not executable.is_file():
        raise RunnerError("validated NVIDIA HPC SDK 26.5 nvc++ was not found")
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RunnerError(f"cannot query NVHPC compiler identity: {error}") from error
    if result.returncode != 0:
        raise RunnerError("NVHPC compiler identity query failed")
    first_line = next(
        (line.strip() for line in result.stdout.splitlines() if line.strip()), ""
    )
    if "nvc++" not in first_line or "26.5" not in first_line:
        raise RunnerError(f"unexpected NVHPC compiler identity: {first_line!r}")
    return f"{executable}: {first_line}"


def _nvhpc_path_entries() -> list[str]:
    candidates = [
        Path("/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/compilers/bin"),
        Path("/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/comm_libs/mpi/bin"),
    ]
    return [str(path) for path in candidates if path.is_dir()]


def _mpi_launcher() -> str:
    candidates = [
        "/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/comm_libs/mpi/bin/mpirun",
        shutil.which("mpirun"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RunnerError("mpi_ranks > 1 requested but mpirun was not found")


def _display_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root))
    except ValueError:
        return str(path.resolve())
