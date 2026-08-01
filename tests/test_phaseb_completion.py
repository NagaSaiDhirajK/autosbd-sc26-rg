"""Tests for the fail-closed Phase B final completion attestation."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autosbd.phaseb_completion import (
    COMPLETION_TYPE,
    EXPECTED_AGGREGATE_SHA256,
    PhaseBCompletionError,
    build_phaseb_final_completion,
    validate_phaseb_final_completion,
    write_phaseb_final_completion,
)


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "reports/phaseb_final_protocol.json"
AGGREGATE = ROOT / "results/processed/phaseb_n2_h2o_grid_final.json"
RAW_DIR = ROOT / "results/raw"


class PhaseBCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.completion = build_phaseb_final_completion(
            PROTOCOL,
            AGGREGATE,
            RAW_DIR,
            repository_root=ROOT,
        )

    def test_real_evidence_builds_exact_completion(self) -> None:
        completion = self.completion
        self.assertEqual(completion["attestation_type"], COMPLETION_TYPE)
        self.assertEqual(completion["status"], "complete")
        self.assertEqual(
            {
                key: completion["campaign_counts"][key]
                for key in (
                    "records",
                    "warmup",
                    "measured",
                    "timing_eligible",
                    "success",
                    "correct",
                )
            },
            {
                "records": 104,
                "warmup": 20,
                "measured": 84,
                "timing_eligible": 84,
                "success": 104,
                "correct": 104,
            },
        )
        self.assertEqual(
            completion["campaign_counts"]["by_shard"],
            {"broad": 32, "crossover": 48, "headline": 24},
        )
        self.assertEqual(
            len(completion["analysis_views"]["balanced_broad"]["record_ids"]),
            60,
        )
        self.assertEqual(len(completion["records"]), 104)
        self.assertTrue(
            completion["temporal_integrity"]["sequential_no_overlap"]
        )
        self.assertAlmostEqual(
            completion["temporal_integrity"]["campaign_span_s"], 279.985871
        )
        validate_phaseb_final_completion(completion)

    def test_build_is_deterministic(self) -> None:
        second = build_phaseb_final_completion(
            PROTOCOL,
            AGGREGATE,
            RAW_DIR,
            repository_root=ROOT,
        )
        self.assertEqual(second, self.completion)

    def test_wrong_frozen_aggregate_hash_fails_before_record_use(self) -> None:
        with patch(
            "autosbd.phaseb_completion.EXPECTED_AGGREGATE_SHA256",
            "0" * 64,
        ):
            with self.assertRaisesRegex(
                PhaseBCompletionError, "aggregate SHA-256 mismatch"
            ):
                build_phaseb_final_completion(
                    PROTOCOL,
                    AGGREGATE,
                    RAW_DIR,
                    repository_root=ROOT,
                )
        self.assertEqual(
            EXPECTED_AGGREGATE_SHA256,
            "f7deacc86e923614fded5f8e6bdfa7206fe8339e3a4d035d6db7ee967212768d",
        )

    def test_validation_rejects_balanced_view_drift(self) -> None:
        changed = deepcopy(self.completion)
        changed["analysis_views"]["balanced_broad"]["record_ids"].pop()
        with self.assertRaisesRegex(PhaseBCompletionError, "exactly 60"):
            validate_phaseb_final_completion(changed)

    def test_atomic_write_changes_once_and_refuses_raw_directory(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "completion.json"
            self.assertTrue(
                write_phaseb_final_completion(
                    self.completion, output, repository_root=ROOT
                )
            )
            first = output.read_bytes()
            self.assertFalse(
                write_phaseb_final_completion(
                    self.completion, output, repository_root=ROOT
                )
            )
            self.assertEqual(output.read_bytes(), first)
            parsed = json.loads(first)
            self.assertEqual(parsed, self.completion)

        forbidden = RAW_DIR / "phaseb-completion-test.json"
        self.assertFalse(forbidden.exists())
        with self.assertRaisesRegex(PhaseBCompletionError, "forbidden"):
            write_phaseb_final_completion(
                self.completion, forbidden, repository_root=ROOT
            )
        self.assertFalse(forbidden.exists())


if __name__ == "__main__":
    unittest.main()
