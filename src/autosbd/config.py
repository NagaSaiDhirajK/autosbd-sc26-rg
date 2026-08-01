"""Strict, deterministic configuration loading for AutoSBD sweeps.

Both supported versions expose only the validated Layer-A AMD configuration:
matrix-free method 0, no RDM calculation, one MPI rank for GPU candidates, and
explicit CPU thread candidates.  Version 2 additionally requires scientific
family metadata on every workload.  Mock candidates exist solely for tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


CONFIG_SCHEMA_VERSION = 2
DEFAULT_CONFIG_SCHEMA_VERSION = 1
SUPPORTED_CONFIG_SCHEMA_VERSIONS = frozenset({1, CONFIG_SCHEMA_VERSION})
VALID_BACKENDS = frozenset({"cpu", "gpu", "mock"})
VALID_PHASES = frozenset({"warmup", "measured"})
VALID_PROTOCOL_PURPOSES = frozenset({"test", "correctness", "pilot", "final"})
FAMILY_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class ConfigError(ValueError):
    """Raised when a sweep configuration is malformed or unsupported."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


@dataclass(frozen=True)
class WorkloadConfig:
    """One authentic SBD input set with resolved and source-level path names."""

    name: str
    fcidump: Path
    adetfile: Path
    bdetfile: Path | None = None
    reference_value: float | None = None
    reference_source: str | None = None
    fcidump_source: str | None = field(default=None, repr=False, compare=False)
    adetfile_source: str | None = field(default=None, repr=False, compare=False)
    bdetfile_source: str | None = field(default=None, repr=False, compare=False)
    family_id: str | None = None
    molecule: str | None = None
    basis: str | None = None

    def __post_init__(self) -> None:
        _validate_name(self.name, "workload.name")
        original_fcidump = str(self.fcidump)
        original_adetfile = str(self.adetfile)
        original_bdetfile = None if self.bdetfile is None else str(self.bdetfile)
        object.__setattr__(self, "fcidump", _existing_file(self.fcidump, "workload.fcidump"))
        object.__setattr__(self, "adetfile", _existing_file(self.adetfile, "workload.adetfile"))
        if self.bdetfile is not None:
            object.__setattr__(
                self, "bdetfile", _existing_file(self.bdetfile, "workload.bdetfile")
            )
        if self.reference_value is not None:
            object.__setattr__(
                self,
                "reference_value",
                _require_finite_float(self.reference_value, "workload.reference_value"),
            )
            if self.reference_source is None:
                raise ConfigError(
                    "workload.reference_source is required when reference_value is set"
                )
        if self.reference_source is not None:
            _require_nonempty_string(
                self.reference_source, "workload.reference_source"
            )
        if self.fcidump_source is None:
            object.__setattr__(self, "fcidump_source", original_fcidump)
        if self.adetfile_source is None:
            object.__setattr__(self, "adetfile_source", original_adetfile)
        if self.bdetfile is not None and self.bdetfile_source is None:
            object.__setattr__(self, "bdetfile_source", original_bdetfile)

        for field_name in ("fcidump_source", "adetfile_source", "bdetfile_source"):
            value = getattr(self, field_name)
            if value is not None:
                _require_nonempty_string(value, f"workload.{field_name}")

        metadata = (self.family_id, self.molecule, self.basis)
        if any(value is not None for value in metadata) and not all(
            value is not None for value in metadata
        ):
            raise ConfigError(
                "workload family_id, molecule, and basis must be provided together"
            )
        if self.family_id is not None:
            family_id = _require_trimmed_nonempty_string(
                self.family_id, "workload.family_id"
            )
            if FAMILY_ID_RE.fullmatch(family_id) is None:
                raise ConfigError(
                    "workload.family_id must be a lowercase ASCII slug"
                )
            _require_trimmed_nonempty_string(self.molecule, "workload.molecule")
            _require_trimmed_nonempty_string(self.basis, "workload.basis")

    @property
    def semantic_input_names(self) -> Mapping[str, str]:
        """Return caller-written path names without changing the resolved paths."""

        names = {
            "fcidump": self.fcidump_source,
            "adetfile": self.adetfile_source,
        }
        if self.bdetfile_source is not None:
            names["bdetfile"] = self.bdetfile_source
        return MappingProxyType({key: str(value) for key, value in names.items()})


