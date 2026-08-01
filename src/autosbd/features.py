"""Pre-execution features and conservative memory guards for AMD SBD.

The formulas in this module describe the arrays visible in the pinned
``AMD-HPC/amd-sbd`` method-0 source.  They are deliberately separated from
measured memory: allocator, OpenMP, MPI, BLAS, CUDA, and compiler-runtime
overheads are covered by a padded admission guard rather than presented as
source-exact predictions.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


BYTES_PER_DOUBLE = 8
BYTES_PER_SIZE_T = 8
MIB = 1 << 20
GIB = 1 << 30
MEMORY_GUARD_BASE_BYTES = 512 * MIB
MEMORY_GUARD_ALIGNMENT_BYTES = 64 * MIB
GPU_VRAM_CAP_BYTES = 20 * GIB
DEFAULT_CONNECTIVITY_PAIR_LIMIT = 1_000_000

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_HEADER_FIELD_RE = re.compile(r"\b([A-Z][A-Z0-9_]*)\s*=", re.IGNORECASE)
_INTEGER_RE = re.compile(r"[-+]?\d+")
_BINARY_RE = re.compile(r"[01]+")


class FeatureError(ValueError):
    """Raised when an input cannot yield trustworthy pre-execution features."""


class UnsupportedGuardConfiguration(FeatureError):
    """Raised for a solver mode not audited by the version-1 memory guard."""


@dataclass(frozen=True)
class FcidumpFeatures:
    path: str
    file_bytes: int
    sha256: str
    n_orbitals: int
    n_electrons: int
    ms2: int
    isym: int
    orbsym: tuple[int, ...]
    integral_records: int
    core_integrals: int
    one_electron_integrals: int
    two_electron_integrals: int
    exact_zero_integrals: int
    sum_abs_integrals: float
    max_abs_integral: float
    compact_two_electron_slots: int
    two_electron_fill_density: float
    source_integral_doubles: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["orbsym"] = list(self.orbsym)
        return payload


@dataclass(frozen=True)
class DeterminantFeatures:
    path: str
    file_bytes: int
    sha256: str
    count: int
    unique_count: int
    bit_length: int
    occupancy_min: int
    occupancy_max: int
    occupancy_mean: float
    occupancy_variance: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConnectivityStats:
    determinants: int
    unordered_pair_comparisons: int
    directed_single_edges: int
    directed_double_edges: int
    single_degree_min: int
    single_degree_max: int
    single_degree_mean: float
    double_degree_min: int
    double_degree_max: int
    double_degree_mean: float
    single_edge_density: float
    double_edge_density: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConnectivityFeatures:
    pair_comparisons: int
    alpha: ConnectivityStats
    beta: ConnectivityStats

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InputFeatures:
    fcidump: FcidumpFeatures
    alpha: DeterminantFeatures
    beta: DeterminantFeatures
    beta_reuses_alpha: bool
    combined_input_sha256: str
    n_configurations: int
    log1p_n_configurations: float
    connectivity: ConnectivityFeatures | None
    connectivity_pair_limit: int
    method0_work_proxy: int | None
    log1p_method0_work_proxy: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceMemoryEstimate:
    """Known array payloads plus padded CPU-host/GPU-host/device guards."""

    input_envelope_bytes: int
    integral_bytes: int
    determinant_cache_bytes: int
    determinant_cache_temporary_bytes: int
    helper_host_bytes: int
    davidson_bytes: int
    gpu_flat_integral_host_bytes: int
    gpu_helper_max_bytes: int
    gpu_task_temporary_bytes: int
    host_known_bytes: int
    gpu_host_known_bytes: int
    gpu_known_bytes: int
    host_guard_bytes: int
    gpu_host_guard_bytes: int
    gpu_guard_bytes: int
    local_configurations: int
    helper_is_upper_bound: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _ParsedDeterminants:
    features: DeterminantFeatures
    masks: tuple[int, ...]


def parse_fcidump(path: Path) -> FcidumpFeatures:
    """Stream-parse an FCIDUMP namelist and its integral records.

    The file is hashed while it is parsed; it is never loaded wholesale.
    Integral records must use the conventional core ``0 0 0 0``, one-body
    ``i j 0 0``, or two-body ``i j k l`` index shapes.
    """

    input_path = Path(path)
    digest = hashlib.sha256()
    file_bytes = 0
    header_fragments: list[str] = []
    header_started = False
    header_finished = False
    header: dict[str, int | tuple[int, ...]] | None = None

    records = 0
    core = 0
    one_electron = 0
    two_electron = 0
    exact_zeros = 0
    sum_abs = 0.0
    sum_compensation = 0.0
    max_abs = 0.0

    with input_path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            digest.update(raw_line)
            file_bytes += len(raw_line)
            try:
                line = raw_line.decode("ascii")
            except UnicodeDecodeError as error:
                raise FeatureError(
                    f"FCIDUMP is not ASCII at {input_path}:{line_number}"
                ) from error

            if not header_finished:
                stripped = line.strip()
                if not header_started:
                    if not stripped:
                        continue
                    if not stripped.upper().startswith("&FCI"):
                        raise FeatureError(
                            f"FCIDUMP must begin with an &FCI namelist: "
                            f"{input_path}:{line_number}"
                        )
                    header_started = True

                fragment, ended = _split_header_terminator(line)
                header_fragments.append(fragment)
                if ended:
                    header_finished = True
                    header = _parse_fcidump_header("".join(header_fragments), input_path)
                continue

            if not line.strip():
                continue
            assert header is not None
            value, indices = _parse_integral_record(
                line, input_path, line_number, int(header["NORB"])
            )
            records += 1
            magnitude = abs(value)
            # Neumaier summation preserves a stable streaming sum without retaining values.
            updated = sum_abs + magnitude
            if abs(sum_abs) >= magnitude:
                sum_compensation += (sum_abs - updated) + magnitude
            else:
                sum_compensation += (magnitude - updated) + sum_abs
            sum_abs = updated
            max_abs = max(max_abs, magnitude)
            if value == 0.0:
                exact_zeros += 1

            i, j, k, l = indices
            if i == j == k == l == 0:
                core += 1
            elif i > 0 and j > 0 and k == l == 0:
                one_electron += 1
            elif i > 0 and j > 0 and k > 0 and l > 0:
                two_electron += 1
            else:
                raise FeatureError(
                    f"Invalid FCIDUMP index shape at {input_path}:{line_number}: "
                    f"{i} {j} {k} {l}"
                )

    if not header_started:
        raise FeatureError(f"FCIDUMP is empty or lacks an &FCI namelist: {input_path}")
    if not header_finished or header is None:
        raise FeatureError(f"Unterminated &FCI namelist: {input_path}")
    if records == 0:
        raise FeatureError(f"FCIDUMP contains no integral records: {input_path}")

    n_orbitals = int(header["NORB"])
    pair_slots = n_orbitals * (n_orbitals + 1) // 2
    compact_two_electron_slots = pair_slots * (pair_slots + 1) // 2
    source_integral_doubles = 6 * n_orbitals * n_orbitals + compact_two_electron_slots

    return FcidumpFeatures(
        path=str(input_path),
        file_bytes=file_bytes,
        sha256=digest.hexdigest(),
        n_orbitals=n_orbitals,
        n_electrons=int(header["NELEC"]),
        ms2=int(header["MS2"]),
        isym=int(header["ISYM"]),
        orbsym=tuple(header["ORBSYM"]),  # type: ignore[arg-type]
        integral_records=records,
        core_integrals=core,
        one_electron_integrals=one_electron,
        two_electron_integrals=two_electron,
        exact_zero_integrals=exact_zeros,
        sum_abs_integrals=sum_abs + sum_compensation,
        max_abs_integral=max_abs,
        compact_two_electron_slots=compact_two_electron_slots,
        two_electron_fill_density=two_electron / compact_two_electron_slots,
        source_integral_doubles=source_integral_doubles,
    )


def parse_determinants(
    path: Path,
    *,
    expected_bit_length: int | None = None,
) -> DeterminantFeatures:
    """Parse unique fixed-length binary determinant strings."""

    return _parse_determinants(path, expected_bit_length=expected_bit_length).features


def extract_input_features(
    fcidump_path: Path,
    alpha_path: Path,
    beta_path: Path | None = None,
    *,
    max_connectivity_pairs: int = DEFAULT_CONNECTIVITY_PAIR_LIMIT,
) -> InputFeatures:
    """Extract input-only features without launching or timing SBD.

    Exact pair connectivity is computed only when the combined number of
    unordered alpha and beta comparisons is at or below
    ``max_connectivity_pairs``.  Otherwise connectivity and its dependent work
    proxy are ``None``; sampled estimates are intentionally not used by the
    safety path.
    """

    _require_nonnegative_int("max_connectivity_pairs", max_connectivity_pairs)
    fcidump = parse_fcidump(fcidump_path)
    alpha_parsed = _parse_determinants(
        alpha_path, expected_bit_length=fcidump.n_orbitals
    )

    beta_reuses_alpha = beta_path is None or Path(beta_path) == Path(alpha_path)
    if beta_reuses_alpha:
        beta_parsed = alpha_parsed
    else:
        assert beta_path is not None
        beta_parsed = _parse_determinants(
            beta_path, expected_bit_length=fcidump.n_orbitals
        )

    alpha = alpha_parsed.features
    beta = beta_parsed.features
    pair_comparisons = _unordered_pairs(alpha.count) + _unordered_pairs(beta.count)
    connectivity: ConnectivityFeatures | None = None
    work_proxy: int | None = None
    if pair_comparisons <= max_connectivity_pairs:
        alpha_connectivity = _connectivity(alpha_parsed.masks)
        beta_connectivity = (
            alpha_connectivity
            if beta_reuses_alpha
            else _connectivity(beta_parsed.masks)
        )
        connectivity = ConnectivityFeatures(
            pair_comparisons=pair_comparisons,
            alpha=alpha_connectivity,
            beta=beta_connectivity,
        )
        work_proxy = method0_work_proxy(alpha.count, beta.count, connectivity)

    combined_hash = combine_input_hashes(
        fcidump.sha256, alpha.sha256, beta.sha256
    )
    n_configurations = alpha.count * beta.count
    return InputFeatures(
        fcidump=fcidump,
        alpha=alpha,
        beta=beta,
        beta_reuses_alpha=beta_reuses_alpha,
        combined_input_sha256=combined_hash,
        n_configurations=n_configurations,
        log1p_n_configurations=math.log1p(n_configurations),
        connectivity=connectivity,
        connectivity_pair_limit=max_connectivity_pairs,
        method0_work_proxy=work_proxy,
        log1p_method0_work_proxy=math.log1p(work_proxy) if work_proxy is not None else None,
    )


def combine_input_hashes(
    fcidump_sha256: str,
    alpha_sha256: str,
    beta_sha256: str,
) -> str:
    """Combine role-labelled file digests into an unambiguous input digest."""

    role_hashes = (
        ("fcidump", fcidump_sha256),
        ("alpha", alpha_sha256),
        ("beta", beta_sha256),
    )
    digest = hashlib.sha256(b"autosbd-input-v1\0")
    for role, value in role_hashes:
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise FeatureError(f"{role} hash must be a lowercase SHA-256 digest")
        digest.update(role.encode("ascii"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(value))
    return digest.hexdigest()


def method0_work_proxy(
    n_alpha: int,
    n_beta: int,
    connectivity: ConnectivityFeatures,
) -> int:
    """Return the source-loop work proxy for one method-0 Hamiltonian multiply."""

    _require_positive_int("n_alpha", n_alpha)
    _require_positive_int("n_beta", n_beta)
    alpha_edges = (
        connectivity.alpha.directed_single_edges
        + connectivity.alpha.directed_double_edges
    )
    beta_edges = (
        connectivity.beta.directed_single_edges
        + connectivity.beta.directed_double_edges
    )
    return (
        n_alpha * n_beta
        + n_beta * alpha_edges
        + n_alpha * beta_edges
        + connectivity.alpha.directed_single_edges
        * connectivity.beta.directed_single_edges
    )


def determinant_word_counts(n_orbitals: int, bit_length: int) -> tuple[int, int]:
    """Return half-string and full interleaved determinant word counts.

    The pinned AMD implementation loads alpha/beta strings of length ``L`` and
    forms a full determinant containing ``2L`` interleaved spin-orbital bits.
    ``bit_length`` is the number of active bits stored in each ``size_t`` word.
    """

    _require_positive_int("n_orbitals", n_orbitals)
    _require_positive_int("bit_length", bit_length)
    if bit_length > 64:
        raise FeatureError("bit_length must not exceed a 64-bit size_t word")
    return (
        _ceil_div(n_orbitals, bit_length),
        _ceil_div(2 * n_orbitals, bit_length),
    )


def estimate_source_memory(
    features: InputFeatures,
    *,
    bit_length: int,
    max_block: int,
    iterations: int,
    method: int = 0,
    rdm: int = 0,
    alpha_comm_size: int = 1,
    beta_comm_size: int = 1,
    task_comm_size: int = 1,
) -> SourceMemoryEstimate:
    """Estimate audited method-0 source arrays and conservative guards.

    Let ``L`` be orbitals, ``A/B`` determinant counts, ``M`` the largest local
    product basis, ``b`` the block size, ``i`` iterations, ``h=ceil(L/w)``, and
    ``d=ceil(2L/w)`` for configured determinant word width ``w``.

    * Dense/compact integrals: ``8 * (6L^2 + K)``, where
      ``K=T(T+1)/2`` and ``T=L(L+1)/2``.
    * Persistent determinant cache: ``8ABd``.
    * Davidson arrays (including one all-reduce scratch):
      ``8 * ((2b+7)M + 2b^2 + b + bi)``.
    * Device arrays: integrals + cache + the larger of cache construction or
      ``T/Wb`` plus the largest helper map.

    Version 1 intentionally rejects stored-Hamiltonian method 1 and any RDM
    request because their peak lifetimes have not been audited into this guard.
    """

    if isinstance(method, bool) or not isinstance(method, int) or method != 0:
        raise UnsupportedGuardConfiguration(
            f"memory guard v1 supports only method=0, got {method!r}"
        )
    if isinstance(rdm, bool) or not isinstance(rdm, int) or rdm != 0:
        raise UnsupportedGuardConfiguration(
            f"memory guard v1 supports only rdm=0, got {rdm!r}"
        )
    _require_positive_int("max_block", max_block)
    _require_positive_int("iterations", iterations)
    _require_positive_int("alpha_comm_size", alpha_comm_size)
    _require_positive_int("beta_comm_size", beta_comm_size)
    _require_positive_int("task_comm_size", task_comm_size)

    n_orbitals = features.fcidump.n_orbitals
    n_alpha = features.alpha.count
    n_beta = features.beta.count
    half_words, full_words = determinant_word_counts(n_orbitals, bit_length)
    local_alpha = _ceil_div(n_alpha, alpha_comm_size)
    local_beta = _ceil_div(n_beta, beta_comm_size)
    local_configurations = local_alpha * local_beta

    integral_bytes = BYTES_PER_DOUBLE * features.fcidump.source_integral_doubles
    determinant_cache_bytes = (
        BYTES_PER_SIZE_T * n_alpha * n_beta * full_words
    )
    determinant_cache_temporary_bytes = (
        BYTES_PER_SIZE_T * half_words * (n_alpha + n_beta)
    )

    alpha_single, alpha_double, beta_single, beta_double, exact_edges = (
        _connectivity_or_safe_bounds(features)
    )
    excitation_entries = alpha_single + alpha_double + beta_single + beta_double
    total_tasks = (
        alpha_comm_size * beta_comm_size + alpha_comm_size + beta_comm_size
    )
    local_tasks = _ceil_div(total_tasks, task_comm_size)
    helper_host_bytes = BYTES_PER_SIZE_T * local_tasks * (
        2 * excitation_entries + 6 * local_alpha + 6 * local_beta + 4
    )

    davidson_doubles = (
        (2 * max_block + 7) * local_configurations
        + 2 * max_block * max_block
        + max_block
        + max_block * iterations
    )
    davidson_bytes = BYTES_PER_DOUBLE * davidson_doubles

    # This envelope covers the FCIDUMP tuple vector/serialization and the
    # determinant object/word payload; the 2x guard below remains the policy pad.
    input_envelope_bytes = (
        32 * features.fcidump.integral_records
        + 2 * features.fcidump.file_bytes
        + BYTES_PER_SIZE_T * half_words * (n_alpha + n_beta)
        + 24 * (n_alpha + n_beta)
    )
    host_known_bytes = (
        input_envelope_bytes
        + integral_bytes
        + determinant_cache_bytes
        + determinant_cache_temporary_bytes
        + helper_host_bytes
        + davidson_bytes
    )
    gpu_flat_integral_host_bytes = integral_bytes
    gpu_host_known_bytes = host_known_bytes + gpu_flat_integral_host_bytes

    gpu_helper_max_bytes = max(
        BYTES_PER_SIZE_T
        * (alpha_single + alpha_double + 4 * local_alpha + 2),
        BYTES_PER_SIZE_T
        * (beta_single + beta_double + 4 * local_beta + 2),
        BYTES_PER_SIZE_T
        * (
            alpha_single
            + beta_single
            + 2 * local_alpha
            + 2 * local_beta
            + 2
        ),
    )
    gpu_task_temporary_bytes = (
        2 * BYTES_PER_DOUBLE * local_configurations + gpu_helper_max_bytes
    )
    gpu_known_bytes = (
        integral_bytes
        + determinant_cache_bytes
        + max(determinant_cache_temporary_bytes, gpu_task_temporary_bytes)
    )

    helper_is_upper_bound = not (
        exact_edges
        and alpha_comm_size == 1
        and beta_comm_size == 1
        and task_comm_size == 1
    )
    return SourceMemoryEstimate(
        input_envelope_bytes=input_envelope_bytes,
        integral_bytes=integral_bytes,
        determinant_cache_bytes=determinant_cache_bytes,
        determinant_cache_temporary_bytes=determinant_cache_temporary_bytes,
        helper_host_bytes=helper_host_bytes,
        davidson_bytes=davidson_bytes,
        gpu_flat_integral_host_bytes=gpu_flat_integral_host_bytes,
        gpu_helper_max_bytes=gpu_helper_max_bytes,
        gpu_task_temporary_bytes=gpu_task_temporary_bytes,
        host_known_bytes=host_known_bytes,
        gpu_host_known_bytes=gpu_host_known_bytes,
        gpu_known_bytes=gpu_known_bytes,
        host_guard_bytes=memory_guard_bytes(host_known_bytes),
        gpu_host_guard_bytes=memory_guard_bytes(gpu_host_known_bytes),
        gpu_guard_bytes=memory_guard_bytes(gpu_known_bytes),
        local_configurations=local_configurations,
        helper_is_upper_bound=helper_is_upper_bound,
    )


def round_up_64_mib(value: int) -> int:
    """Round a nonnegative byte count up to the next 64 MiB boundary."""

    _require_nonnegative_int("value", value)
    return _round_up(value, MEMORY_GUARD_ALIGNMENT_BYTES)


def memory_guard_bytes(known_bytes: int) -> int:
    """Apply the fixed conservative policy: round64(512 MiB + 2*known)."""

    _require_nonnegative_int("known_bytes", known_bytes)
    return round_up_64_mib(MEMORY_GUARD_BASE_BYTES + 2 * known_bytes)


def host_admission_limit_bytes(free_host_bytes: int) -> int:
    """Reserve 20% of currently free host memory."""

    _require_nonnegative_int("free_host_bytes", free_host_bytes)
    return free_host_bytes * 4 // 5


def gpu_admission_limit_bytes(free_vram_bytes: int) -> int:
    """Return ``min(20 GiB, floor(80% * current free VRAM))``."""

    _require_nonnegative_int("free_vram_bytes", free_vram_bytes)
    return min(GPU_VRAM_CAP_BYTES, free_vram_bytes * 4 // 5)


def host_memory_feasible(required_guard_bytes: int, free_host_bytes: int) -> bool:
    _require_nonnegative_int("required_guard_bytes", required_guard_bytes)
    return required_guard_bytes <= host_admission_limit_bytes(free_host_bytes)


def gpu_memory_feasible(required_guard_bytes: int, free_vram_bytes: int) -> bool:
    _require_nonnegative_int("required_guard_bytes", required_guard_bytes)
    return required_guard_bytes <= gpu_admission_limit_bytes(free_vram_bytes)


def candidate_memory_feasible(
    backend: str,
    estimate: SourceMemoryEstimate,
    *,
    free_host_bytes: int,
    free_vram_bytes: int | None = None,
) -> bool:
    """Check the complete host/device admission gate for one candidate."""

    if backend == "cpu":
        return host_memory_feasible(estimate.host_guard_bytes, free_host_bytes)
    if backend == "gpu":
        if free_vram_bytes is None:
            raise FeatureError("free_vram_bytes is required for the GPU candidate")
        return host_memory_feasible(
            estimate.gpu_host_guard_bytes, free_host_bytes
        ) and gpu_memory_feasible(estimate.gpu_guard_bytes, free_vram_bytes)
    raise FeatureError(f"backend must be 'cpu' or 'gpu', got {backend!r}")


def _parse_fcidump_header(
    header_text: str, input_path: Path
) -> dict[str, int | tuple[int, ...]]:
    matches = list(_HEADER_FIELD_RE.finditer(header_text))
    raw_values: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group(1).upper()
        if name in raw_values:
            raise FeatureError(f"Duplicate {name} in FCIDUMP header: {input_path}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(header_text)
        raw_values[name] = header_text[match.end() : end]

    required = {"NORB", "NELEC", "MS2", "ORBSYM", "ISYM"}
    missing = sorted(required.difference(raw_values))
    if missing:
        raise FeatureError(
            f"FCIDUMP header is missing {', '.join(missing)}: {input_path}"
        )

    parsed: dict[str, int | tuple[int, ...]] = {}
    for name in ("NORB", "NELEC", "MS2", "ORBSYM", "ISYM"):
        raw_value = raw_values[name]
        tokens = [token for token in re.split(r"[\s,]+", raw_value.strip(" \t\r\n,")) if token]
        if not tokens or not all(_INTEGER_RE.fullmatch(token) for token in tokens):
            raise FeatureError(f"Invalid integer list for {name} in {input_path}")
        values = tuple(int(token) for token in tokens)
        if name != "ORBSYM" and len(values) != 1:
            raise FeatureError(f"{name} must be scalar in {input_path}")
        parsed[name] = values if name == "ORBSYM" else values[0]

    n_orbitals = int(parsed["NORB"])
    n_electrons = int(parsed["NELEC"])
    ms2 = int(parsed["MS2"])
    if n_orbitals <= 0:
        raise FeatureError(f"NORB must be positive in {input_path}")
    if n_electrons < 0 or n_electrons > 2 * n_orbitals:
        raise FeatureError(f"NELEC is outside [0, 2*NORB] in {input_path}")
    if abs(ms2) > n_electrons or (n_electrons + ms2) % 2:
        raise FeatureError(f"NELEC/MS2 are inconsistent in {input_path}")
    orbsym = tuple(parsed["ORBSYM"])  # type: ignore[arg-type]
    if len(orbsym) != n_orbitals:
        raise FeatureError(
            f"ORBSYM has {len(orbsym)} entries but NORB={n_orbitals}: {input_path}"
        )
    return parsed


def _split_header_terminator(line: str) -> tuple[str, bool]:
    upper_line = line.upper()
    end_position = upper_line.find("&END")
    slash_position = line.find("/")
    positions = [position for position in (end_position, slash_position) if position >= 0]
    if not positions:
        return line, False
    position = min(positions)
    return line[:position], True


def _parse_integral_record(
    line: str,
    input_path: Path,
    line_number: int,
    n_orbitals: int,
) -> tuple[float, tuple[int, int, int, int]]:
    fields = line.split()
    if len(fields) != 5:
        raise FeatureError(
            f"Expected five FCIDUMP fields at {input_path}:{line_number}, "
            f"found {len(fields)}"
        )
    try:
        value = float(fields[0].replace("D", "E").replace("d", "e"))
    except ValueError as error:
        raise FeatureError(
            f"Invalid FCIDUMP value at {input_path}:{line_number}: {fields[0]!r}"
        ) from error
    if not math.isfinite(value):
        raise FeatureError(f"Non-finite FCIDUMP value at {input_path}:{line_number}")

    try:
        indices = tuple(int(field) for field in fields[1:])
    except ValueError as error:
        raise FeatureError(
            f"Invalid FCIDUMP index at {input_path}:{line_number}"
        ) from error
    if any(index < 0 or index > n_orbitals for index in indices):
        raise FeatureError(
            f"FCIDUMP index outside [0, NORB] at {input_path}:{line_number}"
        )
    return value, indices  # type: ignore[return-value]


def _parse_determinants(
    path: Path,
    *,
    expected_bit_length: int | None,
) -> _ParsedDeterminants:
    if expected_bit_length is not None:
        _require_positive_int("expected_bit_length", expected_bit_length)

    input_path = Path(path)
    digest = hashlib.sha256()
    file_bytes = 0
    masks: list[int] = []
    occupancies: list[int] = []
    seen: set[str] = set()
    bit_length = expected_bit_length

    with input_path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            digest.update(raw_line)
            file_bytes += len(raw_line)
            try:
                line = raw_line.decode("ascii")
            except UnicodeDecodeError as error:
                raise FeatureError(
                    f"Determinant file is not ASCII at {input_path}:{line_number}"
                ) from error
            for token in line.split():
                if not _BINARY_RE.fullmatch(token):
                    raise FeatureError(
                        f"Non-binary determinant at {input_path}:{line_number}: {token!r}"
                    )
                if bit_length is None:
                    bit_length = len(token)
                if len(token) != bit_length:
                    raise FeatureError(
                        f"Determinant length {len(token)} does not match expected "
                        f"length {bit_length} at {input_path}:{line_number}"
                    )
                if token in seen:
                    raise FeatureError(
                        f"Duplicate determinant at {input_path}:{line_number}: {token}"
                    )
                seen.add(token)
                masks.append(int(token, 2))
                occupancies.append(token.count("1"))

    if not masks or bit_length is None:
        raise FeatureError(f"Determinant file contains no strings: {input_path}")
    occupancy_mean = sum(occupancies) / len(occupancies)
    occupancy_variance = sum(
        (occupancy - occupancy_mean) ** 2 for occupancy in occupancies
    ) / len(occupancies)
    features = DeterminantFeatures(
        path=str(input_path),
        file_bytes=file_bytes,
        sha256=digest.hexdigest(),
        count=len(masks),
        unique_count=len(seen),
        bit_length=bit_length,
        occupancy_min=min(occupancies),
        occupancy_max=max(occupancies),
        occupancy_mean=occupancy_mean,
        occupancy_variance=occupancy_variance,
    )
    return _ParsedDeterminants(features=features, masks=tuple(masks))


def _connectivity(masks: tuple[int, ...]) -> ConnectivityStats:
    count = len(masks)
    single_degrees = [0] * count
    double_degrees = [0] * count
    directed_single_edges = 0
    directed_double_edges = 0
    for left in range(count):
        left_mask = masks[left]
        for right in range(left + 1, count):
            difference = (left_mask ^ masks[right]).bit_count()
            if difference == 2:
                directed_single_edges += 2
                single_degrees[left] += 1
                single_degrees[right] += 1
            elif difference == 4:
                directed_double_edges += 2
                double_degrees[left] += 1
                double_degrees[right] += 1

    possible_directed_edges = count * (count - 1)
    return ConnectivityStats(
        determinants=count,
        unordered_pair_comparisons=_unordered_pairs(count),
        directed_single_edges=directed_single_edges,
        directed_double_edges=directed_double_edges,
        single_degree_min=min(single_degrees),
        single_degree_max=max(single_degrees),
        single_degree_mean=directed_single_edges / count,
        double_degree_min=min(double_degrees),
        double_degree_max=max(double_degrees),
        double_degree_mean=directed_double_edges / count,
        single_edge_density=(
            directed_single_edges / possible_directed_edges
            if possible_directed_edges
            else 0.0
        ),
        double_edge_density=(
            directed_double_edges / possible_directed_edges
            if possible_directed_edges
            else 0.0
        ),
    )


def _connectivity_or_safe_bounds(
    features: InputFeatures,
) -> tuple[int, int, int, int, bool]:
    if features.connectivity is not None:
        alpha = features.connectivity.alpha
        beta = features.connectivity.beta
        return (
            alpha.directed_single_edges,
            alpha.directed_double_edges,
            beta.directed_single_edges,
            beta.directed_double_edges,
            True,
        )
    # A pair can contribute to at most one excitation class. Assigning the full
    # possible directed graph to the combined single+double count is safe.  Put
    # it in the single class as well because the mixed GPU map uses singles.
    alpha_possible = features.alpha.count * (features.alpha.count - 1)
    beta_possible = features.beta.count * (features.beta.count - 1)
    return alpha_possible, 0, beta_possible, 0, False


def _unordered_pairs(count: int) -> int:
    return count * (count - 1) // 2


def _ceil_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


def _round_up(value: int, multiple: int) -> int:
    return ((value + multiple - 1) // multiple) * multiple if value else 0


def _require_nonnegative_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FeatureError(f"{name} must be a nonnegative integer")


def _require_positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FeatureError(f"{name} must be a positive integer")


__all__ = [
    "BYTES_PER_DOUBLE",
    "BYTES_PER_SIZE_T",
    "DEFAULT_CONNECTIVITY_PAIR_LIMIT",
    "FeatureError",
    "FcidumpFeatures",
    "DeterminantFeatures",
    "ConnectivityStats",
    "ConnectivityFeatures",
    "InputFeatures",
    "SourceMemoryEstimate",
    "UnsupportedGuardConfiguration",
    "GPU_VRAM_CAP_BYTES",
    "MIB",
    "GIB",
    "candidate_memory_feasible",
    "combine_input_hashes",
    "determinant_word_counts",
    "estimate_source_memory",
    "extract_input_features",
    "gpu_admission_limit_bytes",
    "gpu_memory_feasible",
    "host_admission_limit_bytes",
    "host_memory_feasible",
    "memory_guard_bytes",
    "method0_work_proxy",
    "parse_determinants",
    "parse_fcidump",
    "round_up_64_mib",
]
