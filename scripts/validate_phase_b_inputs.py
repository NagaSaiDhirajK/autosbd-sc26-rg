#!/usr/bin/env python3
"""Fail-closed validation for the pinned Phase B N2/H2O input inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "reports" / "phase_b_input_inventory.json"
EXPECTED_ORIGIN = "https://github.com/r-ccs-cms/sbd.git"
EXPECTED_TAG = "v1.3.0"
EXPECTED_COMMIT = "b71e1c3ed857fcb4fb05731dc285831c1afe9ebd"
EXPECTED_REPOSITORY_PATH = "external/riken-sbd"
EXPECTED_FAMILIES = {"n2", "h2o"}
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class InventoryError(ValueError):
    """Raised when pinned provenance or input integrity does not validate."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InventoryError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise InventoryError(f"non-finite JSON constant: {token}")


def _reject_float(token: str) -> None:
    raise InventoryError(f"floating-point JSON value is not allowed: {token}")


def load_manifest(path: Path) -> Mapping[str, Any]:
    """Load UTF-8 JSON while rejecting duplicates and non-finite constants."""

    try:
        payload = Path(path).read_text(encoding="utf-8")
        parsed = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
            parse_float=_reject_float,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot load inventory {path}: {exc}") from exc
    if not isinstance(parsed, Mapping):
        raise InventoryError("inventory root must be a JSON object")
    return parsed


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    observed = set(value)
    if observed != expected:
        missing = sorted(expected - observed)
        unknown = sorted(observed - expected)
        raise InventoryError(
            f"{label} keys mismatch; missing={missing}, unknown={unknown}"
        )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InventoryError(f"{label} must be an object")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise InventoryError(f"{label} must be a nonempty string")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise InventoryError(f"{label} must be an integer >= {minimum}")
    return value


def _sha256(value: Any, label: str) -> str:
    text = _string(value, label)
    if not SHA256_RE.fullmatch(text):
        raise InventoryError(f"{label} must be a lowercase SHA-256")
    return text


def _relative_path(value: Any, label: str) -> str:
    text = _string(value, label)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != text:
        raise InventoryError(f"{label} must be a normalized project-relative path")
    return text


def _source_url(path: str) -> str:
    prefix = f"{EXPECTED_REPOSITORY_PATH}/"
    if not path.startswith(prefix):
        raise InventoryError(f"inventory path is outside {EXPECTED_REPOSITORY_PATH}: {path}")
    suffix = path.removeprefix(prefix)
    return f"https://github.com/r-ccs-cms/sbd/blob/{EXPECTED_TAG}/{suffix}"


def _validate_file_schema(
    entry: Mapping[str, Any], family: Mapping[str, Any], label: str
) -> None:
    common = {"path", "role", "source_url", "size_bytes", "sha256"}
    role = _string(entry.get("role"), f"{label}.role")
    if role == "readme":
        expected = common | {"line_count"}
    elif role == "fcidump":
        expected = common | {
            "line_count",
            "integral_record_count",
            "norb",
            "nelec",
            "ms2",
        }
    elif role == "alpha_determinants":
        expected = common | {"row_count", "string_width", "occupied_orbitals"}
    else:
        raise InventoryError(f"{label}.role is unsupported: {role}")
    _exact_keys(entry, expected, label)
    path = _relative_path(entry["path"], f"{label}.path")
    family_id = _string(family["family_id"], "family_id")
    expected_prefix = f"{EXPECTED_REPOSITORY_PATH}/data/{family_id}/"
    if not path.startswith(expected_prefix):
        raise InventoryError(f"{label}.path is outside family directory")
    if entry["source_url"] != _source_url(path):
        raise InventoryError(f"{label}.source_url does not match its pinned path")
    _integer(entry["size_bytes"], f"{label}.size_bytes", minimum=1)
    _sha256(entry["sha256"], f"{label}.sha256")
    if role in {"readme", "fcidump"}:
        _integer(entry["line_count"], f"{label}.line_count", minimum=1)
    if role == "fcidump":
        _integer(
            entry["integral_record_count"],
            f"{label}.integral_record_count",
            minimum=1,
        )
        for field in ("norb", "nelec"):
            _integer(entry[field], f"{label}.{field}", minimum=1)
            if entry[field] != family[field]:
                raise InventoryError(f"{label}.{field} disagrees with family metadata")
        _integer(entry["ms2"], f"{label}.ms2")
        if entry["ms2"] != family["ms2"]:
            raise InventoryError(f"{label}.ms2 disagrees with family metadata")
    if role == "alpha_determinants":
        _integer(entry["row_count"], f"{label}.row_count", minimum=1)
        width = _integer(entry["string_width"], f"{label}.string_width", minimum=1)
        occupied = _integer(
            entry["occupied_orbitals"],
            f"{label}.occupied_orbitals",
            minimum=1,
        )
        if width != family["norb"]:
            raise InventoryError(f"{label}.string_width disagrees with NORB")
        if occupied * 2 != family["nelec"]:
            raise InventoryError(f"{label}.occupied_orbitals disagrees with NELEC")