@dataclass(frozen=True)
class CandidateConfig:
    """One backend/build/thread candidate.

    Real CPU/GPU candidates use ``executable``.  Mock candidates instead carry
    a complete ``mock_argv`` and are forbidden from entering a scientific sweep.
    """

    name: str
    backend: str
    executable: Path | None = None
    mock_argv: tuple[str, ...] = ()
    threads: int = 1
    mpi_ranks: int = 1
    environment: Mapping[str, str] = field(default_factory=dict)
    compiler_flags: tuple[str, ...] = ()
    estimated_gpu_memory_override_bytes: int | None = None
    executable_source: str | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_name(self.name, "candidate.name")
        backend = _require_nonempty_string(self.backend, f"candidate {self.name}.backend")
        object.__setattr__(self, "backend", backend)
        if backend not in VALID_BACKENDS:
            raise ConfigError(
                f"candidate {self.name!r} backend must be one of "
                f"{sorted(VALID_BACKENDS)}, got {backend!r}"
            )
        object.__setattr__(
            self, "threads", _require_int(self.threads, f"candidate {self.name}.threads", 1)
        )
        object.__setattr__(
            self,
            "mpi_ranks",
            _require_int(self.mpi_ranks, f"candidate {self.name}.mpi_ranks", 1),
        )

        mock_argv = _string_tuple(self.mock_argv, f"candidate {self.name}.mock_argv")
        compiler_flags = _string_tuple(
            self.compiler_flags, f"candidate {self.name}.compiler_flags", allow_empty=True
        )
        environment = _environment_mapping(
            self.environment, f"candidate {self.name}.environment"
        )
        object.__setattr__(self, "mock_argv", mock_argv)
        object.__setattr__(self, "compiler_flags", compiler_flags)
        object.__setattr__(self, "environment", MappingProxyType(environment))

        if backend == "mock":
            if self.executable is not None:
                raise ConfigError(
                    f"mock candidate {self.name!r} must use mock_argv, not executable"
                )
            if self.executable_source is not None:
                raise ConfigError(
                    f"mock candidate {self.name!r} cannot define executable_source"
                )
            if not mock_argv:
                raise ConfigError(f"mock candidate {self.name!r} requires nonempty mock_argv")
        else:
            if self.executable is None:
                raise ConfigError(f"{self.backend} candidate {self.name!r} requires executable")
            if mock_argv:
                raise ConfigError(
                    f"{self.backend} candidate {self.name!r} cannot define mock_argv"
                )
            original_executable = str(self.executable)
            object.__setattr__(
                self,
                "executable",
                _existing_file(self.executable, f"candidate {self.name}.executable"),
            )
            if self.executable_source is None:
                object.__setattr__(self, "executable_source", original_executable)
            else:
                _require_nonempty_string(
                    self.executable_source, f"candidate {self.name}.executable_source"
                )

        if backend == "gpu" and self.mpi_ranks != 1:
            raise ConfigError(
                f"Layer-A GPU candidate {self.name!r} must use exactly one MPI rank"
            )

        override = self.estimated_gpu_memory_override_bytes
        if override is not None:
            override = _require_int(
                override,
                f"candidate {self.name}.estimated_gpu_memory_override_bytes",
                0,
            )
            if backend != "mock":
                raise ConfigError(
                    "estimated_gpu_memory_override_bytes is restricted to mock candidates"
                )
            object.__setattr__(self, "estimated_gpu_memory_override_bytes", override)

    @property
    def base_argv(self) -> tuple[str, ...]:
        """Return the executable prefix without workload or solver arguments."""

        if self.backend == "mock":
            return self.mock_argv
        assert self.executable is not None
        return (str(self.executable),)


