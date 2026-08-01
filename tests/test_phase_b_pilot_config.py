from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from autosbd.config import load_sweep_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORRECTNESS_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "phaseb_n2_h2o_grid_correctness.yaml"
)
PILOT_CONFIG_PATH = PROJECT_ROOT / "configs" / "phaseb_n2_h2o_grid_pilot.yaml"
MANIFEST_PATH = (
    PROJECT_ROOT / "reports" / "phaseb_n2_h2o_grid_correctness_manifest.json"
)
MANIFEST_SHA256 = (
    "ba6bf82b63c9a8bdf2a5a513df914a9f1446605a0d4939cb53f7921527222829"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PhaseBPilotConfigTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.correctness = load_sweep_config(CORRECTNESS_CONFIG_PATH)
        cls.pilot = load_sweep_config(PILOT_CONFIG_PATH)
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_workloads_match_correctness_grid_and_manifest_references(self) -> None:
        self.assertEqual(self.pilot.schema_version, 2)
        self.assertEqual(self.pilot.name, "phaseb-amd-n2-h2o-grid-pilot")
        self.assertEqual(len(self.pilot.workloads), 10)
        self.assertEqual(sha256(MANIFEST_PATH), MANIFEST_SHA256)
        self.assertEqual(self.manifest["schema_version"], 3)
        self.assertTrue(self.manifest["passed"])

        validated = {
            item["problem_instance"]: item
            for item in self.manifest["validated_inputs"]
        }
        self.assertEqual(
            set(validated), {workload.name for workload in self.pilot.workloads}
        )
        for pilot, correctness in zip(
            self.pilot.workloads, self.correctness.workloads, strict=True
        ):
            with self.subTest(workload=pilot.name):
                self.assertEqual(pilot.name, correctness.name)
                self.assertEqual(pilot.family_id, correctness.family_id)
                self.assertEqual(pilot.molecule, correctness.molecule)
                self.assertEqual(pilot.basis, correctness.basis)
                self.assertEqual(pilot.fcidump, correctness.fcidump)
                self.assertEqual(pilot.adetfile, correctness.adetfile)
                self.assertEqual(pilot.bdetfile, correctness.bdetfile)

                entry = validated[pilot.name]
                self.assertEqual(pilot.reference_value, entry["reference_value"])
                self.assertEqual(
                    pilot.reference_source,
                    "reports/phaseb_n2_h2o_grid_correctness_manifest.json",
                )
                self.assertEqual(pilot.family_id, entry["family_id"])
                self.assertEqual(pilot.molecule, entry["molecule"])
                self.assertEqual(pilot.basis, entry["basis"])
                self.assertEqual(
                    pilot.reference_value, entry["comparison"]["cpu_energy"]
                )

    def test_candidate_solver_and_protocol_boundary(self) -> None:
        self.assertEqual(self.pilot.candidates, self.correctness.candidates)
        self.assertEqual(self.pilot.solver, self.correctness.solver)
        protocol = self.pilot.protocol
        self.assertEqual(protocol.warmups, 1)
        self.assertEqual(protocol.repetitions, 1)
        self.assertEqual(protocol.timeout_s, 300.0)
        self.assertEqual(protocol.seed, 1729)
        self.assertEqual(protocol.purpose, "pilot")
        self.assertTrue(protocol.correctness_validated)
        self.assertEqual(protocol.validation_manifest, MANIFEST_PATH.resolve())

    def test_templates_are_forty_grouped_randomized_trials(self) -> None:
        ordered = self.pilot.trial_templates(randomize=False)
        randomized = self.pilot.trial_templates(randomize=True)
        self.assertEqual(randomized, self.pilot.trial_templates(randomize=True))
        self.assertEqual(len(ordered), 40)
        self.assertEqual(len(randomized), 40)
        self.assertEqual(
            [(item.phase, item.repetition) for item in ordered[:20]],
            [("warmup", 0)] * 20,
        )
        self.assertEqual(
            [(item.phase, item.repetition) for item in ordered[20:]],
            [("measured", 0)] * 20,
        )
        self.assertNotEqual(
            [item.candidate.name for item in randomized],
            [item.candidate.name for item in ordered],
        )

        for offset, phase in ((0, "warmup"), (20, "measured")):
            for workload_index, workload in enumerate(self.pilot.workloads):
                group = randomized[
                    offset + workload_index * 2 : offset + workload_index * 2 + 2
                ]
                self.assertEqual({item.workload.name for item in group}, {workload.name})
                self.assertEqual({item.phase for item in group}, {phase})
                self.assertEqual(
                    {item.candidate.name for item in group},
                    {"amd-cpu-16", "amd-l4-default"},
                )


if __name__ == "__main__":
    unittest.main()
