# Decision log

## D-001 — Student-authored submission material is excluded

- Date: 2026-07-31
- Status: accepted; user-directed
- Decision: Codex will not draft, rewrite, or generate the abstract, 800-word summary, poster, poster source/copy, or other student-submission material. Codex may implement code, produce internal engineering/scientific reports and traceable figures/tables, organize evidence, and create checklists.
- Rationale: The user explicitly reserved student submissions for their own authorship and responsibility. This overrides Stage 7 poster/summary generation in the handoff.

## D-002 — Stage 0 remains non-invasive

- Date: 2026-07-31
- Status: accepted
- Decision: Perform only read-only inspection and local durable-document creation, then stop before package installation, cloning, compilation, or benchmarking.
- Rationale: This is the handoff's explicit first-response gate and lets the user review cost/toolchain implications.

## D-003 — Preserve the two-upstream pivot strategy

- Date: 2026-07-31
- Status: superseded by D-012; retained as historical record
- Decision: Inspect AMD-HPC/amd-sbd first and reproduce its CPU target; attempt its NVIDIA GPU path for no more than 60 minutes of focused build work. If blocked, pivot to `r-ccs-cms/sbd` pinned to `v1.3.0` for a CUDA/Thrust path.
- Rationale: AMD aligns most directly with the runtime-parameter motivation, while the RIKEN implementation is the practical match for installed nvcc 12.9.

## D-004 — Do not install NVIDIA HPC SDK during initial setup

- Date: 2026-07-31
- Status: satisfied for initial setup; later SDK installation authorized under D-012
- Decision: Install only the standard missing build/MPI/BLAS/Python packages after approval. Do not install NVIDIA HPC SDK without a separate evidence-backed request and explicit approval.
- Rationale: `nvc++` is absent, the SDK is multi-gigabyte, credits and disk/time are limited, and a CUDA fallback exists.

## D-005 — Begin with a rigorous CPU-versus-GPU selector

- Date: 2026-07-31
- Status: accepted as minimum scope
- Decision: The required initial candidate layer is CPU thread count versus the upstream-default GPU backend. Cache, bit-length, shuffle, decomposition, MPI, or other axes are added only after a complete correct pipeline exists and the chosen implementation exposes them reliably.
- Rationale: A narrow, held-out, reproducible result is more defensible by the deadline than a fragile high-dimensional tuner.

## D-006 — Performance evidence is invalid until correctness passes

- Date: 2026-07-31
- Status: accepted
- Decision: Establish identical-input CPU/GPU convergence and numerical agreement before collecting usable timing evidence. Preserve timeouts, OOMs, invalid candidates, and failures as immutable records.
- Rationale: It prevents fast failures or incomparable execution paths from becoming performance claims.

## D-007 — Treat the existing CUDA/cuDNN APT source as out of scope

- Date: 2026-07-31
- Status: accepted
- Decision: Refresh APT metadata after approval, simulate the standard dependency installation, and stop if it proposes unexpected CUDA/cuDNN changes. Do not edit the enabled Ubuntu-24.04-named local cuDNN source on this Ubuntu 22.04 host as part of AutoSBD setup.
- Rationale: The source mismatch predates this project and changing the GPU software stack is unnecessary, risky, and outside the authorized setup scope.

## D-008 — Install only the standard build stack and bootstrap the local venv

- Date: 2026-07-31
- Status: implemented
- Decision: Install the simulated C++/MPI/BLAS/LAPACK/CMake/Python transaction, then create `.venv` with only pip/setuptools/wheel/packaging. Defer scientific Python packages until the project package definition is implemented.
- Rationale: The simulated transaction was small (108 MB download, 451 MB installed), contained no removals or CUDA/cuDNN changes, and provides everything required to inspect and attempt the upstream CPU/CUDA paths without prematurely expanding dependencies.

## D-009 — Pivot the required GPU path from AMD artifacts to RIKEN v1.3.0