@dataclass(frozen=True)
class SolverConfig:
    """Whitelisted AMD SBD solver settings for supported config schemas."""

    method: int = 0
    iteration: int = 1
    block: int = 10
    tolerance: float = 1.0e-4
    max_time: float = 86400.0
    bit_length: int = 20
    shuffle: int = 0
    carryover_ratio: float = 0.5
    rdm: int = 0
    adet_comm_size: int = 1
    bdet_comm_size: int = 1
    task_comm_size: int = 1

    def __post_init__(self) -> None:
        for field_name in (
            "method",
            "iteration",
            "block",
            "bit_length",
            "shuffle",
            "rdm",
            "adet_comm_size",
            "bdet_comm_size",
            "task_comm_size",
        ):
            minimum = 1 if field_name in {
                "iteration",
                "block",
                "bit_length",
                "adet_comm_size",
                "bdet_comm_size",
                "task_comm_size",
            } else None
            object.__setattr__(
                self,
                field_name,
                _require_int(getattr(self, field_name), f"solver.{field_name}", minimum),
            )
        object.__setattr__(
            self, "tolerance", _require_positive_float(self.tolerance, "solver.tolerance")
        )
        object.__setattr__(
            self, "max_time", _require_positive_float(self.max_time, "solver.max_time")
        )
        object.__setattr__(
            self,
            "carryover_ratio",
            _require_positive_float(self.carryover_ratio, "solver.carryover_ratio"),
        )

        if self.method != 0:
            raise ConfigError("supported config schemas permit only AMD solver method=0")
        if self.rdm != 0:
            raise ConfigError("supported config schemas require rdm=0")
        if self.shuffle not in (0, 1):
            raise ConfigError("solver.shuffle must be exactly 0 or 1")
        if self.carryover_ratio > 1.0:
            raise ConfigError("solver.carryover_ratio must be in the interval (0, 1]")
        if self.bit_length > 64:
            raise ConfigError("solver.bit_length must not exceed 64")

    @property
    def communicator_product(self) -> int:
        return self.adet_comm_size * self.bdet_comm_size * self.task_comm_size

    def h_comm_size(self, mpi_ranks: int) -> int:
        """Return the derived communicator size after validating divisibility."""

        ranks = _require_int(mpi_ranks, "mpi_ranks", 1)
        product = self.communicator_product
        if ranks % product:
            raise ConfigError(
                f"communicator product {product} does not divide mpi_ranks={ranks}"
            )
        return ranks // product

    def amd_cli_args(self) -> tuple[str, ...]:
        """Return only CLI options parsed by the pinned AMD source.

        In particular, this deliberately never emits the silently ignored
        ``--init`` option.
        """

        return (
            "--method",
            str(self.method),
            "--iteration",
            str(self.iteration),
            "--block",
            str(self.block),
            "--tolerance",
            _format_float(self.tolerance),
            "--max_time",
            _format_float(self.max_time),
            "--bit_length",
            str(self.bit_length),
            "--shuffle",
            str(self.shuffle),
            "--carryover_ratio",
            _format_float(self.carryover_ratio),
            "--rdm",
            str(self.rdm),
            "--adet_comm_size",
            str(self.adet_comm_size),
            "--bdet_comm_size",
            str(self.bdet_comm_size),
            "--task_comm_size",
            str(self.task_comm_size),
        )


@dataclass(frozen=True)
class ProtocolConfig:
    """Warmup, repetition, timeout, and deterministic order controls."""

    warmups: int = 1
    repetitions: int = 3
    timeout_s: float = 300.0
    seed: int = 1729
    purpose: str = "test"
    correctness_validated: bool = False
    validation_manifest: Path | None = None
    validation_manifest_source: str | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "warmups", _require_int(self.warmups, "protocol.warmups", 0)
        )
        object.__setattr__(
            self,
            "repetitions",
            _require_int(self.repetitions, "protocol.repetitions", 1),
        )
        object.__setattr__(
            self, "timeout_s", _require_positive_float(self.timeout_s, "protocol.timeout_s")
        )
        object.__setattr__(self, "seed", _require_int(self.seed, "protocol.seed", 0))
        if self.purpose not in VALID_PROTOCOL_PURPOSES:
            raise ConfigError(
                "protocol.purpose must be one of "
                f"{sorted(VALID_PROTOCOL_PURPOSES)}, got {self.purpose!r}"
            )
        if type(self.correctness_validated) is not bool:
            raise ConfigError("protocol.correctness_validated must be a boolean")
        if self.validation_manifest is not None:
            original = str(self.validation_manifest)
            object.__setattr__(
                self,
                "validation_manifest",
                _existing_file(
                    self.validation_manifest, "protocol.validation_manifest"
                ),
            )
            if self.validation_manifest_source is None:
                object.__setattr__(self, "validation_manifest_source", original)
        if self.correctness_validated and self.validation_manifest is None:
            raise ConfigError(
                "protocol.correctness_validated=true requires validation_manifest"
            )


