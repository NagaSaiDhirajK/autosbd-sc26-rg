#!/usr/bin/env python3
"""Prepare audited N2/H2O determinant-prefix workloads for Phase B.

The RIKEN ``r-ccs-cms/sbd`` checkout is used only as the pinned source of
authentic input data.  Every generated workload remains intended for the
official pinned AMD SBD CPU/GPU executables; this script does not build, run,
or authorize a switch to the RIKEN solver implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_ROOT = REPOSITORY_ROOT / "external" / "riken-sbd"
DEFAULT_INVENTORY = REPOSITORY_ROOT / "reports" / "phase_b_input_inventory.json"
DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / "data" / "derived" / "phase_b_prefixes"
INVENTORY_VALIDATOR = REPOSITORY_ROOT / "scripts" / "validate_phase_b_inputs.py"

UPSTREAM_REPOSITORY = "https://github.com/r-ccs-cms/sbd.git"
UPSTREAM_TAG = "v1.3.0"
UPSTREAM_COMMIT = "b71e1c3ed857fcb4fb05731dc285831c1afe9ebd"
EXPECTED_INVENTORY_SHA256 = (
    "0105bc73dea01e31f8a4230ec7c69f0bb903d8f53763eb5270b4f4bbaf0b9fc1"
)
EXPECTED_FAMILY_ORDER = ("n2", "h2o")
EXPECTED_FULL_COUNTS = {"n2": 239, "h2o": 275}
DERIVED_PREFIX_COUNTS = (32, 55, 100, 174)
MANIFEST_NAME = "manifest.json"
ACTIVE_SOLVER_REPOSITORY = "https://github.com/AMD-HPC/amd-sbd.git"
ACTIVE_SOLVER_COMMIT = "729cfa3a5011fb805eb9e686a7711f6919836dcb"


class PreparationError(RuntimeError):
    """Raised when provenance, source, output, or verification checks fail."""


def _load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_autosbd_phase_b_input_validator", INVENTORY_VALIDATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Phase B input validator: {INVENTORY_VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INPUT_VALIDATOR = _load_validator_module()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git_output(*arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(UPSTREAM_ROOT), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreparationError(f"cannot inspect pinned RIKEN checkout: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        raise PreparationError(f"cannot inspect pinned RIKEN checkout: {detail}")
    return completed.stdout.strip()


def _validate_upstream_checkout() -> None:
    if _git_output("remote", "get-url", "origin") != UPSTREAM_REPOSITORY:
        raise PreparationError("pinned RIKEN input checkout origin mismatch")
    if _git_output("rev-parse", "HEAD") != UPSTREAM_COMMIT:
        raise PreparationError("pinned RIKEN input checkout commit mismatch")
    if _git_output("describe", "--tags", "--exact-match", "HEAD") != UPSTREAM_TAG:
        raise PreparationError("pinned RIKEN input checkout tag mismatch")
    if _git_output("rev-parse", f"refs/tags/{UPSTREAM_TAG}^{{commit}}") != UPSTREAM_COMMIT:
        raise PreparationError("pinned RIKEN input tag does not resolve to its commit")
    if _git_output("status", "--porcelain=v1", "--untracked-files=all"):
        raise PreparationError("pinned RIKEN input checkout has local modifications")


def _read_stable_regular_file(path: Path, label: str) -> bytes:
    path = Path(path)
    try:
        if path.is_symlink() or not path.is_file():
            raise PreparationError(f"{label} is not a safe regular file: {path}")
        before = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise PreparationError(f"{label} is not a regular file: {path}")
        payload = path.read_bytes()
        after = path.stat(follow_symlinks=False)
    except PreparationError:
        raise
    except OSError as exc:
        raise PreparationError(f"cannot read {label} {path}: {exc}") from exc
    identities = (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
    )
    if identities[0] != identities[1]:
        raise PreparationError(f"{label} changed while being read: {path}")
    return payload


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _project_file(relative_path: str, label: str) -> Path:
    pure_path = PurePosixPath(relative_path)
    if (
        pure_path.is_absolute()
        or ".." in pure_path.parts
        or pure_path.as_posix() != relative_path
    ):
        raise PreparationError(f"{label} is not a normalized project-relative path")
    candidate = REPOSITORY_ROOT / relative_path
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise PreparationError(f"{label} is missing: {relative_path}") from exc
    if not _is_within(resolved, REPOSITORY_ROOT):
        raise PreparationError(f"{label} escapes the project root: {relative_path}")
    if candidate.is_symlink() or not resolved.is_file():
        raise PreparationError(f"{label} is not a safe regular file: {relative_path}")
    return resolved


def _load_and_validate_inventory(path: Path) -> tuple[Mapping[str, Any], bytes]:
    payload = _read_stable_regular_file(path, "Phase B input inventory")
    observed_hash = _sha256(payload)
    if observed_hash != EXPECTED_INVENTORY_SHA256:
        raise PreparationError(
            "Phase B input inventory SHA-256 mismatch: "
            f"expected {EXPECTED_INVENTORY_SHA256}, observed {observed_hash}"
        )
    try:
        result = INPUT_VALIDATOR.validate_inventory(path, REPOSITORY_ROOT)
        inventory = INPUT_VALIDATOR.load_manifest(path)
    except (INPUT_VALIDATOR.InventoryError, OSError) as exc:
        raise PreparationError(f"Phase B input inventory validation failed: {exc}") from exc
    if result.get("status") != "pass" or result.get("manifest_sha256") != observed_hash:
        raise PreparationError("Phase B input inventory validator returned inconsistent evidence")
    final_payload = _read_stable_regular_file(path, "Phase B input inventory")
    if final_payload != payload:
        raise PreparationError("Phase B input inventory changed during validation")
    if not isinstance(inventory, Mapping):  # defensive guard beyond strict validator
        raise PreparationError("Phase B input inventory root is not an object")
    return inventory, payload


def _file_entry(family: Mapping[str, Any], path: str, role: str) -> Mapping[str, Any]:
    matches = [
        entry
        for entry in family["files"]
        if entry.get("path") == path and entry.get("role") == role
    ]
    if len(matches) != 1:
        raise PreparationError(
            f"inventory must contain exactly one {role} entry for {path}"
        )
    return matches[0]


def _validate_exact_file(
    entry: Mapping[str, Any], payload: bytes, label: str
) -> None:
    expected_bytes = entry["size_bytes"]
    if len(payload) != expected_bytes:
        raise PreparationError(
            f"{label} byte count mismatch: expected {expected_bytes}, observed {len(payload)}"
        )
    observed_hash = _sha256(payload)
    if observed_hash != entry["sha256"]:
        raise PreparationError(
            f"{label} SHA-256 mismatch: expected {entry['sha256']}, "
            f"observed {observed_hash}"
        )


def _validate_parent_determinants(
    entry: Mapping[str, Any], payload: bytes, family_id: str
) -> tuple[bytes, ...]:
    _validate_exact_file(entry, payload, f"{family_id} parent determinant list")
    lines = tuple(payload.splitlines(keepends=True))
    expected_rows = entry["row_count"]
    if len(lines) != expected_rows:
        raise PreparationError(
            f"{family_id} parent determinant row count mismatch: "
            f"expected {expected_rows}, observed {len(lines)}"
        )
    width = entry["string_width"]
    occupancy = entry["occupied_orbitals"]
    for row_number, line in enumerate(lines, start=1):
        if len(line) != width + 1 or not line.endswith(b"\n"):
            raise PreparationError(
                f"{family_id} determinant row {row_number} is not LF-terminated "
                f"with width {width}"
            )
        determinant = line[:-1]
        if set(determinant) - {ord("0"), ord("1")}:
            raise PreparationError(
                f"{family_id} determinant row {row_number} is not binary"
            )
        if determinant.count(b"1") != occupancy:
            raise PreparationError(
                f"{family_id} determinant row {row_number} occupancy mismatch"
            )
    if len(set(lines)) != len(lines):
        raise PreparationError(f"{family_id} parent determinant list has duplicates")
    if b"".join(lines) != payload:
        raise PreparationError(f"{family_id} determinant bytes are not exactly line-preserving")
    return lines


def _variant_name(size: int) -> str:
    return f"AlphaDets_n{size:04d}.txt"


def _variant_relative_path(family_id: str, size: int) -> PurePosixPath:
    return PurePosixPath(family_id) / _variant_name(size)


def _validate_output_location(
    output_directory: Path,
    inventory_path: Path,
    protected_inputs: Sequence[Path],
) -> None:
    resolved_output = output_directory.resolve()
    if output_directory.is_symlink():
        raise PreparationError(f"output directory must not be a symlink: {output_directory}")
    if output_directory.exists() and not output_directory.is_dir():
        raise PreparationError(f"output directory is not a directory: {output_directory}")
    if resolved_output == REPOSITORY_ROOT.resolve():
        raise PreparationError("refusing to use the repository root as an output directory")
    if _is_within(resolved_output, UPSTREAM_ROOT):
        raise PreparationError("refusing to generate derived files inside pinned upstream")
    if _is_within(resolved_output, REPOSITORY_ROOT) and not _is_within(
        resolved_output, REPOSITORY_ROOT / "data" / "derived"
    ):
        raise PreparationError(
            "project-local outputs must remain under data/derived"
        )

    protected = {path.resolve() for path in (*protected_inputs, inventory_path)}
    targets = [resolved_output / MANIFEST_NAME]
    for family_id in EXPECTED_FAMILY_ORDER:
        for size in (*DERIVED_PREFIX_COUNTS, EXPECTED_FULL_COUNTS[family_id]):
            targets.append(resolved_output / _variant_relative_path(family_id, size))
    for target in targets:
        if target.resolve() in protected:
            raise PreparationError(f"refusing to overwrite a pinned input: {target}")


def _build_expected(
    inventory: Mapping[str, Any],
    inventory_path: Path,
    inventory_payload: bytes,
) -> tuple[dict[str, object], dict[PurePosixPath, bytes], dict[Path, bytes]]:
    families_by_id = {family["family_id"]: family for family in inventory["families"]}
    if set(families_by_id) != set(EXPECTED_FAMILY_ORDER):
        raise PreparationError("inventory family IDs do not match N2/H2O Phase B scope")

    license_entry = inventory["license"]
    license_path = _project_file(license_entry["path"], "license input")
    license_payload = _read_stable_regular_file(license_path, "license input")
    _validate_exact_file(license_entry, license_payload, "license input")

    variants: dict[PurePosixPath, bytes] = {}
    snapshots: dict[Path, bytes] = {
        inventory_path.resolve(): inventory_payload,
        license_path: license_payload,
    }
    workload_records: list[dict[str, object]] = []

    for family_id in EXPECTED_FAMILY_ORDER:
        family = families_by_id[family_id]
        pair = family["smallest_complete_pair"]
        full_count = pair["n_alpha_strings"]
        if full_count != EXPECTED_FULL_COUNTS[family_id]:
            raise PreparationError(
                f"{family_id} full official count mismatch: expected "
                f"{EXPECTED_FULL_COUNTS[family_id]}, observed {full_count}"
            )

        parent_entry = _file_entry(
            family, pair["alpha_determinants_path"], "alpha_determinants"
        )
        fcidump_entry = _file_entry(family, pair["fcidump_path"], "fcidump")
        parent_path = _project_file(parent_entry["path"], f"{family_id} parent input")
        fcidump_path = _project_file(fcidump_entry["path"], f"{family_id} FCIDUMP")
        parent_payload = _read_stable_regular_file(
            parent_path, f"{family_id} parent determinant list"
        )
        fcidump_payload = _read_stable_regular_file(fcidump_path, f"{family_id} FCIDUMP")
        parent_lines = _validate_parent_determinants(
            parent_entry, parent_payload, family_id
        )
        _validate_exact_file(fcidump_entry, fcidump_payload, f"{family_id} FCIDUMP")
        snapshots[parent_path] = parent_payload
        snapshots[fcidump_path] = fcidump_payload

        counts = (*DERIVED_PREFIX_COUNTS, full_count)
        previous_payload = b""
        for count in counts:
            if count > full_count:
                raise PreparationError(
                    f"{family_id} prefix {count} exceeds official parent count {full_count}"
                )
            output_payload = b"".join(parent_lines[:count])
            if not output_payload.startswith(previous_payload):
                raise PreparationError(f"{family_id} prefix grid is not nested")
            previous_payload = output_payload
            relative_output = _variant_relative_path(family_id, count)
            variants[relative_output] = output_payload
            is_full = count == full_count
            if is_full and output_payload != parent_payload:
                raise PreparationError(
                    f"{family_id} full variant is not byte-identical to its parent"
                )

            workload_records.append(
                {
                    "workload_id": f"{family_id}-prefix-{count:04d}",
                    "family_id": family_id,
                    "molecule": family["molecule"],
                    "basis": family["basis"],
                    "electronic_structure": {
                        "norb": family["norb"],
                        "nelec": family["nelec"],
                        "ms2": family["ms2"],
                    },
                    "parent_determinants": {
                        "path": parent_entry["path"],
                        "source_url": parent_entry["source_url"],
                        "sha256": parent_entry["sha256"],
                        "bytes": parent_entry["size_bytes"],
                        "row_count": parent_entry["row_count"],
                    },
                    "prefix": {
                        "rule": "first_n_rows_in_official_parent_order",
                        "half_determinant_count": count,
                        "is_full_official_smallest_list": is_full,
                        "byte_identical_to_parent": is_full,
                    },
                    "output": {
                        "path": relative_output.as_posix(),
                        "sha256": _sha256(output_payload),
                        "bytes": len(output_payload),
                        "row_count": count,
                    },
                    "companion_fcidump": {
                        "path": fcidump_entry["path"],
                        "source_url": fcidump_entry["source_url"],
                        "sha256": fcidump_entry["sha256"],
                        "bytes": fcidump_entry["size_bytes"],
                    },
                    "expected_product_configurations": count * count,
                    "source_and_license": {
                        "family_tree_url": family["source_tree_url"],
                        "repository_url": inventory["source_repository"]["origin_url"],
                        "repository_tag": inventory["source_repository"]["tag"],
                        "repository_commit": inventory["source_repository"]["commit"],
                        "license_spdx": license_entry["spdx"],
                        "license_url": license_entry["source_url"],
                    },
                }
            )

    manifest: dict[str, object] = {
        "schema_version": 1,
        "dataset_id": "phase-b-n2-h2o-derived-determinant-prefixes",
        "inventory": {
            "path": _display_path(inventory_path),
            "sha256": _sha256(inventory_payload),
        },
        "source_repository": {
            "url": UPSTREAM_REPOSITORY,
            "tag": UPSTREAM_TAG,
            "commit": UPSTREAM_COMMIT,
            "checkout_role": "input_data_only",
        },
        "solver_boundary": {
            "active_solver_repository": ACTIVE_SOLVER_REPOSITORY,
            "active_solver_commit": ACTIVE_SOLVER_COMMIT,
            "riken_checkout_role": "input_data_only",
            "riken_solver_build_run_or_timing_allowed": False,
            "same_pinned_amd_cpu_gpu_implementation_required": True,
        },
        "license": {
            "path": license_entry["path"],
            "source_url": license_entry["source_url"],
            "spdx": license_entry["spdx"],
            "sha256": license_entry["sha256"],
        },
        "derivation": {
            "operation": "byte_exact_ordered_prefix",
            "nested_within_family": True,
            "source_order_preserved": True,
            "source_line_bytes_preserved": True,
            "derived_prefix_counts": list(DERIVED_PREFIX_COUNTS),
            "full_official_counts": dict(EXPECTED_FULL_COUNTS),
            "product_configuration_rule": "half_determinant_count_squared",
        },
        "workloads": workload_records,
    }
    return manifest, variants, snapshots


def _manifest_bytes(manifest: Mapping[str, object]) -> bytes:
    return (
        json.dumps(manifest, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _verify_exact(path: Path, expected: bytes, label: str) -> None:
    observed = _read_stable_regular_file(path, label)
    if observed != expected:
        raise PreparationError(
            f"{label} differs from deterministic expected content: {path}; "
            f"expected SHA-256 {_sha256(expected)}, observed {_sha256(observed)}"
        )


def _ensure_directory(path: Path, label: str) -> None:
    try:
        if path.is_symlink():
            raise PreparationError(f"{label} must not be a symlink: {path}")
        if path.exists() and not path.is_dir():
            raise PreparationError(f"{label} is not a directory: {path}")
        path.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise PreparationError(f"{label} is not a safe directory: {path}")
    except PreparationError:
        raise
    except OSError as exc:
        raise PreparationError(f"cannot create {label} {path}: {exc}") from exc


def _atomic_write_if_changed(path: Path, payload: bytes) -> bool:
    try:
        if path.is_symlink():
            raise PreparationError(f"output target must not be a symlink: {path}")
        if path.exists():
            if not path.is_file():
                raise PreparationError(f"output target is not a regular file: {path}")
            if path.read_bytes() == payload:
                return False
    except PreparationError:
        raise
    except OSError as exc:
        raise PreparationError(f"cannot inspect output target {path}: {exc}") from exc

    descriptor = -1
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
        temporary_name = None
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as exc:
        raise PreparationError(f"cannot atomically write {path}: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
    return True


def _revalidate_snapshots(snapshots: Mapping[Path, bytes]) -> None:
    _validate_upstream_checkout()
    for path, expected in snapshots.items():
        observed = _read_stable_regular_file(path, f"pinned snapshot {path.name}")
        if observed != expected:
            raise PreparationError(f"pinned input changed during workload preparation: {path}")


def prepare_phase_b_workloads(
    *,
    inventory_path: Path = DEFAULT_INVENTORY,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    check: bool = False,
) -> dict[str, object]:
    """Generate or verify deterministic Phase B N2/H2O prefix workloads."""

    inventory_path = Path(inventory_path)
    output_directory = Path(output_directory)
    _validate_upstream_checkout()
    inventory, inventory_payload = _load_and_validate_inventory(inventory_path)
    manifest, variants, snapshots = _build_expected(
        inventory, inventory_path, inventory_payload
    )
    _validate_output_location(
        output_directory,
        inventory_path,
        tuple(path for path in snapshots if path != inventory_path.resolve()),
    )
    expected_manifest = _manifest_bytes(manifest)

    if check:
        for relative_path, expected_payload in variants.items():
            _verify_exact(
                output_directory / relative_path,
                expected_payload,
                f"derived Phase B workload {relative_path.as_posix()}",
            )
        _verify_exact(
            output_directory / MANIFEST_NAME,
            expected_manifest,
            "derived Phase B workload manifest",
        )
        _revalidate_snapshots(snapshots)
        return {
            "mode": "check",
            "status": "valid",
            "output_directory": str(output_directory.resolve()),
            "manifest_sha256": _sha256(expected_manifest),
            "workload_count": len(variants),
            "changed_files": [],
        }

    _ensure_directory(output_directory, "Phase B output directory")
    for family_id in EXPECTED_FAMILY_ORDER:
        _ensure_directory(output_directory / family_id, f"{family_id} output directory")

    changed_files: list[str] = []
    for relative_path, expected_payload in variants.items():
        target = output_directory / relative_path
        if _atomic_write_if_changed(target, expected_payload):
            changed_files.append(relative_path.as_posix())

    # Publish provenance only after re-reading every source snapshot and
    # rechecking the pinned checkout identity.  A concurrent input change may
    # leave unmanifested prefix files, but can never publish stale provenance.
    _revalidate_snapshots(snapshots)
    manifest_path = output_directory / MANIFEST_NAME
    if _atomic_write_if_changed(manifest_path, expected_manifest):
        changed_files.append(MANIFEST_NAME)

    return {
        "mode": "generate",
        "status": "valid",
        "output_directory": str(output_directory.resolve()),
        "manifest_sha256": _sha256(expected_manifest),
        "workload_count": len(variants),
        "changed_files": changed_files,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify every output exactly without writing files",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        outcome = prepare_phase_b_workloads(
            inventory_path=arguments.inventory,
            output_directory=arguments.output_dir,
            check=arguments.check,
        )
    except PreparationError as exc:
        print(f"prepare_phase_b_workloads: error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(outcome, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
