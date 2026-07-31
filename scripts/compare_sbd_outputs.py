#!/usr/bin/env python3
"""Compare converged CPU and GPU outputs from the upstream SBD application."""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path


FLOAT_PATTERN = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
ITERATION_RE = re.compile(rf"Davidson iteration\s+\S+\s+\(tol=({FLOAT_PATTERN})\)")
ENERGY_RE = re.compile(rf"Sample-based diagonalization: Energy =\s*({FLOAT_PATTERN})")
DENSITY_RE = re.compile(r"Sample-based diagonalization: density =\s*(\[.*)")


@dataclass(frozen=True)
class SbdOutput:
    path: Path
    final_residual: float
    energy: float
    density: tuple[float, ...]


def parse_output(path: Path) -> SbdOutput:
    final_residual: float | None = None
    energy: float | None = None
    density: tuple[float, ...] | None = None

    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if match := ITERATION_RE.search(line):
                final_residual = float(match.group(1))
            if match := ENERGY_RE.search(line):
                energy = float(match.group(1))
            if match := DENSITY_RE.search(line):
                density_text = match.group(1).strip()
                # The pinned upstream vector formatter omits the closing bracket.
                if not density_text.endswith("]"):
                    density_text += "]"
                parsed = ast.literal_eval(density_text)
                if not isinstance(parsed, list):
                    raise ValueError(f"Density is not a list in {path}")
                density = tuple(float(value) for value in parsed)

    missing = [
        name
        for name, value in (
            ("final residual", final_residual),
            ("energy", energy),
            ("density", density),
        )
        if value is None
    ]
    if missing:
        raise ValueError(f"Missing {', '.join(missing)} in {path}")

    assert final_residual is not None
    assert energy is not None
    assert density is not None
    return SbdOutput(path=path, final_residual=final_residual, energy=energy, density=density)


def compare(
    cpu: SbdOutput,
    gpu: SbdOutput,
    residual_tolerance: float,
    energy_rtol: float,
    density_atol: float,
) -> dict[str, object]:
    if len(cpu.density) != len(gpu.density):
        raise ValueError(
            f"Density lengths differ: CPU={len(cpu.density)}, GPU={len(gpu.density)}"
        )

    energy_abs_error = abs(cpu.energy - gpu.energy)
    energy_scale = max(abs(cpu.energy), abs(gpu.energy), 1.0e-300)
    energy_rel_error = energy_abs_error / energy_scale
    density_differences = [
        abs(cpu_value - gpu_value)
        for cpu_value, gpu_value in zip(cpu.density, gpu.density, strict=True)
    ]
    density_max_abs_error = max(density_differences, default=0.0)
    density_l2_error = math.sqrt(math.fsum(value * value for value in density_differences))

    checks = {
        "cpu_residual": cpu.final_residual <= residual_tolerance,
        "gpu_residual": gpu.final_residual <= residual_tolerance,
        "energy_relative_error": energy_rel_error <= energy_rtol,
        "density_max_absolute_error": density_max_abs_error <= density_atol,
    }

    return {
        "schema_version": 1,
        "cpu": {
            "path": str(cpu.path),
            "final_residual": cpu.final_residual,
            "energy_hartree": cpu.energy,
            "density_length": len(cpu.density),
        },
        "gpu": {
            "path": str(gpu.path),
            "final_residual": gpu.final_residual,
            "energy_hartree": gpu.energy,
            "density_length": len(gpu.density),
        },
        "metrics": {
            "residual_absolute_difference": abs(cpu.final_residual - gpu.final_residual),
            "energy_absolute_error_hartree": energy_abs_error,
            "energy_relative_error": energy_rel_error,
            "density_max_absolute_error": density_max_abs_error,
            "density_l2_error": density_l2_error,
        },
        "criteria": {
            "residual_tolerance": residual_tolerance,
            "energy_relative_tolerance": energy_rtol,
            "density_max_absolute_tolerance": density_atol,
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", required=True, type=Path, help="CPU stdout log")
    parser.add_argument("--gpu", required=True, type=Path, help="GPU stdout log")
    parser.add_argument("--residual-tolerance", type=float, default=1.0e-8)
    parser.add_argument("--energy-rtol", type=float, default=1.0e-10)
    parser.add_argument("--density-atol", type=float, default=1.0e-10)
    parser.add_argument("--output", type=Path, help="Optional atomic JSON output path")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    result = compare(
        parse_output(arguments.cpu),
        parse_output(arguments.gpu),
        arguments.residual_tolerance,
        arguments.energy_rtol,
        arguments.density_atol,
    )
    if arguments.output:
        atomic_write_json(arguments.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
