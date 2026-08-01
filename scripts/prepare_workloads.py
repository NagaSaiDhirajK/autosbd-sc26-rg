#!/usr/bin/env python3
"""Prepare audited determinant-count variants of the pinned AMD Fe4S4 input.

The generated determinant files are byte-exact, nested prefixes of the official
``AlphaDets.txt`` ordering.  They are size variants of one chemical system, not
independent chemical families.  The companion FCIDUMP is validated read-only
and is never copied or modified by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_ROOT = REPOSITORY_ROOT / "external" / "amd-sbd"
SAMPLE_DIRECTORY = (
    UPSTREAM_ROOT / "samples" / "selected_basis_diagonalization"
)
DEFAULT_SOURCE = SAMPLE_DIRECTORY / "AlphaDets.txt"
DEFAULT_FCIDUMP = SAMPLE_DIRECTORY / "fcidump_Fe4S4.txt"
DEFAULT_OUTPUT_DIRECTORY = (
    REPOSITORY_ROOT / "data" / "derived" / "amd_fe4s4_prefixes"
)

UPSTREAM_REPOSITORY = "https://github.com/AMD-HPC/amd-sbd.git"
UPSTREAM_COMMIT = "729cfa3a5011fb805eb9e686a7711f6919836dcb"
EXPECTED_SOURCE_SHA256 = (
    "b1aa7e60cfde6adc39f9271bb2c6d8d15774a694e746e66bab44db9842748f68"
)
EXPECTED_FCIDUMP_SHA256 = (
    "9a74e2035f76218f1d02aa641a5be256c0b685f0382b1612fc261117dd1b6e93"
)
EXPECTED_SOURCE_BYTES = 9_028
EXPECTED_FCIDUMP_BYTES = 9_584_950
EXPECTED_DETERMINANT_COUNT = 244
EXPECTED_DETERMINANT_WIDTH = 36
EXPECTED_OCCUPANCY = 27
PREFIX_SIZES = (32, 55, 100, 174, 244)
MANIFEST_NAME = "manifest.json"


class PreparationError(RuntimeError):
    """Raised when provenance, format, output, or verification checks fail."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalize_repository_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized


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
        raise PreparationError(f"cannot inspect official AMD checkout: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        raise PreparationError(f"cannot inspect official AMD checkout: {detail}")
    return completed.stdout.strip()


def _validate_upstream_checkout() -> None:
    observed_url = _git_output("remote", "get-url", "origin")
    if _normalize_repository_url(observed_url) != _normalize_repository_url(
        UPSTREAM_REPOSITORY
    ):
        raise PreparationError(
            "official AMD origin mismatch: "
            f"expected {UPSTREAM_REPOSITORY}, observed {observed_url}"
        )
    observed_commit = _git_output("rev-parse", "HEAD")
    if observed_commit != UPSTREAM_COMMIT:
        raise PreparationError(
            "official AMD commit mismatch: "
            f"expected {UPSTREAM_COMMIT}, observed {observed_commit}"
        )
    if _git_output("status", "--porcelain"):
        raise PreparationError("official AMD checkout has local modifications")


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        if not path.is_file():
            raise PreparationError(f"{label} is not a regular file: {path}")
        return path.read_bytes()
    except PreparationError:
        raise
    except OSError as exc:
        raise PreparationError(f"cannot read {label} {path}: {exc}") from exc


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


def _validate_output_location(
    output_directory: Path,
    source: Path,
    fcidump: Path,
) -> None:
    resolved_output = output_directory.resolve()
    if _is_within(resolved_output, UPSTREAM_ROOT):
        raise PreparationError(
            f"refusing to generate derived files inside pinned upstream: "
            f"{output_directory}"
        )
    for name in (*(_variant_name(size) for size in PREFIX_SIZES), MANIFEST_NAME):
        target = (resolved_output / name).resolve()
        if target in {source.resolve(), fcidump.resolve()}:
            raise PreparationError(f"refusing to overwrite an official input: {target}")


def _validate_determinant_source(path: Path) -> tuple[bytes, tuple[bytes, ...]]:
    payload = _read_bytes(path, "determinant source")
    lines = tuple(payload.splitlines(keepends=True))

    if len(lines) != EXPECTED_DETERMINANT_COUNT:
        raise PreparationError(
            "unexpected determinant count: "
            f"expected {EXPECTED_DETERMINANT_COUNT}, observed {len(lines)}"
        )
    for line_number, line in enumerate(lines, start=1):
        if len(line) != EXPECTED_DETERMINANT_WIDTH + 1 or not line.endswith(b"\n"):
            raise PreparationError(
                f"invalid determinant record length/newline at line {line_number}"
            )
        determinant = line[:-1]
        if any(character not in (ord("0"), ord("1")) for character in determinant):
            raise PreparationError(
                f"non-binary determinant character at line {line_number}"
            )
        if determinant.count(b"1") != EXPECTED_OCCUPANCY:
            raise PreparationError(
                f"unexpected determinant occupancy at line {line_number}"
            )

    if len(set(lines)) != len(lines):
        raise PreparationError("determinant source contains duplicate records")
    if list(lines) != sorted(lines):
        raise PreparationError("determinant source ordering is not canonical")
    if len(payload) != EXPECTED_SOURCE_BYTES:
        raise PreparationError(
            f"unexpected determinant byte count: expected {EXPECTED_SOURCE_BYTES}, "
            f"observed {len(payload)}"
        )

    observed_hash = _sha256(payload)
    if observed_hash != EXPECTED_SOURCE_SHA256:
        raise PreparationError(
            "unexpected determinant source SHA-256: "
            f"expected {EXPECTED_SOURCE_SHA256}, observed {observed_hash}"
        )
    return payload, lines


def _validate_fcidump(path: Path) -> bytes:
    payload = _read_bytes(path, "companion FCIDUMP")
    if len(payload) != EXPECTED_FCIDUMP_BYTES:
        raise PreparationError(
            f"unexpected FCIDUMP byte count: expected {EXPECTED_FCIDUMP_BYTES}, "
            f"observed {len(payload)}"
        )
    observed_hash = _sha256(payload)
    if observed_hash != EXPECTED_FCIDUMP_SHA256:
        raise PreparationError(
            "unexpected FCIDUMP SHA-256: "
            f"expected {EXPECTED_FCIDUMP_SHA256}, observed {observed_hash}"
        )
    return payload


def _variant_name(size: int) -> str:
    return f"AlphaDets_n{size:04d}.txt"


def _build_manifest(
    source: Path,
    source_payload: bytes,
    fcidump: Path,
    fcidump_payload: bytes,
    variants: dict[int, bytes],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "dataset_id": "amd-sbd-fe4s4-derived-determinant-prefixes",
        "dataset_scope": {
            "chemical_system": "Fe4S4",
            "family_count": 1,
            "distinct_chemical_families": False,
            "variant_type": "derived_determinant_prefix_size",
            "label": (
                "Derived size variants of one Fe4S4 input; these are not "
                "distinct chemical families."
            ),
        },
        "upstream": {
            "repository": UPSTREAM_REPOSITORY,
            "commit": UPSTREAM_COMMIT,
            "source_determinants": {
                "path": _display_path(source),
                "sha256": _sha256(source_payload),
                "bytes": len(source_payload),
                "line_count": len(source_payload.splitlines()),
                "determinant_width": EXPECTED_DETERMINANT_WIDTH,
                "occupancy": EXPECTED_OCCUPANCY,
            },
            "companion_fcidump": {
                "path": _display_path(fcidump),
                "sha256": _sha256(fcidump_payload),
                "bytes": len(fcidump_payload),
                "access": "read_only_validation",
                "copied_or_modified": False,
            },
        },
        "derivation": {
            "operation": "byte_exact_ordered_prefix",
            "nested": True,
            "source_order_preserved": True,
            "source_lines_preserved": True,
            "prefix_sizes": list(PREFIX_SIZES),
        },
        "variants": [
            {
                "id": f"fe4s4-prefix-{size:04d}",
                "determinant_count": size,
                "output": {
                    "path": _variant_name(size),
                    "sha256": _sha256(variants[size]),
                    "bytes": len(variants[size]),
                    "line_count": size,
                },
            }
            for size in PREFIX_SIZES
        ],
    }


def _manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _verify_exact(path: Path, expected: bytes, label: str) -> None:
    observed = _read_bytes(path, label)
    if observed != expected:
        raise PreparationError(
            f"{label} differs from deterministic expected content: {path}; "
            f"expected SHA-256 {_sha256(expected)}, observed {_sha256(observed)}"
        )


def _atomic_write_if_changed(path: Path, payload: bytes) -> bool:
    try:
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


def prepare_workloads(
    *,
    source: Path = DEFAULT_SOURCE,
    fcidump: Path = DEFAULT_FCIDUMP,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    check: bool = False,
) -> dict[str, object]:
    """Generate or verify deterministic Fe4S4 determinant-prefix variants."""

    source = Path(source)
    fcidump = Path(fcidump)
    output_directory = Path(output_directory)
    _validate_output_location(output_directory, source, fcidump)
    _validate_upstream_checkout()
    source_payload, source_lines = _validate_determinant_source(source)
    fcidump_payload = _validate_fcidump(fcidump)
    variants = {
        size: b"".join(source_lines[:size])
        for size in PREFIX_SIZES
    }
    manifest = _build_manifest(
        source, source_payload, fcidump, fcidump_payload, variants
    )
    expected_manifest = _manifest_bytes(manifest)

    if check:
        for size in PREFIX_SIZES:
            _verify_exact(
                output_directory / _variant_name(size),
                variants[size],
                f"derived determinant variant n={size}",
            )
        _verify_exact(
            output_directory / MANIFEST_NAME,
            expected_manifest,
            "derived workload manifest",
        )
        return {
            "mode": "check",
            "status": "valid",
            "output_directory": str(output_directory.resolve()),
            "manifest_sha256": _sha256(expected_manifest),
            "changed_files": [],
        }

    try:
        output_directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PreparationError(
            f"cannot create output directory {output_directory}: {exc}"
        ) from exc

    changed_files: list[str] = []
    for size in PREFIX_SIZES:
        target = output_directory / _variant_name(size)
        if _atomic_write_if_changed(target, variants[size]):
            changed_files.append(target.name)

    # Re-read both official inputs before publishing the manifest.  This makes a
    # concurrent source change fail closed instead of producing stale provenance.
    final_source_payload, _ = _validate_determinant_source(source)
    final_fcidump_payload = _validate_fcidump(fcidump)
    if final_source_payload != source_payload or final_fcidump_payload != fcidump_payload:
        raise PreparationError("official input changed during workload preparation")

    manifest_path = output_directory / MANIFEST_NAME
    if _atomic_write_if_changed(manifest_path, expected_manifest):
        changed_files.append(manifest_path.name)

    return {
        "mode": "generate",
        "status": "valid",
        "output_directory": str(output_directory.resolve()),
        "manifest_sha256": _sha256(expected_manifest),
        "changed_files": changed_files,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate or verify audited determinant-prefix size variants of the "
            "pinned AMD Fe4S4 sample."
        )
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--fcidump", type=Path, default=DEFAULT_FCIDUMP)
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify all outputs exactly without writing any files",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        outcome = prepare_workloads(
            source=args.source,
            fcidump=args.fcidump,
            output_directory=args.output_dir,
            check=args.check,
        )
    except PreparationError as exc:
        print(f"prepare_workloads: error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