@dataclass(frozen=True)
class TrialTemplate:
    """A deterministic workload/candidate invocation before attempt identity."""

    sweep_name: str
    workload: WorkloadConfig
    candidate: CandidateConfig
    solver: SolverConfig
    phase: str
    repetition: int

    def __post_init__(self) -> None:
        _validate_name(self.sweep_name, "trial.sweep_name")
        if self.phase not in VALID_PHASES:
            raise ConfigError(f"trial.phase must be one of {sorted(VALID_PHASES)}")
        object.__setattr__(
            self, "repetition", _require_int(self.repetition, "trial.repetition", 0)
        )

    @property
    def warmup_or_measured(self) -> str:
        return self.phase

    @property
    def is_warmup(self) -> bool:
        return self.phase == "warmup"

    @property
    def semantic_key(self) -> tuple[str, str, str, int]:
        return (self.workload.name, self.candidate.name, self.phase, self.repetition)


@dataclass(frozen=True)
class SweepConfig:
    """Validated sweep configuration and deterministic trial expansion."""

    name: str
    workloads: tuple[WorkloadConfig, ...]
    candidates: tuple[CandidateConfig, ...]
    solver: SolverConfig = field(default_factory=SolverConfig)
    protocol: ProtocolConfig = field(default_factory=ProtocolConfig)
    schema_version: int = DEFAULT_CONFIG_SCHEMA_VERSION
    source_path: Path | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_name(self.name, "sweep.name")
        object.__setattr__(
            self,
            "schema_version",
            _require_int(
                self.schema_version, "schema_version", DEFAULT_CONFIG_SCHEMA_VERSION
            ),
        )
        if self.schema_version not in SUPPORTED_CONFIG_SCHEMA_VERSIONS:
            raise ConfigError(
                f"unsupported schema_version={self.schema_version}; "
                f"expected one of {sorted(SUPPORTED_CONFIG_SCHEMA_VERSIONS)}"
            )
        workloads = tuple(self.workloads)
        candidates = tuple(self.candidates)
        if not workloads:
            raise ConfigError("sweep requires at least one workload")
        if not candidates:
            raise ConfigError("sweep requires at least one candidate")
        if not all(isinstance(item, WorkloadConfig) for item in workloads):
            raise ConfigError("sweep.workloads must contain WorkloadConfig values")
        if not all(isinstance(item, CandidateConfig) for item in candidates):
            raise ConfigError("sweep.candidates must contain CandidateConfig values")
        _reject_duplicate_names(workloads, "workload")
        _reject_duplicate_names(candidates, "candidate")
        if self.schema_version == 1:
            annotated = [item.name for item in workloads if item.family_id is not None]
            if annotated:
                raise ConfigError(
                    "configuration schema v1 cannot define workload family metadata: "
                    + ", ".join(annotated)
                )
        else:
            missing_metadata = [
                item.name for item in workloads if item.family_id is None
            ]
            if missing_metadata:
                raise ConfigError(
                    "configuration schema v2 requires family_id, molecule, and basis "
                    "for workloads: "
                    + ", ".join(missing_metadata)
                )
            family_metadata: dict[str, tuple[str, str]] = {}
            for workload in workloads:
                assert workload.family_id is not None
                assert workload.molecule is not None
                assert workload.basis is not None
                metadata = (workload.molecule, workload.basis)
                previous = family_metadata.setdefault(workload.family_id, metadata)
                if previous != metadata:
                    raise ConfigError(
                        f"family_id {workload.family_id!r} has inconsistent "
                        "molecule/basis metadata"
                    )
        if not isinstance(self.solver, SolverConfig):
            raise ConfigError("sweep.solver must be a SolverConfig")
        if not isinstance(self.protocol, ProtocolConfig):
            raise ConfigError("sweep.protocol must be a ProtocolConfig")

        for candidate in candidates:
            try:
                self.solver.h_comm_size(candidate.mpi_ranks)
            except ConfigError as error:
                raise ConfigError(f"candidate {candidate.name!r}: {error}") from error

        object.__setattr__(self, "workloads", workloads)
        object.__setattr__(self, "candidates", candidates)
        if self.source_path is not None:
            object.__setattr__(self, "source_path", Path(self.source_path).resolve())

    def trial_templates(self, *, randomize: bool = True) -> tuple[TrialTemplate, ...]:
        """Expand warmup and measured trials in a reproducible order.

        Workloads retain configuration order.  Candidate order is randomized
        independently within each workload/phase/repetition group using SHA-256,
        making it stable across Python versions and unaffected by earlier groups.
        """

        if type(randomize) is not bool:
            raise ConfigError("randomize must be a boolean")
        templates: list[TrialTemplate] = []
        phases = (
            ("warmup", self.protocol.warmups),
            ("measured", self.protocol.repetitions),
        )
        for phase, count in phases:
            for repetition in range(count):
                for workload in self.workloads:
                    candidates: Sequence[CandidateConfig] = self.candidates
                    if randomize:
                        candidates = tuple(
                            sorted(
                                candidates,
                                key=lambda candidate: _random_order_key(
                                    self.protocol.seed,
                                    self.name,
                                    workload.name,
                                    phase,
                                    repetition,
                                    candidate.name,
                                ),
                            )
                        )
                    templates.extend(
                        TrialTemplate(
                            sweep_name=self.name,
                            workload=workload,
                            candidate=candidate,
                            solver=self.solver,
                            phase=phase,
                            repetition=repetition,
                        )
                        for candidate in candidates
                    )
        return tuple(templates)

    def enumerate_trials(self, *, randomize: bool = True) -> tuple[TrialTemplate, ...]:
        """Alias for :meth:`trial_templates` for sweep-runner call sites."""

        return self.trial_templates(randomize=randomize)


