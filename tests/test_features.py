from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from autosbd.features import (
    GIB,
    MIB,
    FeatureError,
    UnsupportedGuardConfiguration,
    candidate_memory_feasible,
    combine_input_hashes,
    estimate_source_memory,
    extract_input_features,
    gpu_admission_limit_bytes,
    gpu_memory_feasible,
    host_memory_feasible,
    memory_guard_bytes,
    parse_determinants,
    parse_fcidump,
    round_up_64_mib,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FE4S4_DIRECTORY = (
    REPOSITORY_ROOT
    / "external"
    / "amd-sbd"
    / "samples"
    / "selected_basis_diagonalization"
)


class Fe4S4FeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fcidump_path = FE4S4_DIRECTORY / "fcidump_Fe4S4.txt"
        cls.determinant_path = FE4S4_DIRECTORY / "AlphaDets.txt"
        if not cls.fcidump_path.is_file() or not cls.determinant_path.is_file():
            raise unittest.SkipTest("Pinned AMD Fe4S4 inputs are unavailable")
        cls.features = extract_input_features(
            cls.fcidump_path,
            cls.determinant_path,
            max_connectivity_pairs=60_000,
        )

    def test_streamed_fcidump_core_values(self) -> None:
        parsed = self.features.fcidump
        self.assertEqual(parsed.file_bytes, 9_584_950)
        self.assertEqual(parsed.n_orbitals, 36)
        self.assertEqual(parsed.n_electrons, 54)
        self.assertEqual(parsed.ms2, 0)
        self.assertEqual(parsed.isym, 1)
        self.assertEqual(parsed.orbsym, (1,) * 36)
        self.assertEqual(parsed.integral_records, 222_778)
        self.assertEqual(parsed.core_integrals, 1)
        self.assertEqual(parsed.one_electron_integrals, 666)
        self.assertEqual(parsed.two_electron_integrals, 222_111)
        self.assertEqual(parsed.exact_zero_integrals, 1)
        self.assertAlmostEqual(parsed.sum_abs_integrals, 1054.5633693506882, places=12)
        self.assertAlmostEqual(parsed.max_abs_integral, 13.43276390325754)
        self.assertEqual(parsed.compact_two_electron_slots, 222_111)
        self.assertEqual(parsed.two_electron_fill_density, 1.0)
        self.assertEqual(parsed.source_integral_doubles, 229_887)

    def test_determinants_connectivity_and_work_proxy(self) -> None:
        alpha = self.features.alpha
        self.assertTrue(self.features.beta_reuses_alpha)
        self.assertEqual(alpha.file_bytes, 9_028)
        self.assertEqual(alpha.count, 244)
        self.assertEqual(alpha.unique_count, 244)
        self.assertEqual(alpha.bit_length, 36)
        self.assertEqual(alpha.occupancy_min, 27)
        self.assertEqual(alpha.occupancy_max, 27)
        self.assertEqual(alpha.occupancy_mean, 27.0)
        self.assertEqual(alpha.occupancy_variance, 0.0)
        self.assertEqual(self.features.n_configurations, 59_536)

        connectivity = self.features.connectivity
        self.assertIsNotNone(connectivity)
        assert connectivity is not None
        self.assertEqual(connectivity.pair_comparisons, 59_292)
        self.assertEqual(connectivity.alpha.directed_single_edges, 8_748)
        self.assertEqual(connectivity.alpha.directed_double_edges, 50_544)
        self.assertEqual(connectivity.alpha.single_degree_min, 35)
        self.assertEqual(connectivity.alpha.single_degree_max, 243)
        self.assertAlmostEqual(connectivity.alpha.single_degree_mean, 35.85245901639344)
        self.assertEqual(connectivity.alpha.double_degree_min, 0)
        self.assertEqual(connectivity.alpha.double_degree_max, 208)
        self.assertAlmostEqual(connectivity.alpha.double_degree_mean, 207.14754098360655)
        self.assertEqual(self.features.method0_work_proxy, 105_521_536)
        self.assertAlmostEqual(
            self.features.log1p_method0_work_proxy,
            math.log1p(105_521_536),
        )

    def test_hashes_are_content_based_and_combined_by_role(self) -> None:
        self.assertRegex(self.features.fcidump.sha256, r"^[0-9a-f]{64}$")
        self.assertRegex(self.features.alpha.sha256, r"^[0-9a-f]{64}$")
        expected = combine_input_hashes(
            self.features.fcidump.sha256,
            self.features.alpha.sha256,
            self.features.alpha.sha256,
        )
        self.assertEqual(self.features.combined_input_sha256, expected)
        swapped = combine_input_hashes(
            self.features.alpha.sha256,
            self.features.fcidump.sha256,
            self.features.alpha.sha256,
        )
        self.assertNotEqual(expected, swapped)

    def test_source_memory_values_and_guards(self) -> None:
        estimate = estimate_source_memory(
            self.features,
            bit_length=20,
            max_block=10,
            iterations=6,
        )
        self.assertEqual(estimate.integral_bytes, 1_839_096)
        self.assertEqual(estimate.determinant_cache_bytes, 1_905_152)
        self.assertEqual(estimate.determinant_cache_temporary_bytes, 7_808)
        self.assertEqual(estimate.helper_host_bytes, 5_762_400)
        self.assertEqual(estimate.davidson_bytes, 12_861_936)
        self.assertEqual(estimate.gpu_helper_max_bytes, 482_160)
        self.assertEqual(estimate.gpu_task_temporary_bytes, 1_434_736)
        self.assertEqual(estimate.gpu_known_bytes, 5_178_984)
        self.assertEqual(estimate.host_known_bytes, 48_694_708)
        self.assertEqual(estimate.gpu_host_known_bytes, 50_533_804)
        self.assertEqual(estimate.host_guard_bytes, 640 * MIB)
        self.assertEqual(estimate.gpu_host_guard_bytes, 640 * MIB)
        self.assertEqual(estimate.gpu_guard_bytes, 576 * MIB)
        self.assertFalse(estimate.helper_is_upper_bound)


class SmallInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)

    def _write(self, name: str, contents: str) -> Path:
        path = self.directory / name
        path.write_text(contents, encoding="ascii")
        return path

    def _fcidump(self) -> Path:
        return self._write(
            "FCIDUMP",
            """ &FCI NORB=4, NELEC=2, MS2=0,
 ORBSYM=1,1,1,1,
 ISYM=1,
 &END
 1.0D+00 1 1 0 0
 -5.0e-1 1 1 1 1
 0.0 0 0 0 0
""",
        )

    def _determinants(self, name: str = "dets.txt") -> Path:
        return self._write(name, "1100\n1010\n1001\n")

    def test_connectivity_threshold_boundary_and_null_work(self) -> None:
        fcidump = self._fcidump()
        determinants = self._determinants()
        below = extract_input_features(
            fcidump, determinants, max_connectivity_pairs=5
        )
        self.assertIsNone(below.connectivity)
        self.assertIsNone(below.method0_work_proxy)
        self.assertIsNone(below.log1p_method0_work_proxy)

        at_boundary = extract_input_features(
            fcidump, determinants, max_connectivity_pairs=6
        )
        self.assertIsNotNone(at_boundary.connectivity)
        assert at_boundary.connectivity is not None
        self.assertEqual(at_boundary.connectivity.pair_comparisons, 6)
        self.assertEqual(at_boundary.connectivity.alpha.directed_single_edges, 6)
        self.assertEqual(at_boundary.connectivity.alpha.directed_double_edges, 0)
        self.assertEqual(at_boundary.method0_work_proxy, 81)

    def test_fcidump_fortran_float_and_counts(self) -> None:
        parsed = parse_fcidump(self._fcidump())
        self.assertEqual(parsed.integral_records, 3)
        self.assertEqual(parsed.one_electron_integrals, 1)
        self.assertEqual(parsed.two_electron_integrals, 1)
        self.assertEqual(parsed.core_integrals, 1)
        self.assertEqual(parsed.exact_zero_integrals, 1)
        self.assertEqual(parsed.sum_abs_integrals, 1.5)

    def test_extra_fcidump_namelist_fields_are_ignored(self) -> None:
        path = self._write(
            "FCIDUMP-extra",
            "&FCI NORB=2,NELEC=2,MS2=0,ORBSYM=1,1,ISYM=1,IUHF=0,&END\n"
            "0.0 0 0 0 0\n",
        )
        parsed = parse_fcidump(path)
        self.assertEqual(parsed.n_orbitals, 2)
        self.assertEqual(parsed.isym, 1)

    def test_malformed_fcidump_inputs_are_rejected(self) -> None:
        cases = {
            "missing_end": "&FCI NORB=2,NELEC=2,MS2=0,ORBSYM=1,1,ISYM=1,\n",
            "bad_orbsym": (
                "&FCI NORB=2,NELEC=2,MS2=0,ORBSYM=1,ISYM=1,&END\n"
                "0.0 0 0 0 0\n"
            ),
            "bad_record": (
                "&FCI NORB=2,NELEC=2,MS2=0,ORBSYM=1,1,ISYM=1,&END\n"
                "1.0 1 0 0 0\n"
            ),
            "nonfinite": (
                "&FCI NORB=2,NELEC=2,MS2=0,ORBSYM=1,1,ISYM=1,&END\n"
                "nan 0 0 0 0\n"
            ),
        }
        for name, contents in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(FeatureError):
                    parse_fcidump(self._write(name, contents))

    def test_malformed_determinants_are_rejected(self) -> None:
        cases = {
            "duplicate": "1100\n1100\n",
            "nonbinary": "1100\n10x0\n",
            "wrong_length": "1100\n101\n",
            "empty": "\n\t\n",
        }
        for name, contents in cases.items():
            with self.subTest(name=name):
                path = self._write(name, contents)
                with self.assertRaises(FeatureError):
                    parse_determinants(path, expected_bit_length=4)

    def test_guard_rejects_unaudited_solver_modes(self) -> None:
        features = extract_input_features(
            self._fcidump(), self._determinants(), max_connectivity_pairs=6
        )
        with self.assertRaises(UnsupportedGuardConfiguration):
            estimate_source_memory(
                features,
                bit_length=4,
                max_block=2,
                iterations=1,
                method=1,
            )
        with self.assertRaises(UnsupportedGuardConfiguration):
            estimate_source_memory(
                features,
                bit_length=4,
                max_block=2,
                iterations=1,
                rdm=1,
            )
        with self.assertRaises(UnsupportedGuardConfiguration):
            estimate_source_memory(
                features,
                bit_length=4,
                max_block=2,
                iterations=1,
                method=0.0,  # type: ignore[arg-type]
            )

    def test_unknown_connectivity_uses_safe_memory_upper_bound(self) -> None:
        features = extract_input_features(
            self._fcidump(), self._determinants(), max_connectivity_pairs=5
        )
        estimate = estimate_source_memory(
            features,
            bit_length=4,
            max_block=2,
            iterations=1,
        )
        self.assertTrue(estimate.helper_is_upper_bound)
        self.assertGreater(estimate.gpu_helper_max_bytes, 0)


