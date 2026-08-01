from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from autosbd.config import load_sweep_config
from autosbd.features import combine_input_hashes


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "phaseb_n2_h2o_grid_correctness.yaml"
PREFIX_ROOT = PROJECT_ROOT / "data" / "derived" / "phase_b_prefixes"
PREFIX_MANIFEST_PATH = PREFIX_ROOT / "manifest.json"

PREFIX_MANIFEST_SHA256 = (
    "852c6c99b279610b413e29472e4839fc178fc63e094b01275f4bf3aaae57d373"
)
AMD_COMMIT = "729cfa3a5011fb805eb9e686a7711f6919836dcb"
AMD_REPOSITORY = "https://github.com/AMD-HPC/amd-sbd.git"

CANDIDATE_ARTIFACTS = {
    "amd-cpu-16": (
        "build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu",
        "190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07",
        797304,
    ),
    "amd-l4-default": (
        "build/upstream/amd-729cfa3a-nvhpc-26.5/diag_gpu",
        "8f1481b6bcb4ddf3326453fd3a7c03dc36e29034629f46c5e982a4c17e43bc07",
        2021216,
    ),
}

# These are the audited, role-labelled fcidump/alpha/beta hashes.  The AMD
# closed-shell path omits bdetfile and therefore reuses each alpha list as beta.
WORKLOADS = (
    (
        "n2-prefix-0032",
        "n2",
        "N2",
        "6-31G",
        32,
        "n2/AlphaDets_n0032.txt",
        "3d2406670cadd5ba16089fa08af208b469208d3afaf09ff6268aa6bfd2ea7b7d",
        "external/riken-sbd/data/n2/fcidump.txt",
        "dee67eb5e8aee2f099953a52d7910db59bc7b284ad03a8fa7ffd2a4ba8efcf33",
        "ec17e257f65c7e916b64077cad82f26ee99ce1d11991cf89affedccaafd1aa76",
    ),
    (
        "n2-prefix-0055",
        "n2",
        "N2",
        "6-31G",
        55,
        "n2/AlphaDets_n0055.txt",
        "75b771bea9661bb23f98f6e2bdd165e47841cee8e8de91c13959eb40abc54d79",
        "external/riken-sbd/data/n2/fcidump.txt",
        "dee67eb5e8aee2f099953a52d7910db59bc7b284ad03a8fa7ffd2a4ba8efcf33",
        "4507b50dbe257a7a5d0b15b1536c16526f2f0ab957eead9d7e17d765571a3637",
    ),
    (
        "n2-prefix-0100",
        "n2",
        "N2",
        "6-31G",
        100,
        "n2/AlphaDets_n0100.txt",
        "bc288d1aa1293c495453c7bb7bf3079aa9d2e03c799715d2835d9a09034b9917",
        "external/riken-sbd/data/n2/fcidump.txt",
        "dee67eb5e8aee2f099953a52d7910db59bc7b284ad03a8fa7ffd2a4ba8efcf33",
        "1d928136c75b5deedcb2c11db761ed345aaa597dd9fa947d1b41ee63cafa3f5f",
    ),
    (
        "n2-prefix-0174",
        "n2",
        "N2",
        "6-31G",
        174,
        "n2/AlphaDets_n0174.txt",
        "89ff6a62b266baf5d449dbc21d728acf318fb5c2f13dfe5e786804033bfe4823",
        "external/riken-sbd/data/n2/fcidump.txt",
        "dee67eb5e8aee2f099953a52d7910db59bc7b284ad03a8fa7ffd2a4ba8efcf33",
        "d1155d168110c036ee82b3dc7b49f5ee983c34dd893b4504304b8b36a4e23818",
    ),
    (
        "n2-prefix-0239",
        "n2",
        "N2",
        "6-31G",
        239,
        "n2/AlphaDets_n0239.txt",
        "73a28f6e6a26b06fbf4accf704f4112dca36ea53fe52ec40ed6379644b218dd2",
        "external/riken-sbd/data/n2/fcidump.txt",
        "dee67eb5e8aee2f099953a52d7910db59bc7b284ad03a8fa7ffd2a4ba8efcf33",
        "6976b0d5793326781b16b53b6ff8d7c76068bdd016bdd29aa4cbee3e6aab0deb",
    ),
    (
        "h2o-prefix-0032",
        "h2o",
        "H2O",
        "cc-pVDZ",
        32,
        "h2o/AlphaDets_n0032.txt",
        "6f1fcf262ca0e91cbede71522a4f756cc801a0c7730d2e16552876386f6da58f",
        "external/riken-sbd/data/h2o/fcidump.txt",
        "a3c2302834a33dce7260e8050a3f5180e05dbba1bb748f3e2f6410a7eacbd94d",
        "bc8b7df3cfd9b36edc9a7de5e173ba97c6d3260c199b68c67f44ddff94624373",
    ),
    (
        "h2o-prefix-0055",
        "h2o",
        "H2O",
        "cc-pVDZ",
        55,
        "h2o/AlphaDets_n0055.txt",
        "5e4b39a5043f24f7cdaabbc08de83d9d0b1d7e7bd44d0ee17093d9434de09463",
        "external/riken-sbd/data/h2o/fcidump.txt",
        "a3c2302834a33dce7260e8050a3f5180e05dbba1bb748f3e2f6410a7eacbd94d",
        "d0872935a2dc0f51499913dbc2f2300c4158877041671b5eb2d7406276f4b6e4",
    ),
    (
        "h2o-prefix-0100",
        "h2o",
        "H2O",
        "cc-pVDZ",
        100,
        "h2o/AlphaDets_n0100.txt",
        "e9839cc16b450597bac2d0e1c9e8357d6de0e76b6755aab0d3e73419ab329ce3",
        "external/riken-sbd/data/h2o/fcidump.txt",
        "a3c2302834a33dce7260e8050a3f5180e05dbba1bb748f3e2f6410a7eacbd94d",
        "8f6d951383efdfa90bdfdc8fc43e537f3e939861f6d1cd6b81d4217d95861751",
    ),
    (
        "h2o-prefix-0174",
        "h2o",
        "H2O",
        "cc-pVDZ",
        174,
        "h2o/AlphaDets_n0174.txt",
        "5cb369df17d90da84c3fb7fb13ff45a490e56281d262c8ae968e235b93c82c10",
        "external/riken-sbd/data/h2o/fcidump.txt",
        "a3c2302834a33dce7260e8050a3f5180e05dbba1bb748f3e2f6410a7eacbd94d",
        "54238461a8e4af6e254f60eecaa74512c6dee9fa209ca461041b5dea338aa659",
    ),
    (
        "h2o-prefix-0275",
        "h2o",
        "H2O",
        "cc-pVDZ",
        275,
        "h2o/AlphaDets_n0275.txt",
        "ea94906047a1d081d493066478e9f009c07cb4286541f1781060081205fd5a67",
        "external/riken-sbd/data/h2o/fcidump.txt",
        "a3c2302834a33dce7260e8050a3f5180e05dbba1bb748f3e2f6410a7eacbd94d",
        "ee17c38802ca7e869797f014dbc4957e7b589cc2cb8e2f2068c37fc2af1a150d",
    ),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PhaseBGridConfigTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_sweep_config(CONFIG_PATH)
        cls.manifest = json.loads(PREFIX_MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_grid_metadata_paths_counts_and_hashes(self) -> None:
        self.assertEqual(self.config.schema_version, 2)
        self.assertEqual(self.config.name, "phaseb-amd-n2-h2o-grid-correctness")
        self.assertEqual(len(self.config.workloads), 10)

        manifest_by_id = {
            item["workload_id"]: item for item in self.manifest["workloads"]
        }
        self.assertEqual(list(manifest_by_id), [row[0] for row in WORKLOADS])

        for workload, expected in zip(self.config.workloads, WORKLOADS, strict=True):
            (
                name,
                family_id,
                molecule,
                basis,
                count,
                prefix_relative,
                prefix_sha,
                fcidump_relative,
                fcidump_sha,
                combined_sha,
            ) = expected
            with self.subTest(workload=name):
                self.assertEqual(
                    (workload.name, workload.family_id, workload.molecule, workload.basis),
                    (name, family_id, molecule, basis),
                )
                self.assertEqual(workload.adetfile, (PREFIX_ROOT / prefix_relative).resolve())
                self.assertEqual(workload.fcidump, (PROJECT_ROOT / fcidump_relative).resolve())
                self.assertIsNone(workload.bdetfile)
                self.assertNotIn("bdetfile", workload.semantic_input_names)
                self.assertIsNone(workload.reference_value)
                self.assertIsNone(workload.reference_source)

                self.assertEqual(len(workload.adetfile.read_bytes().splitlines()), count)
                self.assertEqual(count * count, manifest_by_id[name]["expected_product_configurations"])
                self.assertEqual(sha256(workload.adetfile), prefix_sha)
                self.assertEqual(sha256(workload.fcidump), fcidump_sha)
                self.assertEqual(
                    combine_input_hashes(fcidump_sha, prefix_sha, prefix_sha),
                    combined_sha,
                )

                manifest_entry = manifest_by_id[name]
                self.assertEqual(manifest_entry["family_id"], family_id)
                self.assertEqual(manifest_entry["molecule"], molecule)
                self.assertEqual(manifest_entry["basis"], basis)
                self.assertEqual(manifest_entry["output"]["path"], prefix_relative)
                self.assertEqual(manifest_entry["output"]["row_count"], count)
                self.assertEqual(manifest_entry["output"]["sha256"], prefix_sha)
                self.assertEqual(manifest_entry["companion_fcidump"]["path"], fcidump_relative)
                self.assertEqual(manifest_entry["companion_fcidump"]["sha256"], fcidump_sha)

    def test_candidates_solver_and_protocol_match_audited_boundary(self) -> None:
        n2_b1 = load_sweep_config(PROJECT_ROOT / "configs" / "phaseb_n2_correctness.yaml")
        h2o_b1 = load_sweep_config(PROJECT_ROOT / "configs" / "phaseb_h2o_correctness.yaml")
        self.assertEqual(self.config.candidates, n2_b1.candidates)
        self.assertEqual(self.config.candidates, h2o_b1.candidates)
        self.assertEqual(self.config.solver, n2_b1.solver)
        self.assertEqual(self.config.solver, h2o_b1.solver)
        self.assertEqual(
            self.config.solver.amd_cli_args(),
            (
                "--method",
                "0",
                "--iteration",
                "6",
                "--block",
                "10",
                "--tolerance",
                "1e-08",
                "--max_time",
                "240",
                "--bit_length",
                "20",
                "--shuffle",
                "0",
                "--carryover_ratio",
                "0.5",
                "--rdm",
                "0",
                "--adet_comm_size",
                "1",
                "--bdet_comm_size",
                "1",
                "--task_comm_size",
                "1",
            ),
        )

        self.assertEqual(
            [candidate.name for candidate in self.config.candidates],
            ["amd-cpu-16", "amd-l4-default"],
        )
        for candidate in self.config.candidates:
            relative_path, expected_sha, expected_size = CANDIDATE_ARTIFACTS[candidate.name]
            artifact = PROJECT_ROOT / relative_path
            self.assertEqual(candidate.executable, artifact.resolve())
            self.assertEqual(sha256(artifact), expected_sha)
            self.assertEqual(artifact.stat().st_size, expected_size)
            self.assertNotIn("riken-sbd", str(candidate.executable))

        protocol = self.config.protocol
        self.assertEqual(protocol.warmups, 0)
        self.assertEqual(protocol.repetitions, 1)
        self.assertEqual(protocol.timeout_s, 300.0)
        self.assertEqual(protocol.seed, 1729)
        self.assertEqual(protocol.purpose, "correctness")
        self.assertFalse(protocol.correctness_validated)
        self.assertIsNone(protocol.validation_manifest)

    def test_templates_are_twenty_ordered_correctness_trials(self) -> None:
        templates = self.config.trial_templates(randomize=False)
        self.assertEqual(len(templates), 20)
        self.assertEqual(
            [
                (template.workload.name, template.candidate.name)
                for template in templates
            ],
            [
                (workload[0], candidate)
                for workload in WORKLOADS
                for candidate in ("amd-cpu-16", "amd-l4-default")
            ],
        )
        self.assertTrue(
            all(
                template.phase == "measured" and template.repetition == 0
                for template in templates
            )
        )

    def test_prefix_manifest_is_pinned_to_official_amd_solver_boundary(self) -> None:
        self.assertEqual(sha256(PREFIX_MANIFEST_PATH), PREFIX_MANIFEST_SHA256)
        boundary = self.manifest["solver_boundary"]
        self.assertEqual(boundary["active_solver_commit"], AMD_COMMIT)
        self.assertEqual(boundary["active_solver_repository"], AMD_REPOSITORY)
        self.assertTrue(boundary["same_pinned_amd_cpu_gpu_implementation_required"])
        self.assertEqual(boundary["riken_checkout_role"], "input_data_only")
        self.assertFalse(boundary["riken_solver_build_run_or_timing_allowed"])


if __name__ == "__main__":
    unittest.main()
