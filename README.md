# AutoSBD

AutoSBD is a reproducible, single-node CPU/GPU runtime-selection project for authentic Selected-Basis Diagonalization (SBD) workloads. It wraps an existing SBD implementation; it does not replace the eigensolver or claim the upstream GPU port as a new contribution.

## Upstream and toolchain

The primary implementation is the official [`AMD-HPC/amd-sbd`](https://github.com/AMD-HPC/amd-sbd) `sc26-artifacts` branch pinned to commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`, as identified by the OpenMP paper and project handoff. Both primary executables are built from that same unmodified commit through one NVIDIA HPC SDK 26.5 path:

- CPU: NVHPC `nvc++` OpenMP, 16-thread candidate;
- GPU: NVHPC `nvc++` OpenMP target offload for the NVIDIA L4 (`cc89`), using the SDK's bundled CUDA 13.2 toolchain.

The earlier [`r-ccs-cms/sbd`](https://github.com/r-ccs-cms/sbd) `v1.3.0` solver work is retained only as historical fallback evidence. Phase B reuses pinned N₂/H₂O bytes from that repository as licensed input data, but no RIKEN executable is built, run, timed, trained on, or selected.

Exact source, compiler, flags, binary hashes, and license provenance are recorded in [`reports/BUILD_PROVENANCE.md`](reports/BUILD_PROVENANCE.md).

## Current status

Stages 0–4 and the current single-family Stage 5 evaluation are complete. The machine and official AMD builds are documented; identical-input CPU/GPU correctness passes at all five calibrated Fe₄S₄ sizes and all ten exact N₂/H₂O Phase B grid inputs. Phase B2 now has ten deterministic size variants, config-v2/raw-v3 family identity, a 20-record schema-v3 correctness gate, a strict external registry for the immutable Fe₄S₄ records, and a completed 40-record N₂/H₂O pilot with 20 excluded warmups and 20 eligible single-repetition measurements. The frozen Stage 4 campaign remains 48 immutable records—10 excluded warmups and 38 timing-eligible measurements—with no failure, timeout, OOM, skip, or correctness error. The current suite passes all 168 tests. Repeated N₂/H₂O timing is frozen but awaiting explicit approval; multifamily evaluation remains pending.

The hardened runner provides:

- strict YAML configuration and pre-execution FCIDUMP/determinant features;
- admission checks for the exact official upstream commit, clean upstream tree, expected binaries, build flags, and NVHPC compiler;
- a node-wide run lock, fail-closed GPU-idle checks, CPU-core and GPU-memory guards, bounded process-group execution, host/GPU resource sampling, and optional stop-on-first-non-success sweep execution;
- immutable atomic JSON records with preserved schema-v2 history and family-aware schema-v3 logical/attempt identity, input re-hashing, artifact hashes, claims, and exact resume behavior;
- explicit process, scientific-correctness, monitoring, and timing-eligibility states; and
- a validation-manifest gate that prevents correctness smoke runs from silently becoming benchmark evidence.

The schema-v2 Fe₄S₄ CPU and GPU runs converged and agreed in energy, density, and iteration count at all five determinant-prefix sizes. Every calibration record has `timing_eligible=false`; its wall time is diagnostic only and is not a final performance result. See [`reports/RESULTS.md`](reports/RESULTS.md) and [`reports/LIMITATIONS.md`](reports/LIMITATIONS.md).

The repeated Stage 4 medians preserve the observed CPU16/GPU winner flip between 1,024 and 3,025 configurations. In the strict largest-size holdout, the corrected static threshold and both trees select the GPU with zero normalized regret; fixed CPU16 has normalized regret `3.542081714297355`. Across the five leave-one-instance-out sensitivity folds, the full and size-only trees have identical `0.8` selection accuracy and geometric selected/oracle runtime `1.0472132783479557`; the corrected geometric-midpoint threshold has `0.6` accuracy and geometric selected/oracle runtime `1.078390418002942`. There are no invalid selections or failures. These remain size-held-out timing results from one Fe₄S₄ family, not cross-family performance evidence. The schema-v3 Phase B gate validates all ten exact N₂/H₂O grid hashes on the same official AMD CPU/GPU binaries through 20 timing-ineligible correctness records. The completed one-repetition pilot brackets a CPU/GPU flip between 3,025 and 10,000 configurations in both families, but it is planning evidence rather than final repeated timing. The frozen 104-record final campaign is awaiting explicit approval; cross-family evaluation remains pending.

## Reproduce the engineering checks

The repository uses Python 3.10 and the project-local `.venv`; the complete runtime and analysis environment is pinned in `requirements-lock.txt`. From the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
PYTHONPATH=src bash scripts/smoke_test.sh
```

Prepare and verify the official-AMD Fe₄S₄ determinant-count variants:

```bash
.venv/bin/python scripts/prepare_workloads.py
.venv/bin/python scripts/prepare_workloads.py --check
.venv/bin/python scripts/prepare_phase_b_workloads.py
.venv/bin/python scripts/prepare_phase_b_workloads.py --check
PYTHONPATH=src .venv/bin/python scripts/build_family_registry.py --check
```

The Fe₄S₄ outputs are size variants of one official determinant list. The Phase B outputs are family-local prefixes of the pinned N₂ and H₂O lists. No prefix is an additional independent chemistry family.

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

Use `scripts/run_sweep.py` for a sequential resumable configuration sweep. The runner performs safety checks itself, but any new timing campaign still requires an approved protocol, warmups, a linked correctness manifest, a clean project tree, and sequential execution.

## Evidence map

- [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md): objective, experimental design, status, and definition of done
- [`reports/ENVIRONMENT.md`](reports/ENVIRONMENT.md): node, dependency, NVIDIA SDK, and Python environment
- [`reports/BUILD_PROVENANCE.md`](reports/BUILD_PROVENANCE.md): exact upstream/build provenance
- [`reports/stage2_amd_correctness.json`](reports/stage2_amd_correctness.json): machine-readable schema-v2 CPU/GPU comparison
- [`reports/stage2_amd_validation_manifest.json`](reports/stage2_amd_validation_manifest.json): hash-linked correctness evidence and eligibility scope
- [`reports/stage3_calibration_manifest.json`](reports/stage3_calibration_manifest.json): deterministic five-input CPU/GPU correctness gate
- [`configs/stage3_pilot.yaml`](configs/stage3_pilot.yaml): bounded manifest-linked pilot protocol
- [`results/processed/stage3_pilot.json`](results/processed/stage3_pilot.json): deterministic pilot aggregation with inclusion/exclusion reasons
- [`results/processed/stage3_pilot.csv`](results/processed/stage3_pilot.csv): companion row-level pilot table
- [`results/processed/stage3_candidate_pilot.json`](results/processed/stage3_candidate_pilot.json): combined CPU-thread/CPU16/GPU pruning evidence
- [`reports/stage4_protocol.json`](reports/stage4_protocol.json): frozen final shard hashes, counts, and analysis rules
- [`reports/stage4_completion.json`](reports/stage4_completion.json): completed-campaign integrity and correctness audit
- [`reports/phase_b_input_inventory.json`](reports/phase_b_input_inventory.json): exact licensed N₂/H₂O data inventory and hashes
- [`reports/PHASE_B_COMPATIBILITY.md`](reports/PHASE_B_COMPATIBILITY.md): unchanged-input static and smallest-pair runtime gate
- [`reports/phaseb_n2_h2o_correctness_manifest.json`](reports/phaseb_n2_h2o_correctness_manifest.json): exact four-record N₂/H₂O CPU/GPU correctness manifest
- [`data/derived/phase_b_prefixes/manifest.json`](data/derived/phase_b_prefixes/manifest.json): ten deterministic N₂/H₂O prefix workloads and source/solver boundary
- [`reports/stage4_fe4s4_family_registry.json`](reports/stage4_fe4s4_family_registry.json): external family metadata for all 48 immutable Stage 4 records
- [`configs/phaseb_n2_h2o_grid_correctness.yaml`](configs/phaseb_n2_h2o_grid_correctness.yaml): completed all-v3 ten-workload correctness protocol
- [`reports/phaseb_n2_h2o_grid_correctness_manifest.json`](reports/phaseb_n2_h2o_grid_correctness_manifest.json): deterministic 20-record, ten-input schema-v3 correctness gate
- [`configs/phaseb_n2_h2o_grid_pilot.yaml`](configs/phaseb_n2_h2o_grid_pilot.yaml): frozen one-warmup/one-measured Phase B pilot protocol
- [`results/processed/phaseb_n2_h2o_grid_pilot.json`](results/processed/phaseb_n2_h2o_grid_pilot.json): deterministic family-aware pilot aggregation
- [`results/processed/phaseb_n2_h2o_grid_pilot.csv`](results/processed/phaseb_n2_h2o_grid_pilot.csv): companion row-level pilot table
- [`reports/PHASE_B_PILOT_AUDIT.md`](reports/PHASE_B_PILOT_AUDIT.md): pilot integrity, diagnostic crossover, resource, cost, and claim-boundary audit
- [`reports/phaseb_final_protocol.json`](reports/phaseb_final_protocol.json): frozen 104-record final shards, hashes, estimates, safety controls, and approval gate
- [`results/processed/stage4_final.json`](results/processed/stage4_final.json): deterministic repeated-timing aggregation
- [`configs/stage5_size_heldout.yaml`](configs/stage5_size_heldout.yaml): leakage-safe single-family evaluation protocol
- [`results/processed/stage5/evaluation.json`](results/processed/stage5/evaluation.json): corrected held-out predictions, metrics, models, and claim boundary
- [`results/processed/stage5/policy_summary.json`](results/processed/stage5/policy_summary.json): six-policy primary and sensitivity summary
- [`results/processed/stage5/inference_overhead.json`](results/processed/stage5/inference_overhead.json): hot and diagnostic cold selector-overhead summary
- [`reports/STAGE5_PRELIMINARY_AUDIT.md`](reports/STAGE5_PRELIMINARY_AUDIT.md): internal Phase A provenance, defect, result, and limitation audit
- `results/raw/*.json`: immutable per-attempt records; failures and skips are retained
- `results/raw/inference_overhead/*.json`: immutable per-iteration selector-overhead samples

Internal reports and reproducibility artifacts are generated by the engineering workflow. The student's abstract, submission summary, poster, and other submission prose remain exclusively student-authored.