class MemoryPolicyTests(unittest.TestCase):
    def test_rounding_and_guard_boundaries(self) -> None:
        self.assertEqual(round_up_64_mib(0), 0)
        self.assertEqual(round_up_64_mib(64 * MIB), 64 * MIB)
        self.assertEqual(round_up_64_mib(64 * MIB + 1), 128 * MIB)
        self.assertEqual(memory_guard_bytes(0), 512 * MIB)
        self.assertEqual(memory_guard_bytes(32 * MIB), 576 * MIB)
        with self.assertRaises(FeatureError):
            round_up_64_mib(-1)

    def test_gpu_limit_uses_eighty_percent_and_twenty_gib_cap(self) -> None:
        self.assertEqual(gpu_admission_limit_bytes(10 * GIB), 8 * GIB)
        self.assertEqual(gpu_admission_limit_bytes(30 * GIB), 20 * GIB)
        self.assertTrue(gpu_memory_feasible(8 * GIB, 10 * GIB))
        self.assertFalse(gpu_memory_feasible(8 * GIB + 1, 10 * GIB))
        self.assertTrue(gpu_memory_feasible(20 * GIB, 30 * GIB))
        self.assertFalse(gpu_memory_feasible(20 * GIB + 1, 30 * GIB))

    def test_candidate_feasibility_checks_host_and_device(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            fcidump = directory / "FCIDUMP"
            determinants = directory / "dets"
            fcidump.write_text(
                "&FCI NORB=2,NELEC=2,MS2=0,ORBSYM=1,1,ISYM=1,&END\n"
                "0.0 0 0 0 0\n",
                encoding="ascii",
            )
            determinants.write_text("10\n01\n", encoding="ascii")
            features = extract_input_features(
                fcidump, determinants, max_connectivity_pairs=2
            )
            estimate = estimate_source_memory(
                features,
                bit_length=2,
                max_block=1,
                iterations=1,
            )

        host_needed = (estimate.gpu_host_guard_bytes * 5 + 3) // 4
        vram_needed = (estimate.gpu_guard_bytes * 5 + 3) // 4
        self.assertTrue(
            candidate_memory_feasible(
                "gpu",
                estimate,
                free_host_bytes=host_needed,
                free_vram_bytes=vram_needed,
            )
        )
        self.assertFalse(
            candidate_memory_feasible(
                "gpu",
                estimate,
                free_host_bytes=host_needed - 1,
                free_vram_bytes=vram_needed,
            )
        )
        self.assertTrue(
            host_memory_feasible(estimate.host_guard_bytes, 10 * GIB)
        )
        with self.assertRaises(FeatureError):
            candidate_memory_feasible(
                "gpu", estimate, free_host_bytes=10 * GIB
            )
        with self.assertRaises(FeatureError):
            candidate_memory_feasible(
                "other", estimate, free_host_bytes=10 * GIB
            )


if __name__ == "__main__":
    unittest.main()
