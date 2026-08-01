"""Strict parsing for the pinned AMD-HPC Selected-Basis Diagonalization output."""

from __future__ import annotations

import ast
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


FLOAT_PATTERN = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
ITERATION_RE = re.compile(
    rf"^\s*Davidson iteration\s+(\d+)\.(\d+)\s+\(tol=({FLOAT_PATTERN})\):"
)
ENERGY_RE = re.compile(
    rf"^\s*Sample-based diagonalization: Energy =\s*({FLOAT_PATTERN})\s*$"
)
DENSITY_RE = re.compile(r"^\s*Sample-based diagonalization: density =\s*(\[.*)\s*$")
DEVICE_RE = re.compile(r"^\s*rank\s+\d+\s+has device\s+\d+\s*$")

TIMING_PATTERNS = {
    "helper_construction_time_s": re.compile(
        rf"^\s*Elapsed time for helper construction\s+({FLOAT_PATTERN})\s+\(sec\)\s*$"
    ),
    "initial_state_time_s": re.compile(
        rf"^\s*Elapsed time for init\s+({FLOAT_PATTERN})\s+\(sec\)\s*$"
    ),
    "solver_time_s": re.compile(
        rf"^\s*Elapsed time for davidson\s+({FLOAT_PATTERN})\s+\(sec\)\s*$"
    ),
    "diagonalization_time_s": re.compile(
        rf"^\s*Elapsed time for diagonalization\s+({FLOAT_PATTERN})\s+\(sec\)\s*$"
    ),
    "post_solver_matvec_time_s": re.compile(
        rf"^\s*Elapsed time for mult\s+({FLOAT_PATTERN})\s+\(sec\)\s*$"
    ),
    "measurement_time_s": re.compile(
        rf"^\s*Elapsed time for measurement\s+({FLOAT_PATTERN})\s+\(sec\)\s*$"
    ),
}


class SbdParseError(ValueError):
    """Raised when upstream output is missing, ambiguous, or non-finite."""


@dataclass(frozen=True)
class ParsedSbdOutput:
    final_residual: float
    converged: bool
    iteration_records: int
    final_restart_index: int
    final_subspace_index: int
    energy: float
    density: tuple[float, ...]
    density_bracket_repaired: bool
    device_assignment_seen: bool
    helper_construction_time_s: float | None
    initial_state_time_s: float | None
    initialization_time_s: float | None
    solver_time_s: float | None
    diagonalization_time_s: float | None
    post_solver_matvec_time_s: float | None
    measurement_time_s: float | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["density"] = list(self.density)
        return payload


def parse_sbd_file(
    path: Path,
    *,
    residual_tolerance: float,
    expected_orbitals: int | None,
    require_device_assignment: bool,
) -> ParsedSbdOutput:
    return parse_sbd_text(
        path.read_text(encoding="utf-8"),
        residual_tolerance=residual_tolerance,
        expected_orbitals=expected_orbitals,
        require_device_assignment=require_device_assignment,
    )


def parse_sbd_text(
    text: str,
    *,
    residual_tolerance: float,
    expected_orbitals: int | None,
    require_device_assignment: bool,
) -> ParsedSbdOutput:
    if not math.isfinite(residual_tolerance) or residual_tolerance <= 0:
        raise SbdParseError("residual_tolerance must be finite and positive")

    iteration_values: list[tuple[int, int, float]] = []
    energies: list[float] = []
    densities: list[tuple[tuple[float, ...], bool]] = []
    timing_values: dict[str, list[float]] = {name: [] for name in TIMING_PATTERNS}
    device_assignment_seen = False

    for line in text.splitlines():
        if match := ITERATION_RE.match(line):
            iteration_values.append(
                (int(match.group(1)), int(match.group(2)), _finite_float(match.group(3)))
            )
        if match := ENERGY_RE.match(line):
            energies.append(_finite_float(match.group(1)))
        if match := DENSITY_RE.match(line):
            densities.append(_parse_density(match.group(1)))
        if DEVICE_RE.match(line):
            device_assignment_seen = True
        for name, pattern in TIMING_PATTERNS.items():
            if match := pattern.match(line):
                timing_values[name].append(_finite_float(match.group(1)))

    if not iteration_values:
        raise SbdParseError("No Davidson iteration records found")
    if len(energies) != 1:
        raise SbdParseError(f"Expected exactly one authoritative energy, found {len(energies)}")
    if len(densities) != 1:
        raise SbdParseError(f"Expected exactly one final density, found {len(densities)}")
    if require_device_assignment and not device_assignment_seen:
        raise SbdParseError("GPU output is missing the device-assignment line")

    density, bracket_repaired = densities[0]
    if expected_orbitals is not None and len(density) != expected_orbitals:
        raise SbdParseError(
            f"Density length {len(density)} does not match orbital count {expected_orbitals}"
        )

    unique_timings = {
        name: _optional_unique_timing(name, values) for name, values in timing_values.items()
    }
    helper_time = unique_timings["helper_construction_time_s"]
    initial_state_time = unique_timings["initial_state_time_s"]
    initialization_time = (
        helper_time + initial_state_time
        if helper_time is not None and initial_state_time is not None
        else None
    )
    restart_index, subspace_index, final_residual = iteration_values[-1]

    return ParsedSbdOutput(
        final_residual=final_residual,
        converged=final_residual <= residual_tolerance,
        iteration_records=len(iteration_values),
        final_restart_index=restart_index,
        final_subspace_index=subspace_index,
        energy=energies[0],
        density=density,
        density_bracket_repaired=bracket_repaired,
        device_assignment_seen=device_assignment_seen,
        helper_construction_time_s=helper_time,
        initial_state_time_s=initial_state_time,
        initialization_time_s=initialization_time,
        solver_time_s=unique_timings["solver_time_s"],
        diagonalization_time_s=unique_timings["diagonalization_time_s"],
        post_solver_matvec_time_s=unique_timings["post_solver_matvec_time_s"],
        measurement_time_s=unique_timings["measurement_time_s"],
    )


def _parse_density(text: str) -> tuple[tuple[float, ...], bool]:
    density_text = text.strip()
    repaired = False
    if not density_text.endswith("]"):
        density_text += "]"
        repaired = True
    try:
        parsed = ast.literal_eval(density_text)
    except (SyntaxError, ValueError) as error:
        raise SbdParseError("Malformed density list") from error
    if not isinstance(parsed, list) or not parsed:
        raise SbdParseError("Density must be a nonempty list")
    density = tuple(_finite_float(value) for value in parsed)
    return density, repaired


def _finite_float(value: Any) -> float:
    try:
        converted = float(value)
    except (TypeError, ValueError) as error:
        raise SbdParseError(f"Invalid numeric value: {value!r}") from error
    if not math.isfinite(converted):
        raise SbdParseError(f"Non-finite numeric value: {value!r}")
    return converted


def _optional_unique_timing(name: str, values: list[float]) -> float | None:
    if len(values) > 1:
        raise SbdParseError(f"Expected at most one {name}, found {len(values)}")
    return values[0] if values else None
