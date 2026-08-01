"""Focused tests for strict parsing of pinned AMD-HPC SBD output."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

from autosbd.sbd_output import SbdParseError, parse_sbd_file, parse_sbd_text


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MOCK_SBD = REPOSITORY_ROOT / "tests" / "fixtures" / "mock_sbd.py"
CPU_STAGE1_LOG = REPOSITORY_ROOT / "logs" / "stage1_amd_cpu_fe4s4_t16_i6.stdout.log"
GPU_STAGE1_LOG = (
    REPOSITORY_ROOT / "logs" / "stage1_amd_gpu_fe4s4_i6_rerun1.stdout.log"
)


def run_fixture(mode: str) -> str:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, str(MOCK_SBD), mode],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return completed.stdout


def minimal_output(density_text: str, *, device_line: str | None = None) -> str:
    lines = [
        " Davidson iteration 0.0 (tol=8.0e-09): -1.0",
        " Sample-based diagonalization: Energy = -1.0",
        f" Sample-based diagonalization: density = {density_text}",
    ]
    if device_line is not None:
        lines.insert(0, device_line)
    return "\n".join(lines) + "\n"


@unittest.skipUnless(
    CPU_STAGE1_LOG.is_file() and GPU_STAGE1_LOG.is_file(),
    "authoritative AMD Stage 1 CPU/GPU logs are not present",
)
class RealAmdStage1OutputTests(unittest.TestCase):
    def test_cpu_gpu_logs_parse_and_agree(self) -> None:
        cpu = parse_sbd_file(
            CPU_STAGE1_LOG,
            residual_tolerance=1.0e-8,
            expected_orbitals=36,
            require_device_assignment=False,
        )
        gpu = parse_sbd_file(
            GPU_STAGE1_LOG,
            residual_tolerance=1.0e-8,
            expected_orbitals=36,
            require_device_assignment=True,
        )

        self.assertTrue(cpu.converged)
        self.assertTrue(gpu.converged)
        self.assertEqual(cpu.iteration_records, 50)
        self.assertEqual(gpu.iteration_records, 50)
        self.assertEqual((cpu.final_restart_index, cpu.final_subspace_index), (4, 9))
        self.assertEqual((gpu.final_restart_index, gpu.final_subspace_index), (4, 9))
        self.assertAlmostEqual(cpu.final_residual, 8.931146441578446e-09)
        self.assertAlmostEqual(gpu.final_residual, 8.931494922593578e-09)
        self.assertFalse(cpu.device_assignment_seen)
        self.assertTrue(gpu.device_assignment_seen)
        self.assertTrue(cpu.density_bracket_repaired)
        self.assertTrue(gpu.density_bracket_repaired)
        self.assertEqual(len(cpu.density), 36)
        self.assertEqual(len(gpu.density), 36)
        self.assertLess(abs(cpu.energy - gpu.energy), 1.0e-10)
        self.assertLess(
            max(abs(cpu_value - gpu_value) for cpu_value, gpu_value in zip(cpu.density, gpu.density)),
            1.0e-10,
        )
        self.assertAlmostEqual(cpu.solver_time_s or 0.0, 75.59071)
        self.assertAlmostEqual(gpu.solver_time_s or 0.0, 15.518114)
        self.assertAlmostEqual(cpu.initialization_time_s or 0.0, 0.007204)
        self.assertAlmostEqual(gpu.initialization_time_s or 0.0, 0.013988)


class FixtureOutputTests(unittest.TestCase):
    def test_nonconverged_fixture_is_parsed_but_not_accepted(self) -> None:
        parsed = parse_sbd_text(
            run_fixture("nonconverged"),
            residual_tolerance=1.0e-8,
            expected_orbitals=36,
            require_device_assignment=False,
        )

        self.assertFalse(parsed.converged)
        self.assertGreater(parsed.final_residual, 1.0e-8)
        self.assertEqual(parsed.energy, -326.6982536731583)
        self.assertEqual(len(parsed.density), 36)
        self.assertTrue(parsed.density_bracket_repaired)

    def test_malformed_fixture_raises_parse_error(self) -> None:
        with self.assertRaisesRegex(SbdParseError, "Malformed density list"):
            parse_sbd_text(
                run_fixture("malformed"),
                residual_tolerance=1.0e-8,
                expected_orbitals=36,
                require_device_assignment=False,
            )


class DensityRepairTests(unittest.TestCase):
    def test_exactly_one_missing_final_bracket_is_repaired(self) -> None:
        repaired = parse_sbd_text(
            minimal_output("[1.0, 2.0"),
            residual_tolerance=1.0e-8,
            expected_orbitals=2,
            require_device_assignment=False,
        )
        complete = parse_sbd_text(
            minimal_output("[1.0, 2.0]"),
            residual_tolerance=1.0e-8,
            expected_orbitals=2,
            require_device_assignment=False,
        )

        self.assertEqual(repaired.density, (1.0, 2.0))
        self.assertTrue(repaired.density_bracket_repaired)
        self.assertEqual(complete.density, (1.0, 2.0))
        self.assertFalse(complete.density_bracket_repaired)

    def test_density_repair_rejects_other_structural_damage(self) -> None:
        malformed_density_values = (
            "1.0, 2.0",
            "[1.0, 2.0 trailing-text",
            "[[1.0, 2.0",
        )
        for density_text in malformed_density_values:
            with self.subTest(density=density_text), self.assertRaises(SbdParseError):
                parse_sbd_text(
                    minimal_output(density_text),
                    residual_tolerance=1.0e-8,
                    expected_orbitals=2,
                    require_device_assignment=False,
                )


class DeviceAssignmentTests(unittest.TestCase):
    def test_gpu_mode_requires_exact_device_assignment_line(self) -> None:
        with self.assertRaisesRegex(SbdParseError, "missing the device-assignment line"):
            parse_sbd_text(
                minimal_output("[1.0, 2.0]"),
                residual_tolerance=1.0e-8,
                expected_orbitals=2,
                require_device_assignment=True,
            )

        parsed = parse_sbd_text(
            minimal_output("[1.0, 2.0]", device_line="rank 0 has device 0"),
            residual_tolerance=1.0e-8,
            expected_orbitals=2,
            require_device_assignment=True,
        )
        self.assertTrue(parsed.device_assignment_seen)

        with self.assertRaisesRegex(SbdParseError, "missing the device-assignment line"):
            parse_sbd_text(
                minimal_output(
                    "[1.0, 2.0]", device_line="rank 0 has device 0 trailing-text"
                ),
                residual_tolerance=1.0e-8,
                expected_orbitals=2,
                require_device_assignment=True,
            )


if __name__ == "__main__":
    unittest.main()
