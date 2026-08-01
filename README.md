# AutoSBD

AutoSBD is a reproducible, single-node CPU/GPU runtime-selection project for authentic Selected-Basis Diagonalization (SBD) workloads. It wraps an existing SBD implementation; it does not replace the eigensolver or claim the upstream GPU port as a new contribution.

## Upstream and toolchain

The primary implementation is the official [`AMD-HPC/amd-sbd`](https://github.com/AMD-HPC/amd-sbd) `sc26-artifacts` branch pinned to commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`, as identified by the OpenMP paper and project handoff. Both primary executables are built from that same unmodified commit through one NVIDIA HPC SDK 26.5 path:

- CPU: NVHPC `nvc++` OpenMP, 16-thread candidate;
- GPU: NVHPC `nvc++` OpenMP target offload for the NVIDIA L4 (`cc89`), using the SDK's bundled CUDA 13.2 toolchain.

The earlier [`r-ccs-cms/sbd`](https://github.com/r-ccs-cms/sbd) `v1.3.0` work is retained only as historical fallback evidence. No RIKEN executable or input is used by the primary Stage 2 runner or its correctness result.

Exact source, compiler, flags, binary hashes, and license provenance are recorded in [`reports/BUILD_PROVENANCE.md`](reports/BUILD_PROVENANCE.md).

## Current status

Stages 0–2 are complete. Stage 3 workload preparation and five-size CPU/GPU correctness calibration are also complete: the machine and upstream builds are documented, identical-input AMD CPU/GPU correctness passes at every calibrated size, and the schema-v2 single-run/resumable-sweep harness is implemented. The current suite has 89 passing tests, including Stage 3 workload, calibration-manifest, multi-input, and clean-resume coverage.

The hardened runner provides:

- strict YAML configuration and pre-execution FCIDUMP/determinant features;
- admission checks for the exact official upstream commit, clean upstream tree, expected binaries, build flags, and NVHPC compiler;
- a node-wide run lock, fail-closed GPU-idle checks, CPU-core and GPU-memory guards, bounded process-group execution, and host/GPU resource sampling;
- immutable atomic schema-v2 JSON records with logical identity plus attempt identity, input re-hashing, artifact hashes, claims, and exact resume behavior;
- explicit process, scientific-correctness, monitoring, and timing-eligibility states; and
- a validation-manifest gate that prevents correctness smoke runs from silently becoming benchmark evidence.

The schema-v2 Fe₄S₄ CPU and GPU runs converged and agreed in energy, density, and iteration count at all five determinant-prefix sizes. Every calibration record has `timing_eligible=false`; its wall time is diagnostic only and is not a final performance result. See [`reports/RESULTS.md`](reports/RESULTS.md) and [`reports/LIMITATIONS.md`](reports/LIMITATIONS.md).

The bounded Stage 3 pilot is configured and manifest-gated but has not yet run. Final timing, held-out evaluation, and the runtime selector have not yet been completed.

## Reproduce the engineering checks

The repository uses Python 3.10 and the project-local `.venv`; the only Stage 2 runtime Python dependency is pinned in `requirements-lock.txt`. From the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
PYTHONPATH=src bash scripts/smoke_test.sh
```

Prepare and verify the official-AMD Fe₄S₄ determinant-count variants:

```bash
.venv/bin/python scripts/prepare_workloads.py
.venv/bin/python scripts/prepare_workloads.py --check
```

These are exact nested prefixes of one official Fe₄S₄ determinant list: derived size variants of one chemical family, not independent chemistry datasets.

Build the official primary executables after NVIDIA HPC SDK 26.5 and the documented system dependencies are available:

```bash
scripts/build_upstream.sh amd-all
```

Run or resume one configured correctness trial:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_one.py \
  configs/stage2_amd_smoke.yaml \
  --candidate amd-cpu-16 \
  --require-success
```

Use `scripts/run_sweep.py` for a sequential resumable configuration sweep. The runner performs safety checks itself, but final timing still requires the approved protocol, warmups, a linked correctness manifest, a clean project tree, and sequential execution.

## Evidence map

- [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md): objective, experimental design, status, and definition of done
- [`reports/ENVIRONMENT.md`](reports/ENVIRONMENT.md): node, dependency, NVIDIA SDK, and Python environment
- [`reports/BUILD_PROVENANCE.md`](reports/BUILD_PROVENANCE.md): exact upstream/build provenance
- [`reports/stage2_amd_correctness.json`](reports/stage2_amd_correctness.json): machine-readable schema-v2 CPU/GPU comparison
- [`reports/stage2_amd_validation_manifest.json`](reports/stage2_amd_validation_manifest.json): hash-linked correctness evidence and eligibility scope
- [`reports/stage3_calibration_manifest.json`](reports/stage3_calibration_manifest.json): deterministic five-input CPU/GPU correctness gate
- [`configs/stage3_pilot.yaml`](configs/stage3_pilot.yaml): bounded manifest-linked pilot protocol
- `results/raw/*.json`: immutable per-attempt records; failures and skips are retained

Internal reports and reproducibility artifacts are generated by the engineering workflow. The student's abstract, submission summary, poster, and other submission prose remain exclusively student-authored.
