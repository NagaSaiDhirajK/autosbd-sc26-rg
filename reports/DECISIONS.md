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

## D-014 — Enforce the official AMD source, artifacts, and CLI surface in the runner

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: Admit real candidates only when their upstream is official `https://github.com/AMD-HPC/amd-sbd` at commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`, the submodule is clean, the executable hash and build flags match the audited NVIDIA HPC SDK 26.5 artifacts, and the direct compiler identity is `nvc++ 26.5`. Emit only the audited AMD options, including `--carryover_ratio`; never emit unsupported `--init` or `--bdetfile`.
- Rationale: The pinned application silently ignores some unknown arguments, so provenance text and a plausible command are insufficient. Enforcing the URL, commit, source cleanliness, binary SHA-256, compiler, build flags, and exact command surface prevents accidental RIKEN promotion, stale binaries, and no-op parameter claims. RIKEN remains archival evidence only; it is not an active fallback.

## D-015 — Use content-bound schema-v2 logical and attempt identities

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: New records use schema v2. A logical trial ID is the canonical SHA-256 of the complete logical identity; a physical trial ID is the canonical SHA-256 of that logical ID plus attempt index. Validation recomputes both hashes. Exact reruns reuse an immutable terminal record, while an explicit retry uses a new attempt index and record path. Continue loading valid schema-v1 records without rewriting them.
- Rationale: A trial ID must bind inputs, candidate, command, environment, compiler/binary provenance, protocol, and harness state closely enough that reuse cannot silently cross experimental conditions. Backward-compatible loading preserves the raw-data immutability rule.

## D-016 — Fail closed on node ownership, GPU idleness, and telemetry

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: Serialize all real trials with a project-wide node lock; reject lock contention without launching the solver. Require a successful GPU compute-process query and an idle L4 before both CPU and GPU candidates so CPU timing cannot overlap another GPU workload. Mark GPU monitoring complete only when queries remain valid and the trial's GPU allocation is actually observed. Keep the memory cap at `min(20 GiB, 80% of current free VRAM)` and preserve skipped/failure records and orphan artifacts without overwrite.
- Rationale: Missing telemetry is not evidence of an idle device, and a CPU candidate can still be distorted by node-level GPU activity or concurrent benchmark work. Fail-closed admission and exclusive execution protect comparability and make monitoring claims testable.

## D-017 — Bind timing eligibility to every scientific gate

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: Derive `timing_eligible` in the runner; never accept it as a caller assertion. Eligibility requires terminal success, numerical correctness, a measured (not warmup) trial, protocol purpose `pilot` or `final`, at least one configured warmup, a valid hash-linked correctness manifest, a clean project worktree, complete resource monitoring, and unchanged inputs before and after execution.
- Rationale: Correct output alone does not make a development smoke run valid performance evidence. The manifest and protocol gates connect timing to exact validated binaries/inputs, while clean-tree, warmup, monitoring, and integrity gates prevent accidental use of provisional measurements.

## D-018 — Preserve schema-v1 evidence but exclude its eligibility flag

- Date: 2026-08-01
- Status: accepted
- Decision: Keep schema-v1 records `3d550a26...96bc1` and `0aa87a7d...ca5` and their artifacts byte-for-byte unchanged. Treat their `timing_eligible=true` values as a superseded harness defect and exclude their wall/solver times from performance analysis. Use them only as historical correctness and harness-integration evidence, cross-linked by the validation manifest.
- Rationale: Editing raw records would violate immutability and erase evidence of the discovered defect. Explicit supersession preserves both scientific transparency and the audit trail.

## D-019 — Hash-link input state and every run artifact

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: Hash semantic input roles initially, immediately before launch, and after completion; fail or disqualify a trial if they change. Record size and SHA-256 for stdout, stderr, and resource telemetry. If any artifact already exists without its matching terminal record, preserve it and write a failure record for that attempt rather than overwriting it.
- Rationale: Path-only feature caches and unlinked log filenames cannot prove what a solver consumed or what evidence belongs to a record. Rehashing and artifact manifests make mutation, stale logs, and interrupted writes visible.

## D-020 — Make the active build path AMD-only

- Date: 2026-08-01
- Status: accepted, user-directed, and implemented
- Decision: Expose only `amd-all`, `amd-cpu`, and `amd-gpu` from `scripts/build_upstream.sh`. Require the official `AMD-HPC/amd-sbd` origin, pinned commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`, and a clean checkout before building either executable with NVIDIA HPC SDK 26.5. Keep the RIKEN submodule, compatibility header, prior logs, and earlier decisions solely as recoverable history; do not build, run, train on, or select RIKEN in the active project.
- Rationale: The paper/handoff's main implementation and the user's explicit correction both require the official AMD path. Removing legacy RIKEN targets from the current entry point eliminates ambiguity while preserving the audit trail. This decision supersedes any interpretation of D-012's secondary-diagnostics clause as authorization for active RIKEN work.

## D-021 — Use audited Fe₄S₄ determinant prefixes only as size variants

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: Derive determinant-count variants `32`, `55`, `100`, `174`, and `244` as byte-exact nested prefixes of the pinned official AMD `AlphaDets.txt`, while keeping the exact official FCIDUMP read-only. Require the generator to verify the live official origin/commit/cleanliness, source hashes and structure, deterministic output hashes, atomic/idempotent writes, and a manifest that states `family_count=1` and `distinct_chemical_families=false`. Calibrate each non-full prefix with identical-input CPU/GPU agreement before it can enter a timing protocol.
- Rationale: The pinned artifact tree contains only one usable authentic chemistry dataset. Prefixes provide controlled size variation for locating a device crossover, but the selected subspace and energy change with prefix length. Calling them independent chemical families or reusing the full-space energy would create false generalization/correctness claims.

## D-022 — Exclude generated raw records from source-dirty identity only

- Date: 2026-08-01
- Status: accepted and implemented after calibration exposed a resume defect
- Decision: When computing the project source-tree dirty flag, ignore only untracked, real, regular lowercase `.json` files beneath `results/raw/`. Keep every tracked modification/deletion, symlink, other suffix/location, and all upstream checkout changes dirty. Do not add raw records to `.gitignore`; they remain visible and intentionally committed. Preserve the eight duplicate dirty-identity calibration records created before this fix and exclude them from calibration/timing evidence.
- Rationale: A clean calibration creates its own immutable untracked outputs. Treating those outputs as a source change caused a new runner process to derive different logical identities and relaunch all eight trials instead of resuming. The narrow exception restores exact resume without hiding code/config/data changes or any modification to an already tracked record.
