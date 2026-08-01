"""Regression tests for the frozen Phase B final timing shards."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import unittest

from autosbd.config import SweepConfig, load_sweep_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_PATH = PROJECT_ROOT / "configs" / "phaseb_n2_h2o_grid_pilot.yaml"
CROSSOVER_PATH = (
    PROJECT_ROOT / "configs" / "phaseb_n2_h2o_final_crossover.yaml"
)
BROAD_PATH = PROJECT_ROOT / "configs" / "phaseb_n2_h2o_final_broad.yaml"
HEADLINE_PATH = PROJECT_ROOT / "configs" / "phaseb_n2_h2o_final_headline.yaml"
PROTOCOL_PATH = PROJECT_ROOT / "reports" / "phaseb_final_protocol.json"

CROSSOVER_WORKLOADS = {
    "n2-prefix-0055",
    "n2-prefix-0100",
    "h2o-prefix-0055",
    "h2o-prefix-0100",
}
BROAD_WORKLOADS = {
    "n2-prefix-0032",
    "n2-prefix-0174",
    "h2o-prefix-0032",
    "h2o-prefix-0174",
}
HEADLINE_WORKLOADS = {
    "n2-prefix-0239",
    "h2o-prefix-0275",
}


class PhaseBFinalConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pilot = load_sweep_config(PILOT_PATH)
        cls.crossover = load_sweep_config(CROSSOVER_PATH)
        cls.broad = load_sweep_config(BROAD_PATH)
        cls.headline = load_sweep_config(HEADLINE_PATH)
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))

    def test_workloads_partition_the_exact_pilot_grid(self) -> None:
        pilot_by_name = {item.name: item for item in self.pilot.workloads}
        crossover_by_name = {
            item.name: item for item in self.crossover.workloads
        }
        broad_by_name = {item.name: item for item in self.broad.workloads}
        headline_by_name = {
            item.name: item for item in self.headline.workloads
        }

        self.assertFalse(CROSSOVER_WORKLOADS.intersection(BROAD_WORKLOADS))
        self.assertFalse(CROSSOVER_WORKLOADS.intersection(HEADLINE_WORKLOADS))
        self.assertFalse(BROAD_WORKLOADS.intersection(HEADLINE_WORKLOADS))
        self.assertEqual(
            CROSSOVER_WORKLOADS.union(BROAD_WORKLOADS, HEADLINE_WORKLOADS),
            set(pilot_by_name),
        )
        self.assertEqual(set(crossover_by_name), CROSSOVER_WORKLOADS)
        self.assertEqual(set(broad_by_name), BROAD_WORKLOADS)
        self.assertEqual(set(headline_by_name), HEADLINE_WORKLOADS)
        final_by_name = {
            **crossover_by_name,
            **broad_by_name,
            **headline_by_name,
        }
        for name, workload in final_by_name.items():
            self.assertEqual(workload, pilot_by_name[name])

    def test_candidates_solver_and_correctness_gate_are_unchanged(self) -> None:
        for shard in (self.crossover, self.broad, self.headline):
            self.assertEqual(shard.schema_version, 2)
            self.assertEqual(shard.name, "phaseb-amd-n2-h2o-grid-final-v1")
            self.assertEqual(shard.candidates, self.pilot.candidates)
            self.assertEqual(shard.solver, self.pilot.solver)
            self.assertEqual(shard.protocol.warmups, 1)
            self.assertEqual(shard.protocol.timeout_s, 300)
            self.assertEqual(shard.protocol.seed, 1729)
            self.assertEqual(shard.protocol.purpose, "final")
            self.assertTrue(shard.protocol.correctness_validated)
            self.assertEqual(
                shard.protocol.validation_manifest,
                self.pilot.protocol.validation_manifest,
            )

    def test_exact_104_record_protocol_and_repetition_geometry(self) -> None:
        expectations: tuple[tuple[SweepConfig, int, int], ...] = (
            (self.crossover, 5, 48),
            (self.broad, 3, 32),
            (self.headline, 5, 24),
        )
        total_templates = 0
        phase_counts: Counter[str] = Counter()
        workload_phase_candidate_counts: Counter[tuple[str, str, str]] = Counter()
        measured_repetitions: dict[tuple[str, str], set[int]] = {}

        for shard, repetitions, expected_total in expectations:
            templates = shard.trial_templates(randomize=True)
            self.assertEqual(len(templates), expected_total)
            self.assertEqual(
                templates, shard.trial_templates(randomize=True)
            )
            total_templates += len(templates)
            for template in templates:
                phase_counts[template.phase] += 1
                key = (
                    template.workload.name,
                    template.phase,
                    template.candidate.name,
                )
                workload_phase_candidate_counts[key] += 1
                if template.phase == "measured":
                    measured_repetitions.setdefault(
                        (template.workload.name, template.candidate.name), set()
                    ).add(template.repetition)

            for workload in shard.workloads:
                for candidate in shard.candidates:
                    self.assertEqual(
                        workload_phase_candidate_counts[
                            (workload.name, "warmup", candidate.name)
                        ],
                        1,
                    )
                    self.assertEqual(
                        workload_phase_candidate_counts[
                            (workload.name, "measured", candidate.name)
                        ],
                        repetitions,
                    )
                    self.assertEqual(
                        measured_repetitions[(workload.name, candidate.name)],
                        set(range(repetitions)),
                    )

        self.assertEqual(total_templates, 104)
        self.assertEqual(phase_counts, {"warmup": 20, "measured": 84})

    def test_frozen_protocol_hashes_counts_and_projection(self) -> None:
        protocol = self.protocol
        self.assertEqual(protocol["schema_version"], 1)
        self.assertEqual(protocol["status"], "frozen_before_measurement")
        self.assertTrue(
            protocol["approval_gate"][
                "explicit_user_approval_required_before_launch"
            ]
        )
        self.assertEqual(
            protocol["approval_gate"]["status_at_freeze"],
            "awaiting_approval",
        )

        configs = {
            CROSSOVER_PATH.relative_to(PROJECT_ROOT).as_posix(): self.crossover,
            BROAD_PATH.relative_to(PROJECT_ROOT).as_posix(): self.broad,
            HEADLINE_PATH.relative_to(PROJECT_ROOT).as_posix(): self.headline,
        }
        expected_counts = Counter()
        for shard in protocol["shards"]:
            relative_path = shard["path"]
            path = PROJECT_ROOT / relative_path
            self.assertIn(relative_path, configs)
            self.assertEqual(shard["sha256"], _sha256(path))
            templates = configs[relative_path].trial_templates(randomize=True)
            phase_counts = Counter(template.phase for template in templates)
            self.assertEqual(shard["expected_total_records"], len(templates))
            self.assertEqual(
                shard["expected_warmup_records"], phase_counts["warmup"]
            )
            self.assertEqual(
                shard["expected_measured_records"], phase_counts["measured"]
            )
            expected_counts.update(phase_counts)

        self.assertEqual(
            protocol["expected_campaign_records"],
            {
                "warmup": expected_counts["warmup"],
                "measured": expected_counts["measured"],
                "total": sum(expected_counts.values()),
            },
        )

        pilot = protocol["pilot_evidence"]
        for key in ("config", "aggregate_json", "aggregate_csv"):
            claim = pilot[key]
            self.assertEqual(
                claim["sha256"], _sha256(PROJECT_ROOT / claim["path"])
            )
        gate = protocol["correctness_gate"]
        self.assertEqual(gate["sha256"], _sha256(PROJECT_ROOT / gate["path"]))

        projection = protocol["projection"]
        self.assertAlmostEqual(
            projection["projected_total_s"],
            projection["projected_process_wall_s"]
            + projection["projected_orchestration_overhead_s"],
        )
        self.assertAlmostEqual(
            projection["projected_total_minutes"],
            projection["projected_total_s"] / 60.0,
        )
        self.assertAlmostEqual(
            projection["projected_cost_usd"],
            projection["projected_total_s"]
            / 3600.0
            * projection["rate_usd_per_hour"],
        )
        self.assertAlmostEqual(
            projection["buffered_minutes"],
            projection["projected_total_minutes"]
            * projection["buffer_factor"],
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