def validate_manifest_schema(manifest: Mapping[str, Any]) -> None:
    """Validate a closed schema and all internal inventory relationships."""

    _exact_keys(
        manifest,
        {"schema_version", "purpose", "source_repository", "license", "families"},
        "inventory",
    )
    if _integer(manifest["schema_version"], "inventory.schema_version", minimum=1) != 1:
        raise InventoryError("inventory.schema_version must be exactly 1")
    if manifest["purpose"] != "phase_b_input_provenance_and_integrity":
        raise InventoryError("inventory purpose mismatch")

    repository = _mapping(manifest["source_repository"], "source_repository")
    _exact_keys(
        repository,
        {
            "path",
            "origin_url",
            "tag",
            "commit",
            "checkout_clean_required",
            "allowed_use",
        },
        "source_repository",
    )
    expected_repository = {
        "path": EXPECTED_REPOSITORY_PATH,
        "origin_url": EXPECTED_ORIGIN,
        "tag": EXPECTED_TAG,
        "commit": EXPECTED_COMMIT,
        "checkout_clean_required": True,
        "allowed_use": "input_data_only",
    }
    if dict(repository) != expected_repository:
        raise InventoryError("source_repository does not match the pinned data-only source")
    if repository["checkout_clean_required"] is not True:
        raise InventoryError("source_repository.checkout_clean_required must be true")

    license_entry = _mapping(manifest["license"], "license")
    _exact_keys(
        license_entry,
        {"path", "source_url", "spdx", "size_bytes", "sha256"},
        "license",
    )
    license_path = _relative_path(license_entry["path"], "license.path")
    if license_path != f"{EXPECTED_REPOSITORY_PATH}/LICENSE.txt":
        raise InventoryError("license.path mismatch")
    if license_entry["source_url"] != _source_url(license_path):
        raise InventoryError("license.source_url mismatch")
    if license_entry["spdx"] != "Apache-2.0":
        raise InventoryError("license SPDX identifier must be Apache-2.0")
    _integer(license_entry["size_bytes"], "license.size_bytes", minimum=1)
    _sha256(license_entry["sha256"], "license.sha256")

    families = manifest["families"]
    if not isinstance(families, list) or len(families) != 2:
        raise InventoryError("families must contain exactly N2 and H2O")
    seen_families: set[str] = set()
    seen_paths: set[str] = set()
    for family_index, raw_family in enumerate(families):
        label = f"families[{family_index}]"
        family = _mapping(raw_family, label)
        _exact_keys(
            family,
            {
                "family_id",
                "molecule",
                "basis",
                "source_tree_url",
                "norb",
                "nelec",
                "ms2",
                "smallest_complete_pair",
                "files",
            },
            label,
        )
        family_id = _string(family["family_id"], f"{label}.family_id")
        if family_id in seen_families:
            raise InventoryError(f"duplicate family_id: {family_id}")
        seen_families.add(family_id)
        _string(family["molecule"], f"{label}.molecule")
        _string(family["basis"], f"{label}.basis")
        expected_tree = (
            f"https://github.com/r-ccs-cms/sbd/tree/{EXPECTED_TAG}/data/{family_id}"
        )
        if family["source_tree_url"] != expected_tree:
            raise InventoryError(f"{label}.source_tree_url mismatch")
        norb = _integer(family["norb"], f"{label}.norb", minimum=1)
        nelec = _integer(family["nelec"], f"{label}.nelec", minimum=1)
        _integer(family["ms2"], f"{label}.ms2")
        if nelec % 2 != 0 or nelec > 2 * norb:
            raise InventoryError(f"{label} has invalid closed-shell electron metadata")

        files = family["files"]
        if not isinstance(files, list) or not files:
            raise InventoryError(f"{label}.files must be a nonempty list")
        roles: dict[str, list[Mapping[str, Any]]] = {}
        entries_by_path: dict[str, Mapping[str, Any]] = {}
        for file_index, raw_entry in enumerate(files):
            file_label = f"{label}.files[{file_index}]"
            entry = _mapping(raw_entry, file_label)
            _validate_file_schema(entry, family, file_label)
            path = str(entry["path"])
            if path in seen_paths:
                raise InventoryError(f"duplicate inventory path: {path}")
            seen_paths.add(path)
            entries_by_path[path] = entry
            roles.setdefault(str(entry["role"]), []).append(entry)
        if len(roles.get("readme", [])) != 1 or len(roles.get("fcidump", [])) != 1:
            raise InventoryError(f"{label} must have exactly one README and FCIDUMP")
        if not roles.get("alpha_determinants"):
            raise InventoryError(f"{label} has no determinant files")

        pair = _mapping(family["smallest_complete_pair"], f"{label}.smallest_complete_pair")
        _exact_keys(
            pair,
            {
                "fcidump_path",
                "alpha_determinants_path",
                "n_alpha_strings",
                "n_configurations",
            },
            f"{label}.smallest_complete_pair",
        )
        fcidump_path = _relative_path(
            pair["fcidump_path"], f"{label}.smallest_complete_pair.fcidump_path"
        )
        determinant_path = _relative_path(
            pair["alpha_determinants_path"],
            f"{label}.smallest_complete_pair.alpha_determinants_path",
        )
        if entries_by_path.get(fcidump_path, {}).get("role") != "fcidump":
            raise InventoryError(f"{label} smallest pair does not name its FCIDUMP")
        determinant = entries_by_path.get(determinant_path)
        if determinant is None or determinant.get("role") != "alpha_determinants":
            raise InventoryError(f"{label} smallest pair does not name determinant data")
        n_alpha = _integer(
            pair["n_alpha_strings"],
            f"{label}.smallest_complete_pair.n_alpha_strings",
            minimum=1,
        )
        if determinant["row_count"] != n_alpha:
            raise InventoryError(f"{label} smallest-pair row count mismatch")
        n_configurations = _integer(
            pair["n_configurations"],
            f"{label}.smallest_complete_pair.n_configurations",
            minimum=1,
        )
        if n_configurations != n_alpha * n_alpha:
            raise InventoryError(f"{label} smallest-pair product count mismatch")
    if seen_families != EXPECTED_FAMILIES:
        raise InventoryError(f"family IDs mismatch: {sorted(seen_families)}")


