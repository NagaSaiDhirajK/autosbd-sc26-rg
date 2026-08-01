from __future__ import annotations

from pathlib import Path
import tempfile
import textwrap
import unittest

from autosbd.config import (
    CandidateConfig,
    ConfigError,
    ProtocolConfig,
    SolverConfig,
    SweepConfig,
    WorkloadConfig,
    enumerate_trials,
    load_sweep_config,
)


class ConfigTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.inputs = self.root / "inputs"
        self.bin = self.root / "bin"
        self.inputs.mkdir()
        self.bin.mkdir()
        for path in (
            self.inputs / "FCIDUMP",
            self.inputs / "alpha.txt",
            self.inputs / "beta.txt",
            self.inputs / "FCIDUMP-2",
            self.inputs / "alpha-2.txt",
            self.bin / "sbd_cpu",
            self.bin / "sbd_gpu",
        ):
            path.write_text("fixture\n", encoding="utf-8")

    def write_config(self, body: str, name: str = "sweep.yaml") -> Path:
        path = self.root / name
        path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
        return path

    def valid_yaml(self) -> str:
        return """
            schema_version: 1
            name: smoke
            workloads:
              - name: fe4s4-small
                fcidump: inputs/FCIDUMP
                adetfile: inputs/alpha.txt
                bdetfile: inputs/beta.txt
              - name: fe4s4-larger
                fcidump: inputs/FCIDUMP-2
                adetfile: inputs/alpha-2.txt
            candidates:
              - name: cpu-1
                backend: cpu
                executable: bin/sbd_cpu
                threads: 1
                mpi_ranks: 1
                environment:
                  OMP_DYNAMIC: "false"
                  OMP_PLACES: cores
                compiler_flags: ["-O3", "-march=native"]
              - name: gpu-default
                backend: gpu
                executable: bin/sbd_gpu
                threads: 1
                mpi_ranks: 1
                environment:
                  OMP_TARGET_OFFLOAD: MANDATORY
              - name: mock-success
                backend: mock
                mock_argv: [python3, tests/fixtures/mock_sbd.py, success]
                estimated_gpu_memory_override_bytes: 4096
            solver:
              method: 0
              iteration: 6
              block: 10
              tolerance: 1e-8
              max_time: 240
              bit_length: 20
              shuffle: 0
              rdm: 0
              adet_comm_size: 1
              bdet_comm_size: 1
              task_comm_size: 1
            protocol:
              warmups: 1
              repetitions: 2
              timeout_s: 300
              seed: 1729
              purpose: correctness
              correctness_validated: false
        """

    def valid_v2_yaml(self) -> str:
        body = self.valid_yaml().replace("schema_version: 1", "schema_version: 2", 1)
        body = body.replace(
            "- name: fe4s4-small\n                fcidump:",
            "- name: fe4s4-small\n"
            "                family_id: fe4s4\n"
            "                molecule: Fe4S4\n"
            "                basis: documented-fixture-basis\n"
            "                fcidump:",
            1,
        )
        body = body.replace(
            "- name: fe4s4-larger\n                fcidump:",
            "- name: fe4s4-larger\n"
            "                family_id: fe4s4\n"
            "                molecule: Fe4S4\n"
            "                basis: documented-fixture-basis\n"
            "                fcidump:",
            1,
        )
        return body

    def test_loads_resolved_paths_and_preserves_source_names(self) -> None:
        config_path = self.write_config(self.valid_yaml())
        config = load_sweep_config(config_path)

        self.assertEqual(config.name, "smoke")
        self.assertEqual(config.schema_version, 1)
        self.assertEqual(config.source_path, config_path.resolve())
        self.assertEqual(len(config.workloads), 2)
        workload = config.workloads[0]
        self.assertEqual(workload.fcidump, (self.inputs / "FCIDUMP").resolve())
        self.assertEqual(workload.adetfile, (self.inputs / "alpha.txt").resolve())
        self.assertEqual(workload.bdetfile, (self.inputs / "beta.txt").resolve())
        self.assertEqual(workload.semantic_input_names["fcidump"], "inputs/FCIDUMP")
        self.assertEqual(workload.semantic_input_names["adetfile"], "inputs/alpha.txt")
        self.assertEqual(workload.semantic_input_names["bdetfile"], "inputs/beta.txt")

        cpu = config.candidates[0]
        self.assertEqual(cpu.executable, (self.bin / "sbd_cpu").resolve())
        self.assertEqual(cpu.base_argv, (str((self.bin / "sbd_cpu").resolve()),))
        self.assertEqual(cpu.environment["OMP_PLACES"], "cores")
        self.assertEqual(cpu.compiler_flags, ("-O3", "-march=native"))
        mock = config.candidates[2]
        self.assertEqual(mock.base_argv[-1], "success")
        self.assertEqual(mock.estimated_gpu_memory_override_bytes, 4096)
        self.assertEqual(config.protocol.purpose, "correctness")
        self.assertFalse(config.protocol.correctness_validated)
        self.assertFalse(ProtocolConfig().correctness_validated)

    def test_schema_v1_remains_default_and_schema_v2_requires_metadata(self) -> None:
        implicit_v1 = self.valid_yaml().replace("schema_version: 1\n", "", 1)
        implicit = load_sweep_config(self.write_config(implicit_v1, "implicit.yaml"))
        self.assertEqual(implicit.schema_version, 1)
        self.assertIsNone(implicit.workloads[0].family_id)

        v2 = load_sweep_config(self.write_config(self.valid_v2_yaml(), "v2.yaml"))
        self.assertEqual(v2.schema_version, 2)
        self.assertEqual(v2.workloads[0].family_id, "fe4s4")
        self.assertEqual(v2.workloads[0].molecule, "Fe4S4")
        self.assertEqual(v2.workloads[0].basis, "documented-fixture-basis")

        missing_basis = self.valid_v2_yaml().replace(
            "                basis: documented-fixture-basis\n", "", 1
        )
        with self.assertRaisesRegex(ConfigError, "missing required keys"):
            load_sweep_config(self.write_config(missing_basis, "missing-basis.yaml"))

    def test_schema_v2_rejects_invalid_or_inconsistent_family_metadata(self) -> None:
        invalid_cases = (
            (
                "uppercase-family",
                self.valid_v2_yaml().replace("family_id: fe4s4", "family_id: Fe4S4", 1),
                "lowercase ASCII slug",
            ),
            (
                "blank-molecule",
                self.valid_v2_yaml().replace("molecule: Fe4S4", 'molecule: "   "', 1),
                "nonempty string",
            ),
            (
                "padded-basis",
                self.valid_v2_yaml().replace(
                    "basis: documented-fixture-basis",
                    'basis: " documented-fixture-basis"',
                    1,
                ),
                "surrounding whitespace",
            ),
            (
                "inconsistent-family",
                self.valid_v2_yaml().replace("molecule: Fe4S4", "molecule: Other", 1),
                "inconsistent molecule/basis",
            ),
        )
        for label, body, message in invalid_cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ConfigError, message):
                    load_sweep_config(self.write_config(body, f"{label}.yaml"))

        v1_with_metadata = self.valid_yaml().replace(
            "- name: fe4s4-small\n                fcidump:",
            "- name: fe4s4-small\n"
            "                family_id: fe4s4\n"
            "                molecule: Fe4S4\n"
            "                basis: documented-fixture-basis\n"
            "                fcidump:",
            1,
        )
        with self.assertRaisesRegex(ConfigError, "unknown keys"):
            load_sweep_config(self.write_config(v1_with_metadata, "v1-metadata.yaml"))

    def test_unknown_keys_and_duplicate_yaml_keys_are_rejected(self) -> None:
        cases = {
            "root": self.valid_yaml() + "unexpected: true\n",
            "workload": self.valid_yaml().replace(
                "adetfile: inputs/alpha.txt",
                "adetfile: inputs/alpha.txt\n        mystery: 1",
                1,
            ),
            "candidate": self.valid_yaml().replace(
                "threads: 1", "threads: 1\n        mystery: 1", 1
            ),
            "solver_init": self.valid_yaml().replace(
                "method: 0", "method: 0\n      init: 0", 1
            ),
            "protocol": self.valid_yaml().replace(
                "seed: 1729", "seed: 1729\n      mystery: 1", 1
            ),
            "duplicate": self.valid_yaml().replace(
                "warmups: 1", "warmups: 1\n      warmups: 2", 1
            ),
        }
        for label, contents in cases.items():
            with self.subTest(label=label):
                path = self.write_config(contents, f"{label}.yaml")
                with self.assertRaises(ConfigError):
                    load_sweep_config(path)

    def test_solver_v1_whitelist_and_positive_fields(self) -> None:
        invalid_overrides = (
            {"method": 1},
            {"rdm": 1},
            {"shuffle": 2},
            {"iteration": 0},
            {"block": 0},
            {"tolerance": 0},
            {"tolerance": float("nan")},
            {"max_time": 0},
            {"bit_length": 0},
            {"bit_length": 65},
            {"carryover_ratio": 0},
            {"carryover_ratio": 1.01},
            {"adet_comm_size": 0},
            {"bdet_comm_size": 0},
            {"task_comm_size": 0},
        )
        defaults = {
            "method": 0,
            "iteration": 6,
            "block": 10,
            "tolerance": 1.0e-8,
            "max_time": 240,
            "bit_length": 20,
            "shuffle": 0,
            "carryover_ratio": 0.5,
            "rdm": 0,
            "adet_comm_size": 1,
            "bdet_comm_size": 1,
            "task_comm_size": 1,
        }
        for override in invalid_overrides:
            with self.subTest(override=override):
                with self.assertRaises(ConfigError):
                    SolverConfig(**(defaults | override))

        solver = SolverConfig(**defaults)
        argv = solver.amd_cli_args()
        self.assertNotIn("--init", argv)
        self.assertIn("--carryover_ratio", argv)
        self.assertEqual(argv[argv.index("--carryover_ratio") + 1], "0.5")
        self.assertEqual(argv[argv.index("--method") + 1], "0")
        self.assertEqual(solver.h_comm_size(1), 1)

        with self.assertRaises(ConfigError):
            ProtocolConfig(purpose="benchmark")
        with self.assertRaisesRegex(ConfigError, "requires validation_manifest"):
            ProtocolConfig(correctness_validated=True)

    def test_candidate_and_cross_candidate_validation(self) -> None:
        gpu_path = self.bin / "sbd_gpu"
        with self.assertRaisesRegex(ConfigError, "backend must be a string"):
            CandidateConfig(name="bad-backend", backend=[])  # type: ignore[arg-type]
        with self.assertRaisesRegex(ConfigError, "exactly one MPI rank"):
            CandidateConfig(
                name="gpu-two-ranks", backend="gpu", executable=gpu_path, mpi_ranks=2
            )
        with self.assertRaisesRegex(ConfigError, "requires executable"):
            CandidateConfig(name="cpu-missing", backend="cpu")
        with self.assertRaisesRegex(ConfigError, "requires nonempty mock_argv"):
            CandidateConfig(name="mock-missing", backend="mock")
        with self.assertRaisesRegex(ConfigError, "restricted to mock"):
            CandidateConfig(
                name="cpu-override",
                backend="cpu",
                executable=self.bin / "sbd_cpu",
                estimated_gpu_memory_override_bytes=1,
            )
        empty_environment = CandidateConfig(
            name="empty-env",
            backend="mock",
            mock_argv=("true",),
            environment={"CUDA_VISIBLE_DEVICES": ""},
        )
        self.assertEqual(empty_environment.environment["CUDA_VISIBLE_DEVICES"], "")

        workload = WorkloadConfig(
            name="tiny",
            fcidump=self.inputs / "FCIDUMP",
            adetfile=self.inputs / "alpha.txt",
        )
        candidate = CandidateConfig(
            name="cpu-1", backend="cpu", executable=self.bin / "sbd_cpu", mpi_ranks=3
        )
        solver = SolverConfig(adet_comm_size=2)
        with self.assertRaisesRegex(ConfigError, "does not divide"):
            SweepConfig(
                name="bad-communicators",
                workloads=(workload,),
                candidates=(candidate,),
                solver=solver,
            )

    def test_trial_enumeration_is_complete_grouped_and_deterministic(self) -> None:
        config = load_sweep_config(self.write_config(self.valid_yaml()))
        first = config.trial_templates()
        second = enumerate_trials(config)
        ordered = config.trial_templates(randomize=False)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 2 * 3 * (1 + 2))
        self.assertEqual(
            {(trial.phase, trial.repetition) for trial in first},
            {("warmup", 0), ("measured", 0), ("measured", 1)},
        )
        self.assertTrue(all(trial.warmup_or_measured == trial.phase for trial in first))
        self.assertEqual(
            [trial.candidate.name for trial in ordered[:3]],
            ["cpu-1", "gpu-default", "mock-success"],
        )
        self.assertEqual(
            [trial.workload.name for trial in ordered[:6]],
            ["fe4s4-small"] * 3 + ["fe4s4-larger"] * 3,
        )

        for phase, count in (("warmup", 1), ("measured", 2)):
            for repetition in range(count):
                for workload in config.workloads:
                    group = [
                        trial
                        for trial in first
                        if trial.phase == phase
                        and trial.repetition == repetition
                        and trial.workload == workload
                    ]
                    self.assertCountEqual(
                        [trial.candidate.name for trial in group],
                        [candidate.name for candidate in config.candidates],
                    )

        changed_seed = SweepConfig(
            name=config.name,
            workloads=config.workloads,
            candidates=config.candidates,
            solver=config.solver,
            protocol=ProtocolConfig(
                warmups=config.protocol.warmups,
                repetitions=config.protocol.repetitions,
                timeout_s=config.protocol.timeout_s,
                seed=1730,
            ),
        )
        first_order = [trial.semantic_key for trial in first]
        changed_order = [trial.semantic_key for trial in changed_seed.trial_templates()]
        self.assertNotEqual(first_order, changed_order)

    def test_duplicate_semantic_names_are_rejected(self) -> None:
        workload = WorkloadConfig(
            name="same",
            fcidump=self.inputs / "FCIDUMP",
            adetfile=self.inputs / "alpha.txt",
        )
        candidate = CandidateConfig(name="mock", backend="mock", mock_argv=("true",))
        with self.assertRaisesRegex(ConfigError, "duplicate workload names"):
            SweepConfig(
                name="duplicates",
                workloads=(workload, workload),
                candidates=(candidate,),
            )


if __name__ == "__main__":
    unittest.main()
