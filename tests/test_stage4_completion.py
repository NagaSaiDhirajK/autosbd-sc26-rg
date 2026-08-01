"""Tests for the fail-closed Stage 4 completion attestation."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from autosbd.completion import (
    CompletionError,
    build_stage4_completion,
    write_completion_manifest,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = REPOSITORY_ROOT / "reports" / "stage4_protocol.json"
AGGREGATE_PATH = REPOSITORY_ROOT / "results" / "processed" / "stage4_final.json"
RAW_DIR = REPOSITORY_ROOT / "results" / "raw"
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "build_stage4_completion.py"


class Stage4CompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.aggregate = json.loads(AGGREGATE_PATH.read_text(encoding="utf-8"))

    def build(self, **overrides: object) -> dict[str, object]:
        return build_stage4_completion(
            overrides.get("protocol", PROTOCOL_PATH),
            overrides.get("aggregate", AGGREGATE_PATH),
            overrides.get("raw_dir", RAW_DIR),
            repository_root=REPOSITORY_ROOT,
        )

    def write_json(self, directory: Path, name: str, value: object) -> Path:
        path = directory / name
        path.write_text(
            json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def copy_raw_records(self, destination: Path) -> None:
        destination.mkdir()
        for trial_id in self.aggregate["input_record_ids"]:
            shutil.copyfile(RAW_DIR / f"{trial_id}.json", destination / f"{trial_id}.json")

    def test_real_campaign_attests_exact_counts_views_and_artifacts(self) -> None:
        completion = self.build()
        self.assertEqual(completion["schema_version"], 1)
        self.assertEqual(completion["attestation_type"], "autosbd_stage4_completion")
        self.assertEqual(completion["status"], "complete")
        self.assertEqual(
            {
                key: completion["campaign_counts"][key]
                for key in (
                    "records",
                    "unique_trial_ids",
                    "unique_logical_trial_ids",
                    "warmup",
                    "measured",
                    "timing_eligible",
                    "success",
                    "correct",
                )
            },
            {
                "records": 48,
                "unique_trial_ids": 48,
                "unique_logical_trial_ids": 48,
                "warmup": 10,
                "measured": 38,
                "timing_eligible": 38,
                "success": 48,
                "correct": 48,
            },
        )
        self.assertEqual(
            {
                name: completion["analysis_views"][name]["record_count"]
                for name in (
                    "primary_final",
                    "balanced_broad_sensitivity",
                    "crossover",
                )
            },
            {
                "primary_final": 38,
                "balanced_broad_sensitivity": 30,
                "crossover": 20,
            },
        )
        artifacts = completion["source_artifacts"]["candidate_artifacts"]
        self.assertEqual({item["backend"] for item in artifacts}, {"cpu", "gpu"})
        self.assertTrue(
            all(set(item) == {"backend", "path", "sha256", "size_bytes"} for item in artifacts)
        )
        self.assertEqual(len(completion["records"]), 48)
        self.assertTrue(
            all(
                set(item["raw_record"]) == {"path", "sha256", "size_bytes"}
                for item in completion["records"]
            )
        )

    def test_atomic_output_is_changed_only_and_deterministic(self) -> None:
        completion = self.build()
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "nested" / "completion.json"
            self.assertTrue(write_completion_manifest(completion, output))
            first_bytes = output.read_bytes()
            os.utime(output, ns=(1_700_000_000_000_000_000,) * 2)
            first_mtime = output.stat().st_mtime_ns
            self.assertFalse(write_completion_manifest(completion, output))
            self.assertEqual(output.read_bytes(), first_bytes)
            self.assertEqual(output.stat().st_mtime_ns, first_mtime)

    def test_missing_raw_record_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            raw_dir = Path(temporary_directory) / "raw"
            self.copy_raw_records(raw_dir)
            missing = self.aggregate["input_record_ids"][0]
            (raw_dir / f"{missing}.json").unlink()
            with self.assertRaisesRegex(CompletionError, "cannot resolve raw record"):
                self.build(raw_dir=raw_dir)

    def test_duplicate_input_id_and_tampered_aggregate_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            duplicate = copy.deepcopy(self.aggregate)
            duplicate["input_record_ids"][-1] = duplicate["input_record_ids"][0]
            duplicate_path = self.write_json(root, "duplicate.json", duplicate)
            with self.assertRaisesRegex(CompletionError, "duplicate input record IDs"):
                self.build(aggregate=duplicate_path)

            tampered = copy.deepcopy(self.aggregate)
            tampered["rows"][0]["times_s"]["wall"] += 1.0
            tampered_path = self.write_json(root, "tampered.json", tampered)
            with self.assertRaisesRegex(CompletionError, "deterministic recomputation"):
                self.build(aggregate=tampered_path)

    def test_tampered_raw_outcome_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            raw_dir = Path(temporary_directory) / "raw"
            self.copy_raw_records(raw_dir)
            trial_id = self.aggregate["input_record_ids"][0]
            path = raw_dir / f"{trial_id}.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            record["correct"] = False
            path.write_text(
                json.dumps(record, allow_nan=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CompletionError, "outcome correct"):
                self.build(raw_dir=raw_dir)

    def test_protocol_config_and_correctness_hashes_fail_closed(self) -> None:
        protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bad_config = copy.deepcopy(protocol)
            bad_config["shards"][0]["sha256"] = "0" * 64
            config_path = self.write_json(root, "bad-config.json", bad_config)
            with self.assertRaisesRegex(CompletionError, "configuration SHA-256 mismatch"):
                self.build(protocol=config_path)

            bad_correctness = copy.deepcopy(protocol)
            bad_correctness["correctness_gate"]["sha256"] = "0" * 64
            correctness_path = self.write_json(
                root, "bad-correctness.json", bad_correctness
            )
            with self.assertRaisesRegex(CompletionError, "correctness gate SHA-256 mismatch"):
                self.build(protocol=correctness_path)

    def test_cli_uses_explicit_inputs_and_reports_idempotence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "stage4_completion.json"
            command = [
                sys.executable,
                str(SCRIPT_PATH),
                "--protocol",
                str(PROTOCOL_PATH),
                "--aggregate",
                str(AGGREGATE_PATH),
                "--raw-dir",
                str(RAW_DIR),
                "--output",
                str(output),
            ]
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(REPOSITORY_ROOT / "src")
            first = subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue(json.loads(first.stdout)["changed"])
            second = subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertFalse(json.loads(second.stdout)["changed"])


if __name__ == "__main__":
    unittest.main()
