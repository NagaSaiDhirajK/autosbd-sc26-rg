"""Regression checks for the frozen Stage 4 measurement protocol."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from autosbd.config import load_sweep_config


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = REPOSITORY_ROOT / "reports" / "stage4_protocol.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Stage4ProtocolTests(unittest.TestCase):
    def test_frozen_protocol_hashes_geometry_and_candidates(self) -> None:
        protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(protocol["schema_version"], 1)
        self.assertEqual(protocol["status"], "frozen_before_measurement")
        self.assertEqual(protocol["name"], "stage4-amd-fe4s4-final-v1")
        self.assertEqual(protocol["scope"]["problem_family_count"], 1)
        self.assertFalse(protocol["scope"]["distinct_chemical_families"])

        expected_candidates = {
            ("amd-cpu-16", "cpu", 16),
            ("amd-l4-default", "gpu", 1),
        }
        semantic_keys: set[tuple[str, str, str, int]] = set()
        workloads: set[str] = set()
        observed_counts = {"warmup": 0, "measured": 0, "total": 0}

        for shard in protocol["shards"]:
            path = REPOSITORY_ROOT / shard["path"]
            self.assertEqual(sha256_file(path), shard["sha256"])
            config = load_sweep_config(path)
            self.assertEqual(config.name, protocol["name"])
            self.assertEqual(config.protocol.purpose, "final")
            self.assertTrue(config.protocol.correctness_validated)
            self.assertEqual(config.protocol.seed, protocol["protocol"]["seed"])
            self.assertEqual(
                config.protocol.timeout_s, protocol["protocol"]["timeout_s"]
            )
            self.assertEqual(
                {
                    (candidate.name, candidate.backend, candidate.threads)
                    for candidate in config.candidates
                },
                expected_candidates,
            )

            shard_workloads = {workload.name for workload in config.workloads}
            self.assertFalse(workloads.intersection(shard_workloads))
            self.assertEqual(shard_workloads, set(shard["workloads"]))
            workloads.update(shard_workloads)

            templates = config.trial_templates(randomize=True)
            shard_keys = {template.semantic_key for template in templates}
            self.assertEqual(len(shard_keys), len(templates))
            self.assertFalse(semantic_keys.intersection(shard_keys))
            semantic_keys.update(shard_keys)
            warmups = sum(template.phase == "warmup" for template in templates)
            measured = sum(template.phase == "measured" for template in templates)
            self.assertEqual(warmups, shard["expected_warmup_records"])
            self.assertEqual(measured, shard["expected_measured_records"])
            self.assertEqual(len(templates), shard["expected_total_records"])
            observed_counts["warmup"] += warmups
            observed_counts["measured"] += measured
            observed_counts["total"] += len(templates)

        self.assertEqual(len(workloads), 5)
        self.assertEqual(len(semantic_keys), 48)
        self.assertEqual(observed_counts, protocol["expected_campaign_records"])

        for evidence_key in ("correctness_gate", "candidate_pruning_evidence"):
            evidence = protocol[evidence_key]
            path = REPOSITORY_ROOT / evidence["path"]
            self.assertEqual(sha256_file(path), evidence["sha256"])

        self.assertEqual(
            set(protocol["candidate_pruning_evidence"]["retained_candidates"]),
            {"amd-cpu-16", "amd-l4-default"},
        )
        self.assertEqual(
            set(protocol["candidate_pruning_evidence"]["pruned_candidates"]),
            {"amd-cpu-1", "amd-cpu-4", "amd-cpu-8"},
        )


if __name__ == "__main__":
    unittest.main()