def _git_output(repository: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise InventoryError(f"git {' '.join(arguments)} failed for {repository}: {exc}") from exc
    return result.stdout.strip()


def _validate_repository(project_root: Path, repository: Mapping[str, Any]) -> None:
    repository_path = project_root / str(repository["path"])
    if not repository_path.is_dir() or repository_path.is_symlink():
        raise InventoryError(f"pinned repository is missing or unsafe: {repository_path}")
    if _git_output(repository_path, "remote", "get-url", "origin") != EXPECTED_ORIGIN:
        raise InventoryError("RIKEN input checkout origin mismatch")
    if _git_output(repository_path, "rev-parse", "HEAD") != EXPECTED_COMMIT:
        raise InventoryError("RIKEN input checkout commit mismatch")
    if _git_output(repository_path, "describe", "--tags", "--exact-match", "HEAD") != EXPECTED_TAG:
        raise InventoryError("RIKEN input checkout is not at exact tag v1.3.0")
    if _git_output(repository_path, "rev-parse", f"refs/tags/{EXPECTED_TAG}^{{commit}}") != EXPECTED_COMMIT:
        raise InventoryError("RIKEN tag does not resolve to the pinned commit")
    if _git_output(repository_path, "status", "--porcelain=v1", "--untracked-files=all"):
        raise InventoryError("RIKEN input checkout is dirty")


def _safe_project_file(project_root: Path, relative_path: str) -> Path:
    root = project_root.resolve(strict=True)
    path = project_root / relative_path
    if path.is_symlink():
        raise InventoryError(f"inventory path must not be a symlink: {relative_path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise InventoryError(f"inventory file is missing: {relative_path}") from exc
    if not resolved.is_relative_to(root):
        raise InventoryError(f"inventory path escapes project root: {relative_path}")
    mode = resolved.stat().st_mode
    if not stat.S_ISREG(mode):
        raise InventoryError(f"inventory path is not a regular file: {relative_path}")
    return resolved


def _read_stable_file(path: Path) -> bytes:
    before = path.stat()
    payload = path.read_bytes()
    after = path.stat()
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise InventoryError(f"inventory file changed while reading: {path}")
    return payload


def _validate_common_file(entry: Mapping[str, Any], project_root: Path) -> bytes:
    relative_path = str(entry["path"])
    path = _safe_project_file(project_root, relative_path)
    payload = _read_stable_file(path)
    if len(payload) != entry["size_bytes"]:
        raise InventoryError(
            f"{relative_path} size mismatch: expected {entry['size_bytes']}, observed {len(payload)}"
        )
    observed_hash = hashlib.sha256(payload).hexdigest()
    if observed_hash != entry["sha256"]:
        raise InventoryError(
            f"{relative_path} SHA-256 mismatch: expected {entry['sha256']}, observed {observed_hash}"
        )
    return payload


def _decode_lines(payload: bytes, relative_path: str) -> list[str]:
    try:
        return payload.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise InventoryError(f"{relative_path} must be ASCII text") from exc


def _header_integer(header: str, field: str, relative_path: str) -> int:
    match = re.search(rf"\b{field}\s*=\s*(-?\d+)", header, flags=re.IGNORECASE)
    if match is None:
        raise InventoryError(f"{relative_path} FCIDUMP header has no {field}")
    return int(match.group(1))


def _validate_fcidump(entry: Mapping[str, Any], payload: bytes) -> None:
    relative_path = str(entry["path"])
    lines = _decode_lines(payload, relative_path)
    if len(lines) != entry["line_count"]:
        raise InventoryError(f"{relative_path} line-count mismatch")
    end_markers = [index for index, line in enumerate(lines) if line.strip().upper() == "&END"]
    if end_markers != [3] or not lines[0].lstrip().upper().startswith("&FCI"):
        raise InventoryError(f"{relative_path} must have one four-line &FCI/&END header")
    header = " ".join(lines[:4])
    for field in ("norb", "nelec", "ms2"):
        if _header_integer(header, field, relative_path) != entry[field]:
            raise InventoryError(f"{relative_path} {field.upper()} mismatch")
    body = lines[4:]
    if len(body) != entry["integral_record_count"]:
        raise InventoryError(f"{relative_path} integral-record count mismatch")
    zero_index_records = 0
    saw_norb_index = False
    for record_index, line in enumerate(body, start=1):
        fields = line.split()
        if len(fields) != 5:
            raise InventoryError(f"{relative_path} integral {record_index} must have five fields")
        try:
            value = float(fields[0])
            indices = tuple(int(field) for field in fields[1:])
        except ValueError as exc:
            raise InventoryError(f"{relative_path} integral {record_index} is malformed") from exc
        if not math.isfinite(value):
            raise InventoryError(f"{relative_path} integral {record_index} is non-finite")
        if any(index < 0 or index > entry["norb"] for index in indices):
            raise InventoryError(f"{relative_path} integral {record_index} index out of bounds")
        zero_index_records += int(all(index == 0 for index in indices))
        saw_norb_index = saw_norb_index or entry["norb"] in indices
    if zero_index_records != 1 or not saw_norb_index:
        raise InventoryError(f"{relative_path} has invalid FCIDUMP boundary records")


def _validate_determinants(entry: Mapping[str, Any], payload: bytes) -> None:
    relative_path = str(entry["path"])
    lines = _decode_lines(payload, relative_path)
    if len(lines) != entry["row_count"]:
        raise InventoryError(f"{relative_path} determinant row-count mismatch")
    if any(not line for line in lines):
        raise InventoryError(f"{relative_path} contains a blank determinant row")
    for row_index, line in enumerate(lines, start=1):
        if len(line) != entry["string_width"]:
            raise InventoryError(f"{relative_path} row {row_index} width mismatch")
        if set(line) - {"0", "1"}:
            raise InventoryError(f"{relative_path} row {row_index} is not binary")
        if line.count("1") != entry["occupied_orbitals"]:
            raise InventoryError(f"{relative_path} row {row_index} occupation mismatch")
    if len(set(lines)) != len(lines):
        raise InventoryError(f"{relative_path} contains duplicate determinant rows")


def _validate_file(entry: Mapping[str, Any], project_root: Path) -> None:
    payload = _validate_common_file(entry, project_root)
    role = entry["role"]
    if role == "readme":
        lines = _decode_lines(payload, str(entry["path"]))
        if len(lines) != entry["line_count"]:
            raise InventoryError(f"{entry['path']} line-count mismatch")
    elif role == "fcidump":
        _validate_fcidump(entry, payload)
    elif role == "alpha_determinants":
        _validate_determinants(entry, payload)


def _validate_complete_data_inventory(
    project_root: Path, families: Sequence[Mapping[str, Any]]
) -> None:
    expected = {
        str(entry["path"])
        for family in families
        for entry in family["files"]
    }
    observed: set[str] = set()
    for family_id in EXPECTED_FAMILIES:
        directory = project_root / EXPECTED_REPOSITORY_PATH / "data" / family_id
        if not directory.is_dir() or directory.is_symlink():
            raise InventoryError(f"family directory is missing or unsafe: {directory}")
        for path in directory.rglob("*"):
            if path.is_file() or path.is_symlink():
                observed.add(path.relative_to(project_root).as_posix())
    if observed != expected:
        raise InventoryError(
            "data inventory is incomplete; "
            f"missing={sorted(expected - observed)}, unlisted={sorted(observed - expected)}"
        )


def validate_inventory(manifest_path: Path, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Validate source identity, complete inventory, bytes, and file structure."""

    project_root = Path(project_root).resolve(strict=True)
    manifest_path = Path(manifest_path).resolve(strict=True)
    manifest = load_manifest(manifest_path)
    validate_manifest_schema(manifest)
    repository = _mapping(manifest["source_repository"], "source_repository")
    _validate_repository(project_root, repository)
    license_entry = _mapping(manifest["license"], "license")
    license_payload = _validate_common_file(license_entry, project_root)
    if b"Apache License" not in license_payload or b"Version 2.0" not in license_payload:
        raise InventoryError("license content does not identify Apache License 2.0")
    families = [
        _mapping(family, f"families[{index}]")
        for index, family in enumerate(manifest["families"])
    ]
    _validate_complete_data_inventory(project_root, families)
    artifact_count = 1
    determinant_count = 0
    for family in families:
        for entry in family["files"]:
            _validate_file(entry, project_root)
            artifact_count += 1
            determinant_count += int(entry["role"] == "alpha_determinants")
    manifest_payload = manifest_path.read_bytes()
    return {
        "status": "pass",
        "manifest": manifest_path.relative_to(project_root).as_posix()
        if manifest_path.is_relative_to(project_root)
        else str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
        "source_commit": EXPECTED_COMMIT,
        "families": sorted(EXPECTED_FAMILIES),
        "artifact_count": artifact_count,
        "determinant_file_count": determinant_count,
    }


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)
    try:
        result = validate_inventory(arguments.manifest, arguments.project_root)
    except (InventoryError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