def load_sweep_config(path: str | Path) -> SweepConfig:
    """Load and strictly validate a supported YAML sweep configuration."""

    config_path = Path(path).resolve()
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"cannot read configuration {config_path}: {error}") from error
    try:
        loaded = yaml.load(text, Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as error:
        raise ConfigError(f"invalid YAML in {config_path}: {error}") from error

    root = _strict_mapping(
        loaded,
        "configuration",
        allowed={"schema_version", "name", "workloads", "candidates", "solver", "protocol"},
        required={"workloads", "candidates"},
    )
    schema_version = root.get("schema_version", DEFAULT_CONFIG_SCHEMA_VERSION)
    schema_version = _require_int(
        schema_version, "schema_version", DEFAULT_CONFIG_SCHEMA_VERSION
    )
    if schema_version not in SUPPORTED_CONFIG_SCHEMA_VERSIONS:
        raise ConfigError(
            f"unsupported schema_version={schema_version}; expected one of "
            f"{sorted(SUPPORTED_CONFIG_SCHEMA_VERSIONS)}"
        )
    name = root.get("name", config_path.stem)
    _validate_name(name, "sweep.name")

    workloads_data = _require_list(root["workloads"], "workloads")
    candidates_data = _require_list(root["candidates"], "candidates")
    workloads = tuple(
        _load_workload(item, config_path.parent, index, schema_version)
        for index, item in enumerate(workloads_data)
    )
    candidates = tuple(
        _load_candidate(item, config_path.parent, index)
        for index, item in enumerate(candidates_data)
    )
    solver = _load_solver(root.get("solver", {}))
    protocol = _load_protocol(root.get("protocol", {}), config_path.parent)
    return SweepConfig(
        name=name,
        workloads=workloads,
        candidates=candidates,
        solver=solver,
        protocol=protocol,
        schema_version=schema_version,
        source_path=config_path,
    )


def enumerate_trials(
    config: SweepConfig, *, randomize: bool = True
) -> tuple[TrialTemplate, ...]:
    """Expand a validated sweep through a small functional API."""

    if not isinstance(config, SweepConfig):
        raise ConfigError("config must be a SweepConfig")
    return config.trial_templates(randomize=randomize)


def _load_workload(
    value: Any, base_dir: Path, index: int, schema_version: int
) -> WorkloadConfig:
    context = f"workloads[{index}]"
    metadata_keys = {"family_id", "molecule", "basis"}
    allowed = {
        "name",
        "fcidump",
        "adetfile",
        "bdetfile",
        "reference_value",
        "reference_source",
    }
    required = {"name", "fcidump", "adetfile"}
    if schema_version == 2:
        allowed |= metadata_keys
        required |= metadata_keys
    data = _strict_mapping(
        value,
        context,
        allowed=allowed,
        required=required,
    )
    fcidump_source = _require_nonempty_string(data["fcidump"], f"{context}.fcidump")
    adetfile_source = _require_nonempty_string(data["adetfile"], f"{context}.adetfile")
    bdetfile_source = data.get("bdetfile")
    if bdetfile_source is not None:
        bdetfile_source = _require_nonempty_string(
            bdetfile_source, f"{context}.bdetfile"
        )
    return WorkloadConfig(
        name=data["name"],
        fcidump=_resolve_config_path(fcidump_source, base_dir),
        adetfile=_resolve_config_path(adetfile_source, base_dir),
        bdetfile=(
            _resolve_config_path(bdetfile_source, base_dir)
            if bdetfile_source is not None
            else None
        ),
        fcidump_source=fcidump_source,
        adetfile_source=adetfile_source,
        bdetfile_source=bdetfile_source,
        reference_value=data.get("reference_value"),
        reference_source=data.get("reference_source"),
        family_id=data.get("family_id"),
        molecule=data.get("molecule"),
        basis=data.get("basis"),
    )


def _load_candidate(value: Any, base_dir: Path, index: int) -> CandidateConfig:
    context = f"candidates[{index}]"
    data = _strict_mapping(
        value,
        context,
        allowed={
            "name",
            "backend",
            "executable",
            "mock_argv",
            "threads",
            "mpi_ranks",
            "environment",
            "compiler_flags",
            "estimated_gpu_memory_override_bytes",
        },
        required={"name", "backend"},
    )
    executable_source = data.get("executable")
    if executable_source is not None:
        executable_source = _require_nonempty_string(
            executable_source, f"{context}.executable"
        )
    executable = (
        _resolve_config_path(executable_source, base_dir)
        if executable_source is not None
        else None
    )
    return CandidateConfig(
        name=data["name"],
        backend=data["backend"],
        executable=executable,
        mock_argv=data.get("mock_argv", ()),
        threads=data.get("threads", 1),
        mpi_ranks=data.get("mpi_ranks", 1),
        environment=data.get("environment", {}),
        compiler_flags=data.get("compiler_flags", ()),
        estimated_gpu_memory_override_bytes=data.get(
            "estimated_gpu_memory_override_bytes"
        ),
        executable_source=executable_source,
    )


def _load_solver(value: Any) -> SolverConfig:
    data = _strict_mapping(
        value,
        "solver",
        allowed={
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
        },
    )
    return SolverConfig(**data)


def _load_protocol(value: Any, base_dir: Path) -> ProtocolConfig:
    data = _strict_mapping(
        value,
        "protocol",
        allowed={
            "warmups",
            "repetitions",
            "timeout_s",
            "seed",
            "purpose",
            "correctness_validated",
            "validation_manifest",
        },
    )
    manifest_source = data.get("validation_manifest")
    if manifest_source is not None:
        manifest_source = _require_nonempty_string(
            manifest_source, "protocol.validation_manifest"
        )
        data["validation_manifest"] = _resolve_config_path(
            manifest_source, base_dir
        )
        data["validation_manifest_source"] = manifest_source
    return ProtocolConfig(**data)


def _strict_mapping(
    value: Any,
    context: str,
    *,
    allowed: set[str],
    required: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{context} must be a mapping")
    non_string_keys = [key for key in value if not isinstance(key, str)]
    if non_string_keys:
        raise ConfigError(f"{context} keys must be strings: {non_string_keys!r}")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ConfigError(f"{context} contains unknown keys: {unknown}")
    missing = sorted((required or set()) - set(value))
    if missing:
        raise ConfigError(f"{context} is missing required keys: {missing}")
    return dict(value)


def _require_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigError(f"{context} must be a list")
    return value


def _require_nonempty_string(value: Any, context: str) -> str:
    converted = _require_string(value, context)
    if not converted.strip():
        raise ConfigError(f"{context} must be a nonempty string")
    return converted


def _require_trimmed_nonempty_string(value: Any, context: str) -> str:
    converted = _require_nonempty_string(value, context)
    if converted != converted.strip():
        raise ConfigError(f"{context} must not contain surrounding whitespace")
    return converted


def _require_string(value: Any, context: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{context} must be a string")
    if "\0" in value:
        raise ConfigError(f"{context} cannot contain a NUL byte")
    return value


def _validate_name(value: Any, context: str) -> None:
    _require_nonempty_string(value, context)


def _require_int(value: Any, context: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{context} must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{context} must be at least {minimum}")
    return value


def _require_positive_float(value: Any, context: str) -> float:
    if isinstance(value, bool):
        raise ConfigError(f"{context} must be a finite positive number")
    try:
        converted = float(value)
    except (TypeError, ValueError) as error:
        raise ConfigError(f"{context} must be a finite positive number") from error
    if not math.isfinite(converted) or converted <= 0:
        raise ConfigError(f"{context} must be a finite positive number")
    return converted


def _require_finite_float(value: Any, context: str) -> float:
    if isinstance(value, bool):
        raise ConfigError(f"{context} must be a finite number")
    try:
        converted = float(value)
    except (TypeError, ValueError) as error:
        raise ConfigError(f"{context} must be a finite number") from error
    if not math.isfinite(converted):
        raise ConfigError(f"{context} must be a finite number")
    return converted


def _string_tuple(value: Any, context: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ConfigError(f"{context} must be a list of strings")
    converted = tuple(value)
    if not allow_empty and not converted:
        return ()
    for index, item in enumerate(converted):
        _require_nonempty_string(item, f"{context}[{index}]")
    return converted


def _environment_mapping(value: Any, context: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{context} must be a mapping of strings")
    result: dict[str, str] = {}
    for key, item in value.items():
        key = _require_nonempty_string(key, f"{context} key")
        item = _require_string(item, f"{context}[{key!r}]")
        if "=" in key:
            raise ConfigError(f"{context} key cannot contain '=': {key!r}")
        result[key] = item
    return dict(sorted(result.items()))


def _existing_file(path: str | Path, context: str) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ConfigError(f"{context} does not resolve to an existing file: {path}") from error
    if not resolved.is_file():
        raise ConfigError(f"{context} is not a file: {resolved}")
    return resolved


def _resolve_config_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def _reject_duplicate_names(values: Sequence[Any], kind: str) -> None:
    names = [value.name for value in values]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ConfigError(f"duplicate {kind} names: {duplicates}")


def _random_order_key(
    seed: int,
    sweep_name: str,
    workload_name: str,
    phase: str,
    repetition: int,
    candidate_name: str,
) -> bytes:
    fields = (
        "autosbd-order-v1",
        str(seed),
        sweep_name,
        workload_name,
        phase,
        str(repetition),
        candidate_name,
    )
    return hashlib.sha256("\0".join(fields).encode("utf-8")).digest()


def _format_float(value: float) -> str:
    return format(value, ".17g")


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "DEFAULT_CONFIG_SCHEMA_VERSION",
    "SUPPORTED_CONFIG_SCHEMA_VERSIONS",
    "CandidateConfig",
    "ConfigError",
    "ProtocolConfig",
    "SolverConfig",
    "SweepConfig",
    "TrialTemplate",
    "WorkloadConfig",
    "enumerate_trials",
    "load_sweep_config",
]