- Date: 2026-07-31
- Status: superseded by D-012; retained as historical record
- Decision: Retain AMD `sc26-artifacts` as a pinned paper-aligned source and working CPU baseline, but use RIKEN tag `v1.3.0` for identical-source CPU/Thrust-GPU validation and measurements.
- Rationale: AMD CPU compiled successfully, but its artifact GPU build is ROCm/`gfx90a`-specific. NVIDIA requires unavailable Clang NVPTX OpenMP offload or NVIDIA HPC SDK plus GPU-aware MPI. The artifact Docker image is also ROCm-only. The RIKEN source exposes a CUDA/Thrust backend compatible with the installed nvcc after a narrow build shim, so continuing AMD GPU work would violate the time-focused pivot rule.

## D-010 — Use a forced-include nvcc popcount compatibility shim

- Date: 2026-07-31
- Status: implemented provisionally; correctness validation required
- Decision: Compile unmodified RIKEN `v1.3.0` with CUDA 12.9 nvcc for `sm_89`, forcing in `include/autosbd/nvcc_compat.h` to remap four `__host__ __device__` calls from device-only `__popcll` to `__builtin_popcountll`.
- Rationale: The unmodified direct nvcc compile failed only at those four calls. The shim preserves popcount semantics, emits real L4 cubins, and avoids a multi-gigabyte toolchain. Remaining upstream cross-execution warnings mean no GPU timing is valid until identical-input convergence, energy, and density checks pass.

## D-011 — Do not use the RIKEN v1.3.0 rounded N₂ table as the primary oracle

- Date: 2026-07-31
- Status: accepted
- Decision: Use identical-input CPU/GPU numerical agreement as the primary correctness criterion. Record the RIKEN table value only as secondary provenance and flag its discrepancy.
- Rationale: The converged CPU energy is `-109.0416210980518 Ha`; the RIKEN table says `-109.041511 Ha`, while newer AMD-synchronized documentation says `-109.04162110 Ha` for the same hashed input and matches the run. Hiding or forcing agreement with the stale rounded table would be scientifically unsound.

## D-012 — Restore AMD-HPC as the primary implementation

- Date: 2026-07-31
- Status: accepted; user-directed; supersedes D-003 and D-009 for current implementation selection
- Decision: Use official AMD-HPC `sc26-artifacts` commit `729cfa3a5011fb805eb9e686a7711f6919836dcb` as the primary CPU/GPU benchmark and runtime-selector implementation. Install NVIDIA HPC SDK 26.5 and build both backends from that same unmodified AMD source. Keep RIKEN `v1.3.0` pinned only to preserve prior build, compatibility-probe, and CPU-smoke evidence and for explicitly secondary diagnostics.
- Rationale: The OpenMP paper and handoff identify `AMD-HPC/amd-sbd` as the main implementation for the runtime-parameter problem, and the user explicitly corrected the implementation priority. Historical RIKEN and failed AMD attempts remain valid provenance but do not determine the current scientific target.

## D-013 — Accept the same-source AMD Stage 1 correctness result

- Date: 2026-07-31
- Status: accepted
- Decision: Require both final residual norms to be at most `1e-8`, CPU/GPU relative energy error to be at most `1e-10`, and maximum absolute density difference to be at most `1e-10`. Parse convergence from the residual rather than treating exit 0 as sufficient. Use the explicit-environment mandatory-offload GPU rerun as the accepted GPU record. The official AMD Fe₄S₄ CPU/GPU pair passes all criteria and becomes the Stage 1 baseline; its single-run timings remain excluded from final benchmark claims.
- Rationale: The nonconverged four-restart CPU attempt exited 0, demonstrating why application status alone is insufficient. Upstream documents the printed `tol=` as the residual norm and provides only an approximate, non-asserted Fe₄S₄ energy. The OpenMP paper reports CPU/GPU agreement within `1e-10` relative error without defining a precise output formula. Requiring convergence plus independently recomputed energy and density agreement is strict, explicit, and reproducible.
