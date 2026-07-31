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
- Status: accepted provisionally; validate from source in Stage 1
- Decision: Inspect AMD-HPC/amd-sbd first and reproduce its CPU target; attempt its NVIDIA GPU path for no more than 60 minutes of focused build work. If blocked, pivot to `r-ccs-cms/sbd` pinned to `v1.3.0` for a CUDA/Thrust path.
- Rationale: AMD aligns most directly with the runtime-parameter motivation, while the RIKEN implementation is the practical match for installed nvcc 12.9.

## D-004 — Do not install NVIDIA HPC SDK during initial setup

- Date: 2026-07-31
- Status: accepted
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
