"""End-to-end tests for one immutable AutoSBD trial."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from autosbd.config import (
    CandidateConfig,
    ProtocolConfig,
    SolverConfig,
    SweepConfig,
    TrialTemplate,
    WorkloadConfig,
)
from autosbd.features import extract_input_features
from autosbd.records import load_record, make_trial_id, validate_record
from autosbd.runner import (
    NodeBusyError,
    NodeRunLock,
    OFFICIAL_UPSTREAM_URL,
    RunnerError,
    TrialRunner,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MOCK_SBD = REPOSITORY_ROOT / "tests" / "fixtures" / "mock_sbd.py"
REFERENCE_ENERGY = -326.6982536731583
PROJECT_COMMIT = "1" * 40
UPSTREAM_COMMIT = "729cfa3a5011fb805eb9e686a7711f6919836dcb"


class TrialRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)
        self.project_root = self.root / "project"
        self.upstream_root = self.root / "amd-sbd"
        self.results_dir = self.project_root / "results" / "raw"
        self.logs_dir = self.project_root / "logs" / "trials"
        self.input_dir = self.project_root / "inputs"
        for directory in (
            self.project_root,
            self.upstream_root,
            self.input_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self.fcidump = self.input_dir / "FCIDUMP"
        orbital_symmetries = ",".join("1" for _ in range(36))
        self.fcidump.write_text(
            "&FCI NORB=36,NELEC=2,MS2=0,\n"
            f" ORBSYM={orbital_symmetries},\n"
            " ISYM=1,\n"
            "/\n"
            " 1.0000000000000000 1 1 1 1\n"
            " 0.0000000000000000 0 0 0 0\n",
            encoding="ascii",
        )
        self.determinants = self.input_dir / "AlphaDets.txt"
        self.determinants.write_text("1" + "0" * 35 + "\n", encoding="ascii")
        self.workload = WorkloadConfig(
            name="tiny-36",
            fcidump=self.fcidump,
            adetfile=self.determinants,
        )
        self.solver = SolverConfig(iteration=1, block=1, tolerance=1.0e-8)
        self.invocation_counter = self.root / "invocations.log"
        self.preflight = {
            "load_average_1m": 0.0,
            "host_memory_available_bytes": 16 * 1024**3,
            "host_memory_cap_bytes": 12 * 1024**3,
            "gpu": None,
            "gpu_compute_processes": [],
            "gpu_process_query_ok": True,
            "gpu_idle": None,
            "gpu_memory_cap_bytes": None,
            "gpu_memory_policy": None,
        }
        system_snapshot = {
            "hostname": "runner-test-host",
            "cpu_model": "runner-test-cpu",
            "physical_cores": 4,
            "logical_cpus": 8,
            "gpu": None,
            "cuda_toolkit_version": "test-cuda",
            "machine_fingerprint": "f" * 64,
        }

        def fake_git_state(path: Path, **_kwargs: object) -> dict[str, object]:
            resolved = Path(path).resolve()
            if resolved == self.upstream_root.resolve():
                return {
                    "commit": UPSTREAM_COMMIT,
                    "dirty": False,
                    "url": OFFICIAL_UPSTREAM_URL,
                }
            return {
                "commit": PROJECT_COMMIT,
                "dirty": False,
                "url": "https://example.invalid/autosbd-test",
            }

        patchers = (
            patch("autosbd.runner.git_state", side_effect=fake_git_state),
            patch(
                "autosbd.runner.static_system_snapshot",
                return_value=system_snapshot,
            ),
            patch(
                "autosbd.runner.dynamic_preflight",
                side_effect=lambda: copy.deepcopy(self.preflight),
            ),
        )
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        self.runner = TrialRunner(
            project_root=self.project_root,
            results_dir=self.results_dir,
            logs_dir=self.logs_dir,
            upstream_root=self.upstream_root,
            cuda_toolkit_version="test-cuda",
            compiler_identity="test nvc++ 26.5",
        )

    def mock_candidate(
        self,
        mode: str,
        *,
        memory_override: int | None = None,
        extra_arguments: tuple[str, ...] = (),
        solver_overrides: dict[str, int] | None = None,
    ) -> CandidateConfig:
        return CandidateConfig(
            name=f"mock-{mode}",
            backend="mock",
            mock_argv=(
                sys.executable,
                str(MOCK_SBD),
                mode,
                "--invocation-counter",
                str(self.invocation_counter),
                *extra_arguments,
            ),
            solver_overrides={} if solver_overrides is None else solver_overrides,
            estimated_gpu_memory_override_bytes=memory_override,
        )

    def trial(
        self,
        candidate: CandidateConfig,
        *,
        timeout_s: float = 2.0,
        correctness_validated: bool = False,
        purpose: str = "test",
        warmups: int = 0,
        validation_manifest: Path | None = None,
        phase: str = "measured",
        workload: WorkloadConfig | None = None,
        schema_version: int = 1,
    ) -> tuple[SweepConfig, TrialTemplate]:
        selected_workload = self.workload if workload is None else workload
        config = SweepConfig(
            name="runner-test",
            workloads=(selected_workload,),
            candidates=(candidate,),
            solver=self.solver,
            protocol=ProtocolConfig(
                warmups=warmups,
                repetitions=1,
                timeout_s=timeout_s,
                seed=17,
                purpose=purpose,
                correctness_validated=correctness_validated,
                validation_manifest=validation_manifest,
            ),
            schema_version=schema_version,
        )
        template = TrialTemplate(
            sweep_name=config.name,
            workload=selected_workload,
            candidate=candidate,
            solver=self.solver,
            phase=phase,
            repetition=0,
        )
        return config, template

    def make_runner_with_git_state(
        self,
        *,
        project_dirty: bool = False,
        upstream_commit: str = UPSTREAM_COMMIT,
        upstream_url: str = OFFICIAL_UPSTREAM_URL,
    ) -> TrialRunner:
        def git_state_for_test(
            path: Path, **_kwargs: object
        ) -> dict[str, object]:
            if Path(path).resolve() == self.upstream_root.resolve():
                return {
                    "commit": upstream_commit,
                    "dirty": False,
                    "url": upstream_url,
                }
            return {
                "commit": PROJECT_COMMIT,
                "dirty": project_dirty,
                "url": "https://example.invalid/autosbd-test",
            }

        with patch("autosbd.runner.git_state", side_effect=git_state_for_test):
            return TrialRunner(
                project_root=self.project_root,
                results_dir=self.results_dir,
                logs_dir=self.logs_dir,
                upstream_root=self.upstream_root,
                cuda_toolkit_version="test-cuda",
                compiler_identity="test nvc++ 26.5",
            )

    def solver_identity(
        self, solver: SolverConfig | None = None
    ) -> dict[str, object]:
        solver = self.solver if solver is None else solver
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

    def write_validation_manifest(
        self,
        candidate: CandidateConfig,
        label: str,
        *,
        candidate_artifact_sha256: str | None = None,
        input_sha256: str | None = None,
        solver: dict[str, object] | None = None,
    ) -> Path:
        features = extract_input_features(self.fcidump, self.determinants)
        artifact_sha256 = hashlib.sha256(
            "\0".join(candidate.mock_argv).encode()
        ).hexdigest()
        manifest = {
            "passed": True,
            "upstream_url": OFFICIAL_UPSTREAM_URL,
            "upstream_git_commit": UPSTREAM_COMMIT,
            "input_sha256": (
                features.combined_input_sha256
                if input_sha256 is None
                else input_sha256
            ),
            "solver": self.solver_identity() if solver is None else solver,
            "candidate_artifacts": [
                {
                    "backend": candidate.backend,
                    "sha256": (
                        artifact_sha256
                        if candidate_artifact_sha256 is None
                        else candidate_artifact_sha256
                    ),
                }
            ],
        }
        path = self.root / f"{label}.validation.json"
        path.write_text(
            json.dumps(manifest, allow_nan=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def write_validation_manifest_v2(
        self,
        candidate: CandidateConfig,
        label: str,
        validated_inputs: list[dict[str, object]],
        *,
        candidate_artifact_sha256: str | None = None,
        candidate_backend: str | None = None,
        allow_nan: bool = False,
        schema_version: int = 2,
    ) -> Path:
        artifact_sha256 = hashlib.sha256(
            "\0".join(candidate.mock_argv).encode()
        ).hexdigest()
        manifest = {
            "schema_version": schema_version,
            "passed": True,
            "upstream_url": OFFICIAL_UPSTREAM_URL,
            "upstream_git_commit": UPSTREAM_COMMIT,
            "validated_inputs": validated_inputs,
            "candidate_artifacts": [
                {
                    "backend": (
                        candidate.backend
                        if candidate_backend is None
                        else candidate_backend
                    ),
                    "sha256": (
                        artifact_sha256
                        if candidate_artifact_sha256 is None
                        else candidate_artifact_sha256
                    ),
                }
            ],
        }
        path = self.root / f"{label}.validation.json"
        path.write_text(
            json.dumps(
                manifest,
                allow_nan=allow_nan,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def run_mock(
        self,
        mode: str,
        *,
        timeout_s: float = 2.0,
        attempt_index: int = 0,
        memory_override: int | None = None,
        extra_arguments: tuple[str, ...] = (),
    ):
        candidate = self.mock_candidate(
            mode,
            memory_override=memory_override,
            extra_arguments=extra_arguments,
        )
        config, template = self.trial(candidate, timeout_s=timeout_s)
        return self.runner.run(
            template,
            config=config,
            attempt_index=attempt_index,
            reference_value=REFERENCE_ENERGY,
        )

    def assert_durable_valid_record(self, result) -> dict[str, object]:
        self.assertTrue(result.record_path.is_file())
        validate_record(result.record)
        loaded = load_record(result.record_path)
        self.assertEqual(loaded, result.record)
        return loaded

    def test_success_is_schema_valid_and_not_timing_eligible(self) -> None:
        result = self.run_mock("success")
        record = self.assert_durable_valid_record(result)

        self.assertTrue(result.launched)
        self.assertFalse(result.reused)
        self.assertEqual(record["status"], "success")
        self.assertTrue(record["process_success"])
        self.assertTrue(record["scientific_success"])
        self.assertFalse(record["timing_eligible"])
        self.assertTrue(record["correct"])
        self.assertEqual(record["relative_error"], 0.0)
        self.assertEqual(record["energy_or_eigenvalue"], REFERENCE_ENERGY)

    def test_exit_zero_nonconvergence_is_a_scientific_failure(self) -> None:
        result = self.run_mock("nonconverged")
        record = self.assert_durable_valid_record(result)

        self.assertEqual(record["exit_code"], 0)
        self.assertTrue(record["process_success"])
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["failure_kind"], "not_converged")
        self.assertFalse(record["scientific_success"])
        self.assertFalse(record["timing_eligible"])

    def test_nonzero_exit_is_a_durable_process_failure(self) -> None:
        result = self.run_mock("fail")
        record = self.assert_durable_valid_record(result)

        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["failure_kind"], "nonzero_exit")
        self.assertEqual(record["exit_code"], 17)
        self.assertFalse(record["process_success"])
        self.assertFalse(record["scientific_success"])

    def test_timeout_writes_a_terminal_record_and_preserves_artifacts(self) -> None:
        result = self.run_mock(
            "timeout",
            timeout_s=0.2,
            extra_arguments=("--sleep-seconds", "30"),
        )
        record = self.assert_durable_valid_record(result)

        self.assertEqual(record["status"], "timeout")
        self.assertEqual(record["failure_kind"], "timeout")
        self.assertTrue(record["timeout"])
        self.assertFalse(record["process_success"])
        self.assertTrue(record["resource_monitoring"]["term_sent"])
        for field in ("stdout_log", "stderr_log"):
            self.assertTrue((self.project_root / record[field]).is_file())

    def test_explicit_out_of_memory_evidence_is_classified_as_oom(self) -> None:
        result = self.run_mock("oom")
        record = self.assert_durable_valid_record(result)

        self.assertEqual(record["status"], "oom")
        self.assertEqual(record["failure_kind"], "oom_evidence")
        self.assertTrue(record["oom"])
        self.assertEqual(record["exit_code"], 42)

    def test_memory_skip_records_without_launching(self) -> None:
        self.preflight["gpu_memory_cap_bytes"] = 1024
        candidate = self.mock_candidate("success", memory_override=1025)
        config, template = self.trial(candidate)

        with patch("autosbd.runner.run_monitored") as monitored:
            result = self.runner.run(
                template,
                config=config,
                reference_value=REFERENCE_ENERGY,
            )

        record = self.assert_durable_valid_record(result)
        monitored.assert_not_called()
        self.assertFalse(result.launched)
        self.assertEqual(record["status"], "skipped_memory")
        self.assertEqual(record["failure_kind"], "skipped_memory")
        self.assertIsNotNone(record["skip_reason"])
        self.assertIsNone(record["exit_code"])
        self.assertFalse(self.invocation_counter.exists())

    def test_exact_rerun_reuses_record_but_new_attempt_gets_new_id(self) -> None:
        candidate = self.mock_candidate("success")
        config, template = self.trial(candidate)
        first = self.runner.run(
            template,
            config=config,
            attempt_index=0,
            reference_value=REFERENCE_ENERGY,
        )
        original_bytes = first.record_path.read_bytes()

        reused = self.runner.run(
            template,
            config=config,
            attempt_index=0,
            reference_value=REFERENCE_ENERGY,
        )
        second_attempt = self.runner.run(
            template,
            config=config,
            attempt_index=1,
            reference_value=REFERENCE_ENERGY,
        )

        self.assertFalse(first.reused)
        self.assertTrue(reused.reused)
        self.assertFalse(reused.launched)
        self.assertEqual(reused.record_path, first.record_path)
        self.assertEqual(first.record_path.read_bytes(), original_bytes)
        self.assertNotEqual(second_attempt.record_path, first.record_path)
        self.assertNotEqual(
            second_attempt.record["trial_id"], first.record["trial_id"]
        )
        self.assertEqual(
            second_attempt.record["logical_trial_id"],
            first.record["logical_trial_id"],
        )
        self.assertEqual(second_attempt.record["attempt_index"], 1)
        self.assertEqual(
            self.invocation_counter.read_text(encoding="utf-8").splitlines(),
            ["success", "success"],
        )

    def test_real_candidate_uses_whitelisted_amd_command_and_provenance(self) -> None:
        build_directory = (
            self.project_root
            / "build"
            / "upstream"
            / "amd-729cfa3a-test"
        )
        build_directory.mkdir(parents=True)
        executable = build_directory / "diag_cpu"
        executable.write_bytes(MOCK_SBD.read_bytes())
        executable.chmod(0o755)
        expected_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
        candidate = CandidateConfig(
            name="amd-cpu-test",
            backend="cpu",
            executable=executable,
            threads=2,
            compiler_flags=(
                "-O3",
                "-mp",
                "-DSBD_TRADMODE",
                "-DUSE_DET_CACHE_OMP",
            ),
        )
        config, template = self.trial(candidate)
        with patch.dict(
            "autosbd.runner.OFFICIAL_BUILD_SHA256", {"cpu": expected_hash}
        ):
            result = self.runner.run(
                template,
                config=config,
                reference_value=REFERENCE_ENERGY,
            )
        record = self.assert_durable_valid_record(result)

        command = record["command"]
        self.assertEqual(command[0], str(executable.resolve()))
        self.assertNotIn("--init", command)
        self.assertNotIn("--bdetfile", command)
        self.assertIn("--fcidump", command)
        self.assertIn("--adetfile", command)
        self.assertIn("--method", command)
        self.assertEqual(record["upstream_url"], OFFICIAL_UPSTREAM_URL)
        self.assertEqual(record["upstream_git_commit"], UPSTREAM_COMMIT)
        self.assertEqual(record["project_git_commit"], PROJECT_COMMIT)
        self.assertTrue(record["official_upstream_primary"])
        self.assertEqual(record["environment_overrides"]["OMP_NUM_THREADS"], "2")
        self.assertEqual(
            record["environment_overrides"]["OMP_TARGET_OFFLOAD"], "DISABLED"
        )

    def test_node_lock_contention_raises_without_invocation(self) -> None:
        candidate = self.mock_candidate("success")
        config, template = self.trial(candidate)

        with NodeRunLock(self.runner.node_lock_path, {"owner": "test"}):
            with self.assertRaises(NodeBusyError) as caught:
                self.runner.run(
                    template,
                    config=config,
                    reference_value=REFERENCE_ENERGY,
                )

        self.assertIsInstance(caught.exception, RunnerError)
        self.assertFalse(self.invocation_counter.exists())
        self.assertEqual(list(self.results_dir.glob("*.json")), [])
        self.assertEqual(list(self.results_dir.glob("*.claim")), [])

    def test_input_mutation_before_launch_is_recorded_without_invocation(self) -> None:
        candidate = self.mock_candidate("success")
        config, template = self.trial(candidate)
        original_rehash = self.runner._rehash_inputs
        rehash_calls = 0

        def mutate_then_rehash(trial_template: TrialTemplate):
            nonlocal rehash_calls
            rehash_calls += 1
            if rehash_calls == 1:
                with self.fcidump.open("a", encoding="ascii") as stream:
                    stream.write("\n")
            return original_rehash(trial_template)

        with (
            patch.object(
                self.runner,
                "_rehash_inputs",
                side_effect=mutate_then_rehash,
            ),
            patch("autosbd.runner.run_monitored") as monitored,
        ):
            result = self.runner.run(
                template,
                config=config,
                reference_value=REFERENCE_ENERGY,
            )

        record = self.assert_durable_valid_record(result)
        monitored.assert_not_called()
        self.assertFalse(result.launched)
        self.assertEqual(record["status"], "skipped_invalid")
        self.assertEqual(
            record["failure_kind"], "input_changed_before_launch"
        )
        self.assertFalse(record["input_integrity"]["unchanged_before_launch"])
        self.assertFalse(record["input_integrity"]["unchanged_after_run"])
        self.assertFalse(record["preflight"]["input_unchanged_before_launch"])
        self.assertFalse(self.invocation_counter.exists())

    def test_run_artifacts_and_logical_identity_self_verify(self) -> None:
        result = self.run_mock("success")
        record = self.assert_durable_valid_record(result)

        self.assertEqual(record["schema_version"], 2)
        self.assertIn(
            "gpu_process_observed", record["resource_monitoring"]
        )
        self.assertIsNone(record["resource_monitoring"]["gpu_process_observed"])
        self.assertEqual(
            set(record["run_artifacts"]), {"stdout", "stderr", "resources"}
        )
        for artifact in record["run_artifacts"].values():
            path = self.project_root / artifact["path"]
            payload = path.read_bytes()
            self.assertEqual(artifact["size_bytes"], len(payload))
            self.assertEqual(
                artifact["sha256"], hashlib.sha256(payload).hexdigest()
            )

        self.assertEqual(
            record["logical_trial_id"],
            make_trial_id(record["logical_identity"]),
        )
        self.assertEqual(
            record["trial_id"],
            make_trial_id(
                {
                    "logical_trial_id": record["logical_trial_id"],
                    "attempt_index": record["attempt_index"],
                }
            ),
        )

    def test_config_v2_emits_schema_v3_with_bound_family_metadata(self) -> None:
        candidate = self.mock_candidate("success")
        workload = WorkloadConfig(
            name="tiny-36-family",
            fcidump=self.fcidump,
            adetfile=self.determinants,
            family_id="fixture",
            molecule="Fixture",
            basis="fixture-basis",
        )
        config, template = self.trial(
            candidate, workload=workload, schema_version=2
        )
        record = self.assert_durable_valid_record(
            self.runner.run(template, config=config, reference_value=REFERENCE_ENERGY)
        )

        self.assertEqual(record["schema_version"], 3)
        self.assertEqual(record["problem_family"], "runner-test")
        self.assertEqual(record["problem_instance"], workload.name)
        for field in ("family_id", "molecule", "basis"):
            self.assertEqual(record[field], getattr(workload, field))
            self.assertEqual(
                record["logical_identity"][field], getattr(workload, field)
            )

        changed_workload = WorkloadConfig(
            name=workload.name,
            fcidump=self.fcidump,
            adetfile=self.determinants,
            family_id="other-fixture",
            molecule="Other Fixture",
            basis="fixture-basis",
        )
        changed_config, changed_template = self.trial(
            candidate, workload=changed_workload, schema_version=2
        )
        changed_record = self.assert_durable_valid_record(
            self.runner.run(
                changed_template,
                config=changed_config,
                reference_value=REFERENCE_ENERGY,
            )
        )
        self.assertNotEqual(
            record["logical_trial_id"], changed_record["logical_trial_id"]
        )

    def test_unofficial_source_and_wrong_binary_hash_are_rejected(self) -> None:
        invalid_upstream_states = (
            (
                {"upstream_commit": "0" * 40},
                "official AMD pin required",
            ),
            (
                {"upstream_url": "https://example.invalid/not-amd-sbd"},
                "official AMD origin required",
            ),
        )
        for overrides, message in invalid_upstream_states:
            with self.subTest(message=message):
                with self.assertRaisesRegex(RunnerError, message):
                    self.make_runner_with_git_state(**overrides)

        build_directory = (
            self.project_root
            / "build"
            / "upstream"
            / "amd-729cfa3a-test"
        )
        build_directory.mkdir(parents=True)
        executable = build_directory / "diag_cpu"
        executable.write_bytes(MOCK_SBD.read_bytes())
        executable.chmod(0o755)
        candidate = CandidateConfig(
            name="amd-cpu-wrong-hash",
            backend="cpu",
            executable=executable,
            compiler_flags=(
                "-mp",
                "-DSBD_TRADMODE",
                "-DUSE_DET_CACHE_OMP",
            ),
        )
        config, template = self.trial(candidate)
        with (
            patch("autosbd.runner.run_monitored") as monitored,
            self.assertRaisesRegex(RunnerError, "artifact hash"),
        ):
            self.runner.run(
                template,
                config=config,
                reference_value=REFERENCE_ENERGY,
            )
        monitored.assert_not_called()

    def _referenced_workloads(self) -> tuple[WorkloadConfig, WorkloadConfig]:
        second_determinants = self.input_dir / "AlphaDets-second.txt"
        second_determinants.write_text(
            "0" + "1" + "0" * 34 + "\n", encoding="ascii"
        )
        return (
            WorkloadConfig(
                name="tiny-36-first",
                fcidump=self.fcidump,
                adetfile=self.determinants,
                reference_value=REFERENCE_ENERGY,
                reference_source="runner test fixture",
            ),
            WorkloadConfig(
                name="tiny-36-second",
                fcidump=self.fcidump,
                adetfile=second_determinants,
                reference_value=REFERENCE_ENERGY,
                reference_source="runner test fixture",
            ),
        )

    def _validated_input(
        self, workload: WorkloadConfig, solver: SolverConfig | None = None
    ) -> dict[str, object]:
        features = extract_input_features(workload.fcidump, workload.adetfile)
        return {
            "input_sha256": features.combined_input_sha256,
            "solver": self.solver_identity(solver),
            "reference_value": workload.reference_value,
        }

    def test_effective_candidate_solver_controls_template_membership_and_command(self) -> None:
        candidate = CandidateConfig(
            name="cpu-parameterized",
            backend="cpu",
            executable=MOCK_SBD,
            solver_overrides={"bit_length": 48, "shuffle": 1},
        )
        config = SweepConfig(
            name="runner-effective-solver",
            workloads=(self.workload,),
            candidates=(candidate,),
            solver=self.solver,
            protocol=ProtocolConfig(warmups=0, repetitions=1),
        )
        generated = config.trial_templates(randomize=False)[0]
        effective = candidate.resolved_solver(self.solver)
        self.assertEqual(generated.solver, effective)
        self.runner._validate_template_config(generated, config)

        command = self.runner._command(generated)
        self.assertEqual(command[command.index("--bit_length") + 1], "48")
        self.assertEqual(command[command.index("--shuffle") + 1], "1")

        mismatched = TrialTemplate(
            sweep_name=config.name,
            workload=self.workload,
            candidate=candidate,
            solver=self.solver,
            phase="measured",
            repetition=0,
        )
        with self.assertRaisesRegex(RunnerError, "does not belong"):
            self.runner._validate_template_config(mismatched, config)

    def test_schema_v2_v3_manifest_matches_input_and_exact_effective_solver(self) -> None:
        workload = WorkloadConfig(
            name="tiny-parameterized",
            fcidump=self.fcidump,
            adetfile=self.determinants,
            reference_value=REFERENCE_ENERGY,
            reference_source="runner test fixture",
            family_id="fixture",
            molecule="Fixture",
            basis="fixture-basis",
        )
        candidate = self.mock_candidate(
            "success", solver_overrides={"bit_length": 48, "shuffle": 1}
        )
        effective = candidate.resolved_solver(self.solver)
        base_entry = {
            **self._validated_input(workload, self.solver),
            "family_id": workload.family_id,
            "molecule": workload.molecule,
            "basis": workload.basis,
        }
        effective_entry = {
            **self._validated_input(workload, effective),
            "family_id": workload.family_id,
            "molecule": workload.molecule,
            "basis": workload.basis,
        }

        def evidence_for(
            entries: list[dict[str, object]], label: str, schema_version: int
        ) -> dict[str, object]:
            manifest = self.write_validation_manifest_v2(
                candidate,
                label,
                entries,
                schema_version=schema_version,
            )
            config = SweepConfig(
                name=f"runner-manifest-{label}",
                workloads=(workload,),
                candidates=(candidate,),
                solver=self.solver,
                protocol=ProtocolConfig(
                    warmups=1,
                    repetitions=1,
                    purpose="pilot",
                    correctness_validated=True,
                    validation_manifest=manifest,
                ),
                schema_version=2,
            )
            template = config.trial_templates(randomize=False)[0]
            features = extract_input_features(workload.fcidump, workload.adetfile)
            build = self.runner._build_description(candidate)
            return self.runner._validation_evidence(
                template, config, features, build
            )

        for schema_version in (2, 3):
            with self.subTest(schema_version=schema_version):
                valid = evidence_for(
                    [base_entry, effective_entry],
                    f"same-hash-distinct-solvers-v{schema_version}",
                    schema_version,
                )
                self.assertTrue(valid["valid"])
                self.assertEqual(valid["errors"], [])

        duplicate = evidence_for(
            [base_entry, effective_entry, copy.deepcopy(effective_entry)],
            "duplicate-effective-solver",
            2,
        )
        self.assertFalse(duplicate["valid"])
        self.assertIn(
            "manifest has duplicate matching validated inputs", duplicate["errors"]
        )

        missing = evidence_for([base_entry], "missing-effective-solver", 2)
        self.assertFalse(missing["valid"])
        self.assertIn(
            "manifest validated input solver settings mismatch", missing["errors"]
        )

    def test_schema_v2_manifest_validates_two_inputs(self) -> None:
        candidate = self.mock_candidate("success")
        workloads = self._referenced_workloads()
        validated_inputs = [
            self._validated_input(workload) for workload in workloads
        ]
        manifest = self.write_validation_manifest_v2(
            candidate, "v2-two-inputs", validated_inputs
        )

        for workload in workloads:
            with self.subTest(workload=workload.name):
                config, template = self.trial(
                    candidate,
                    purpose="pilot",
                    warmups=1,
                    correctness_validated=True,
                    validation_manifest=manifest,
                    workload=workload,
                )
                record = self.assert_durable_valid_record(
                    self.runner.run(template, config=config)
                )
                self.assertTrue(record["validation_evidence"]["valid"])
                self.assertEqual(record["validation_evidence"]["errors"], [])
                self.assertTrue(record["timing_eligible"])

    def test_config_v2_accepts_legacy_manifest_and_checks_v3_metadata(self) -> None:
        candidate = self.mock_candidate("success")
        workload = WorkloadConfig(
            name="tiny-v3-validated",
            fcidump=self.fcidump,
            adetfile=self.determinants,
            reference_value=REFERENCE_ENERGY,
            reference_source="runner test fixture",
            family_id="fixture",
            molecule="Fixture",
            basis="fixture-basis",
        )
        entry = self._validated_input(workload)

        legacy_manifest = self.write_validation_manifest_v2(
            candidate, "legacy-for-v3", [entry]
        )
        legacy_config, legacy_template = self.trial(
            candidate,
            purpose="pilot",
            warmups=1,
            correctness_validated=True,
            validation_manifest=legacy_manifest,
            workload=workload,
            schema_version=2,
        )
        legacy_record = self.assert_durable_valid_record(
            self.runner.run(legacy_template, config=legacy_config)
        )
        self.assertTrue(legacy_record["validation_evidence"]["valid"])
        self.assertTrue(legacy_record["timing_eligible"])

        v3_entry = {
            **entry,
            "family_id": workload.family_id,
            "molecule": workload.molecule,
            "basis": workload.basis,
        }
        v3_manifest = self.write_validation_manifest_v2(
            candidate, "v3-valid", [v3_entry], schema_version=3
        )
        v3_config, v3_template = self.trial(
            candidate,
            purpose="pilot",
            warmups=1,
            correctness_validated=True,
            validation_manifest=v3_manifest,
            workload=workload,
            schema_version=2,
        )
        v3_record = self.assert_durable_valid_record(
            self.runner.run(v3_template, config=v3_config)
        )
        self.assertTrue(v3_record["validation_evidence"]["valid"])

        bad_entry = {**v3_entry, "basis": "wrong-basis"}
        bad_manifest = self.write_validation_manifest_v2(
            candidate, "v3-bad", [bad_entry], schema_version=3
        )
        bad_config, bad_template = self.trial(
            candidate,
            purpose="pilot",
            warmups=1,
            correctness_validated=True,
            validation_manifest=bad_manifest,
            workload=workload,
            schema_version=2,
        )
        bad_record = self.assert_durable_valid_record(
            self.runner.run(bad_template, config=bad_config)
        )
        self.assertFalse(bad_record["validation_evidence"]["valid"])
        self.assertIn(
            "manifest validated input basis mismatch",
            bad_record["validation_evidence"]["errors"],
        )

    def test_schema_v2_manifest_rejects_invalid_input_bindings(self) -> None:
        candidate = self.mock_candidate("success")
        workload, other_workload = self._referenced_workloads()
        valid_entry = self._validated_input(workload)
        other_entry = self._validated_input(other_workload)

        duplicate_entries = [copy.deepcopy(valid_entry), copy.deepcopy(valid_entry)]
        wrong_solver = copy.deepcopy(valid_entry)
        wrong_solver["solver"] = {**self.solver_identity(), "block": 2}
        missing_reference = copy.deepcopy(valid_entry)
        missing_reference.pop("reference_value")
        nonfinite_reference = copy.deepcopy(valid_entry)
        nonfinite_reference["reference_value"] = float("nan")
        oversized_reference = copy.deepcopy(valid_entry)
        oversized_reference["reference_value"] = 10**400
        wrong_reference = copy.deepcopy(valid_entry)
        wrong_reference["reference_value"] = -1.0

        invalid_cases = (
            (
                "missing-input",
                [other_entry],
                {},
                "manifest has no matching validated input",
            ),
            (
                "duplicate-input",
                duplicate_entries,
                {},
                "manifest has duplicate matching validated inputs",
            ),
            (
                "wrong-solver-v2",
                [wrong_solver],
                {},
                "manifest validated input solver settings mismatch",
            ),
            (
                "missing-reference-v2",
                [missing_reference],
                {},
                "manifest validated input reference_value is missing or nonfinite",
            ),
            (
                "nonfinite-reference-v2",
                [nonfinite_reference],
                {"allow_nan": True},
                "manifest validated input reference_value is missing or nonfinite",
            ),
            (
                "oversized-reference-v2",
                [oversized_reference],
                {},
                "manifest validated input reference_value is missing or nonfinite",
            ),
            (
                "wrong-reference-v2",
                [wrong_reference],
                {},
                "manifest validated input reference_value mismatch",
            ),
            (
                "wrong-artifact-v2",
                [valid_entry],
                {"candidate_artifact_sha256": "0" * 64},
                "manifest has no matching backend artifact hash",
            ),
            (
                "wrong-backend-v2",
                [valid_entry],
                {"candidate_backend": "gpu"},
                "manifest has no matching backend artifact hash",
            ),
        )
        for label, entries, manifest_kwargs, expected_error in invalid_cases:
            with self.subTest(manifest_error=expected_error):
                manifest = self.write_validation_manifest_v2(
                    candidate,
                    label,
                    entries,
                    **manifest_kwargs,
                )
                config, template = self.trial(
                    candidate,
                    purpose="pilot",
                    warmups=1,
                    correctness_validated=True,
                    validation_manifest=manifest,
                    workload=workload,
                )
                record = self.assert_durable_valid_record(
                    self.runner.run(template, config=config)
                )
                self.assertFalse(record["validation_evidence"]["valid"])
                self.assertIn(
                    expected_error,
                    record["validation_evidence"]["errors"],
                )
                self.assertFalse(record["timing_eligible"])

    def test_timing_eligibility_requires_every_scientific_gate(self) -> None:
        candidate = self.mock_candidate("success")
        valid_manifest = self.write_validation_manifest(candidate, "valid")

        def run_case(
            *,
            purpose: str,
            warmups: int = 1,
            manifest: Path = valid_manifest,
            reference_value: float = REFERENCE_ENERGY,
            runner: TrialRunner = self.runner,
        ) -> dict[str, object]:
            config, template = self.trial(
                candidate,
                purpose=purpose,
                warmups=warmups,
                correctness_validated=True,
                validation_manifest=manifest,
            )
            result = runner.run(
                template,
                config=config,
                reference_value=reference_value,
            )
            return self.assert_durable_valid_record(result)

        for purpose in ("test", "correctness"):
            with self.subTest(purpose=purpose):
                record = run_case(purpose=purpose)
                self.assertTrue(record["validation_evidence"]["valid"])
                self.assertFalse(record["timing_eligible"])

        for purpose in ("pilot", "final"):
            with self.subTest(purpose=purpose):
                record = run_case(purpose=purpose)
                self.assertEqual(record["status"], "success")
                self.assertTrue(record["correct"])
                self.assertTrue(record["validation_evidence"]["valid"])
                self.assertFalse(record["project_git_dirty"])
                self.assertGreater(record["resource_monitoring"]["samples"], 0)
                self.assertTrue(record["timing_eligible"])

        no_warmup = run_case(purpose="pilot", warmups=0)
        self.assertFalse(no_warmup["timing_eligible"])

        wrong_reference = run_case(purpose="pilot", reference_value=-1.0)
        self.assertEqual(wrong_reference["failure_kind"], "reference_mismatch")
        self.assertFalse(wrong_reference["timing_eligible"])

        invalid_manifests = (
            (
                self.write_validation_manifest(
                    candidate,
                    "wrong-input",
                    input_sha256="0" * 64,
                ),
                "manifest input hash mismatch",
            ),
            (
                self.write_validation_manifest(
                    candidate,
                    "wrong-solver",
                    solver={**self.solver_identity(), "block": 2},
                ),
                "manifest solver settings mismatch",
            ),
            (
                self.write_validation_manifest(
                    candidate,
                    "wrong-artifact",
                    candidate_artifact_sha256="0" * 64,
                ),
                "manifest has no matching backend artifact hash",
            ),
        )
        for invalid_manifest, expected_error in invalid_manifests:
            with self.subTest(manifest_error=expected_error):
                invalid_evidence = run_case(
                    purpose="pilot", manifest=invalid_manifest
                )
                self.assertFalse(
                    invalid_evidence["validation_evidence"]["valid"]
                )
                self.assertIn(
                    expected_error,
                    invalid_evidence["validation_evidence"]["errors"],
                )
                self.assertFalse(invalid_evidence["timing_eligible"])

        dirty_runner = self.make_runner_with_git_state(project_dirty=True)
        dirty_project = run_case(purpose="pilot", runner=dirty_runner)
        self.assertTrue(dirty_project["project_git_dirty"])
        self.assertFalse(dirty_project["timing_eligible"])


if __name__ == "__main__":
    unittest.main()
