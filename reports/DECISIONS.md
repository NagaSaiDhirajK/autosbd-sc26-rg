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

## D-023 — Accept the five-size correctness manifest and admit a bounded pilot

- Date: 2026-08-01
- Status: accepted
- Decision: Accept `reports/stage3_calibration_manifest.json` schema 2, SHA-256 `6fcc273d84f65d20185c0abcba9b750a29c2d64a87c982e500a4be5cdd93bdec`, as the correctness gate for sizes 32, 55, 100, 174, and 244. Configure the pilot with all five sizes, both official AMD CPU/GPU backends, one warmup and one measured repetition per candidate, sequential execution, and randomized trial order. Admit timing evidence only from measured records that remain clean and pass the exact validation manifest and all existing eligibility gates.
- Rationale: The definitive calibration produced 10/10 clean correctness records at project commit `7bdb03d`; all five CPU/GPU pairs met the residual, energy, density, and exact-iteration agreement criteria, and an immediate resume launched 0 trials while reusing all 10 records. Correctness-run wall values remain diagnostic-only and do not establish speedup or crossover.
- Upstream boundary: The active implementation remains the official pinned `AMD-HPC/amd-sbd` source, with CPU and NVIDIA OpenMP-offload GPU builds from the single NVIDIA HPC SDK 26.5 toolchain. Do not execute RIKEN for calibration, pilot, final measurement, training, or selection.

## D-024 — Meet the Stage 3 exit criterion, close the CPU thread gap, then freeze Stage 4

- Date: 2026-08-01
- Status: accepted
- Decision: Accept the clean five-size pilot as satisfying the Stage 3 exit criterion. Run the missing official AMD CPU candidates with 1, 4, and 8 threads at determinant-prefix sizes 32, 55, and 100. Prune an alternate CPU thread candidate unless it either beats CPU16 by at least 10% or changes the CPU/GPU winner for a workload. After this bounded thread pilot, freeze the Stage 4 configurations and do not reopen the candidate axis without new evidence.
- Rationale: The pilot completed 20/20 successful records and exact resume reused all 20. Its single measured repetition per candidate places the observed CPU16/GPU wall-time crossover between 1,024 and 3,025 configurations, but provides neither uncertainty nor a final speedup estimate. Testing only the missing CPU thread counts at the three smallest sizes closes the minimum selector axis from D-005 without expanding into an unfocused sweep.
- Evidence boundary: The ratios `0.867971`, `1.248678`, `1.987723`, `3.400104`, and `4.548233` are internal single-repetition pilot observations. The workloads are nested sizes from one Fe₄S₄ family, and final claims require the frozen Stage 4 protocol and repeated held-out measurements.
- Upstream boundary: Continue with the official pinned `AMD-HPC/amd-sbd` CPU/GPU artifacts built through the single NVIDIA HPC SDK toolchain. Do not execute or promote RIKEN.

## D-025 — Prune alternate CPU threads and freeze the three-shard Stage 4 protocol

- Date: 2026-08-01
- Status: accepted
- Decision: Prune CPU1, CPU4, and CPU8; retain only CPU16 and the GPU candidate. Freeze Stage 4 into three named shards: `cross` covers determinant-prefix sizes 32 and 55 with five measured repetitions per candidate; `mid` covers sizes 100 and 174 with three measured repetitions; `large` covers size 244 with three measured repetitions. Each shard uses one warmup, protocol purpose `final`, sequential execution, and the existing default seeded backend-order randomization within workload/phase blocks. Do not reopen the candidate axis without new evidence.
- Rationale: CPU16 was the fastest CPU at all three thread-pilot sizes. CPU1/CPU16 wall ratios were `3.418619`, `7.687172`, and `11.923566`; CPU4 ratios were `1.569013`, `2.286679`, and `3.173900`; CPU8 ratios were `1.142218`, `1.372931`, and `1.694620`. No alternate was at least 10% faster than CPU16, and no alternate changed the candidate-set CPU/GPU oracle at a tested workload, so every alternate meets D-024's pruning condition.
- Configuration state: Stage 4 configuration creation is in progress. This decision fixes shard names, workloads, repetitions, warmup count, purpose, candidates, sequencing, and randomization policy, but asserts no unfinished file or configuration hash.
- Evidence boundary: The thread pilot used one measured repetition per candidate and separate baseline/thread batches; all workloads are nested sizes from one Fe₄S₄ family. Stage 4 repeated measurements remain necessary, and this decision is not a final performance claim.
- Upstream boundary: Continue exclusively with the official pinned `AMD-HPC/amd-sbd` CPU/GPU artifacts built through NVIDIA HPC SDK 26.5. Do not execute, train on, select, or promote RIKEN.

## D-026 — Use explicit static-threshold sentinels and geometric boundaries

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: Fit on training instances only with candidates in exact registered order: `always_gpu`, geometric midpoints between adjacent unique training configuration counts, then `always_cpu`. Represent sentinel thresholds as JSON `null`, dispatch them by explicit `kind`, and retain the first registered candidate on an objective tie.
- Rationale: observed-size integers are not true between-size boundaries and are ambiguous stand-ins for unconditional policies. Explicit kinds are deterministic, JSON-safe, and testable on unseen sizes.

## D-027 — Treat upstream default as provenance, not a seventh baseline

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: Keep `upstream_default: fixed_gpu` in provenance metadata, but exclude the alias from predictions, metrics, summaries, and plots. Report six unique policies: fixed CPU16, fixed GPU, static threshold, size-only tree, full AutoSBD tree, and measured feasible oracle.
- Rationale: upstream default and fixed GPU are identical here. Counting the alias independently duplicates evidence.

## D-028 — Measure hot selection and object-cold load-plus-selection overhead

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: Time the exported full-tree path with `perf_counter_ns`. Hot timing includes feasibility filtering, feature-vector construction, prediction, and argmin for at least 10,000 iterations after warmup. Cold timing additionally reads/parses `models.json` and looks up the model for at least 100 iterations. Consume every selection, preserve immutable raw samples, emit processed JSON/CSV summaries, and compare hot median with the shortest measured SBD median.
- Rationale: this covers the deployed selection path without conflating it with FCIDUMP parsing or solver runtime. OS page-cache state remains uncontrolled and is stated explicitly.
- Evidence: immutable raw SHA `ea293deabbd2c904e1b432a88075c750db9ef7eb595d58d8a45fc452e1c4d356`; hot median `38.65 us`, equal to `0.002739337080263366%` of the shortest measured SBD median; load-plus-selection median `929.11 us`.

## D-029 — Permit RIKEN-origin inputs only as data for the official AMD path

- Date: 2026-08-01
- Status: accepted policy; Phase B execution remains approval-gated
- Decision: The active CPU/GPU solver remains the same exact official `AMD-HPC/amd-sbd` commit and NVIDIA HPC SDK toolchain. A pinned RIKEN repository may supply authentic N2/H2O input files only after license, provenance, format-compatibility, and identical-input correctness gates. Do not build, execute, time, train on, or promote the RIKEN solver. Stop if the data format is incompatible rather than adapting the scientific input silently.
- Rationale: this follows the completion handoff's multifamily data plan without violating the user-directed official upstream implementation path or creating a cross-solver comparison.

## D-030 — Accept the static Phase B input gate; keep runtime correctness pending

- Date: 2026-08-01
- Status: accepted and implemented; user approved the bounded B1 correctness batch
- Decision: Admit the exact pinned N₂/6-31G and H₂O/cc-pVDZ bytes to staged correctness-only execution through the existing official AMD CPU16 and NVIDIA OpenMP-offload GPU binaries. Bind the data to `reports/phase_b_input_inventory.json` and require `scripts/validate_phase_b_inputs.py` to pass immediately before execution. Treat `r-ccs-cms/sbd` tag `v1.3.0` commit `b71e1c3ed857fcb4fb05731dc285831c1afe9ebd` strictly as the licensed data source; do not build, execute, time, train on, select, or promote its solver. Keep static compatibility and runtime correctness as separate states: no N₂/H₂O timing is admissible until an exact-hash CPU/GPU correctness manifest passes.
- Correctness rule: run the smallest N₂ CPU record first, then its GPU pair, then repeat that staged order for H₂O. Stop the affected family on unchanged-input incompatibility or any process, convergence, residual, iteration, energy, density, input-integrity, project-cleanliness, idleness, memory-admission, offload, device-assignment, or monitoring failure. Preserve every terminal raw record; do not repeat an unchanged failure more than once.
- Rationale: exhaustive static checks establish that the official AMD parser can consume all retained files unchanged, but cannot prove numerical convergence or CPU/GPU parity. A deterministic inventory plus staged runtime gate adds two authentic chemistry families without crossing solver implementations, altering scientific inputs, or misusing correctness-run wall values as performance evidence.

## D-031 — Accept exact smallest N₂/H₂O correctness; admit no timing yet

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: Accept `reports/phaseb_n2_h2o_correctness_manifest.json`, schema 2, SHA-256 `fc73db40f756384e86852e8a7a12ec00fe8838db25683681aa12eceb9bdf38c5`, as the correctness gate only for combined input hashes `6976b0d5793326781b16b53b6ff8d7c76068bdd016bdd29aa4cbee3e6aab0deb` (N₂) and `ee17c38802ca7e869797f014dbc4957e7b589cc2cb8e2f2068c37fc2af1a150d` (H₂O). Preserve all four immutable records. Do not infer correctness for any larger list or derived prefix, and do not admit any recorded duration as performance evidence.
- Evidence: both CPU/GPU pairs used the same exact official AMD commit, solver settings, and family-specific input bytes; all four records converged with residual at most `1e-8`; per-family iteration counts match exactly; energy relative errors are `0` and `5.5922e-16`; density lengths equal `NORB`; density maximum differences are `3.1974e-14` and `1.9984e-14`; inputs and run artifacts verify; and both GPU records contain mandatory offload, exact device assignment, positive allocation, process observation, and complete monitoring.
- Rationale: Phase B1 demonstrates that the official AMD path can consume and solve authentic smallest N₂/H₂O cases unchanged, closing the runtime compatibility gate while preserving a single implementation. Zero warmups and one correctness repetition provide no timing distribution or cross-family selector evidence. Phase B2 may prepare deterministic derived sizes and family metadata, but each exact hash needs a new correctness gate before a separately approved timing protocol.

## D-032 — Version family identity without rewriting historical evidence

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: Preserve config schema 1 as the default and preserve raw-record schemas 1/2 exactly. Introduce config schema 2 for future chemistry-aware workloads, requiring `family_id`, `molecule`, and `basis`; emit raw-record schema 3 and bind the same metadata into both the top level and logical identity. Keep `problem_family=sweep_name` and `problem_instance=workload.name`; use `family_id` as the scientific grouping key. Never retrofit any of the 120 historical raw records. Add Fe₄S₄ metadata through a deterministic external registry that verifies exact immutable record bytes, IDs, component hashes, instance, and combined input SHA.
- Rationale: existing `problem_family` values identify sweep configurations, not chemistry. Conditional additions to raw schema 2 would weaken its closed identity contract and could permit conflicting labels under one trial ID. A version boundary preserves all existing attestations while making future family metadata identity-bearing and collision-safe.
- Leakage boundary: family, molecule, basis, paths, hashes, identifiers, and post-execution outcomes remain grouping/provenance fields only and must never enter selector predictors.

## D-033 — Prepare two deterministic family-local grids as inputs only

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: For each authentic N₂ and H₂O family, derive byte-exact nested determinant prefixes at half-list counts 32, 55, 100, and 174, plus the full official smallest count (239 N₂; 275 H₂O). Bind every output to the exact parent determinant, FCIDUMP, family metadata, electronic structure, license/source, official input repository commit, and the official-AMD-only active solver boundary in `data/derived/phase_b_prefixes/manifest.json`, SHA-256 `852c6c99b279610b413e29472e4839fc178fc63e094b01275f4bf3aaae57d373`.
- Rationale: the controlled grid matches the handoff and provides comparable configuration-count scales across three families. Prefixes are size variants within a family, not independent chemical solutions or extra independent families.
- Evidence boundary: generation proves provenance and byte determinism only. Each exact combined input hash needs CPU/GPU correctness before timing; correctness-run durations remain ineligible; no cross-family performance or selector claim follows from this preparation.

## D-034 — Augment frozen Fe₄S₄ evidence externally with an explicitly unknown basis

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: Preserve all 48 Stage 4 raw records and their IDs/bytes. Generate `reports/stage4_fe4s4_family_registry.json` only after verifying the exact completion attestation, exact aggregate, every raw path/SHA/size, schema-v2 identity, input-integrity snapshots, component bytes, and aggregate/raw features. Bind exact `(problem_instance,input_sha256)` mappings to `family_id=fe4s4`, `molecule=Fe4S4`, `basis=null`, and `basis_status=upstream_not_reported`; reject unknown, ambiguous, inconsistent, duplicate, or extra fields.
- Evidence: registry ID `86bb6e3954b0b6dc86ae831c6b754eb25d77f63a3e548e7c4bd88fb10858e631`; file SHA-256 `cfeb5f60e29d01068c68b9d348739fba4b4e204e5165edce899aff5dfa94395d`; five workload entries; 48 mapped raw records; unchanged raw-chain digest `3bc6e00863305e08720aeb0949f1b0ceb80d2715af213cae5f7375629b66a91c`.
- Rationale: the verified upstream/local evidence names the Fe₄S₄ sample but does not report a basis set. External augmentation preserves immutable provenance and prevents both a fabricated basis and misuse of the historical sweep-name `problem_family` as chemistry identity.

## D-035 — Use a homogeneous raw-v3 correctness gate for all ten Phase B grid inputs

- Date: 2026-08-01
- Status: accepted and implemented
- Decision: Retain the four B1 schema-v2 full-size correctness records and manifest unchanged as historical compatibility evidence, but do not mix them into the new family-aware gate. Run one correctness-only CPU/GPU pair for each of the ten N₂/H₂O grid workloads under config schema 2/raw schema 3, including bounded full-size repeats, and build one all-v3 manifest. Only after that manifest passes and regenerates unchanged may a one-warmup/one-measured pilot run.
- Rationale: the calibration builder intentionally rejects mixed v2/v3 evidence. A bridge would omit identity-bound family metadata for the two full cases, while the four bounded full-size v3 repeats add only about 33 conservative seconds and create a simple fail-closed contract across every exact pilot input.
- Frozen protocol: `configs/phaseb_n2_h2o_grid_correctness.yaml`, SHA-256 `d9ff3d497a0ba561016b5c22b12a29ad3db808b0fe3c2f68beef37ebb14fe99a`; exact deterministic input manifest SHA-256 `852c6c99b279610b413e29472e4839fc178fc63e094b01275f4bf3aaae57d373`.
- Approval boundary: correctness plus pilot are conservatively estimated at 4.64 minutes and about `USD 0.134`, below repository gates. After the pilot, replace projections with measured family-specific runtime/cost and stop for explicit approval before any broad three-/five-repetition final timing.

## D-036 — Accept the exact schema-v3 grid gate and permit only the bounded pilot

- Date: 2026-08-01
- Status: accepted; correctness complete and pilot config frozen
- Decision: Accept `reports/phaseb_n2_h2o_grid_correctness_manifest.json`, schema 3, SHA-256 `ba6bf82b63c9a8bdf2a5a513df914a9f1446605a0d4939cb53f7921527222829`, as the correctness gate for exactly the ten N₂/H₂O combined input hashes it names. Preserve all 20 immutable source records. Permit the manifest-linked config `configs/phaseb_n2_h2o_grid_pilot.yaml`, SHA-256 `3519b8fd4e45d9a412dd85a1fae9c586ddf865c078ae4cbfeaa43ee1a5091d70`, with one excluded warmup and one measured repetition per candidate/input, sequential execution, and deterministic randomized candidate order.
- Evidence: all 20 runs used clean project commit `477a132911bed1756d42e298ea3af69d7a10a9bb`, the exact official AMD commit and CPU/GPU artifacts, stable inputs, complete monitoring, and required GPU offload/device evidence. All ten CPU/GPU pairs passed exact iteration parity, residual `<=1e-8`, energy relative tolerance `1e-10`, density tolerance `1e-10`, and density-length checks. The manifest rebuilt byte-identically.
- Raw-state interpretation: `correct=null` and a non-required prior validation manifest are expected on the zero-reference correctness source records; the post-pair manifest is the authoritative correctness attestation. These records remain `timing_eligible=false` and none enters performance analysis.
- Claim/approval boundary: this gate supports only exact-input CPU/GPU correctness and admission to the bounded pilot. It does not complete Phase B, establish N₂/H₂O speedup/crossover, provide variance, or support leave-one-family-out selector claims. After the pilot, calculate measured repeated-campaign runtime/cost and stop for explicit approval before broad three-/five-repetition timing.

## D-037 — Accept the pilot for planning and freeze a 104-record final protocol

- Date: 2026-08-01
- Status: pilot accepted; final execution awaiting explicit approval
- Decision: Accept the 40-record schema-v3 pilot only as integrity-checked planning and crossover-bracketing evidence. Preserve its 20 excluded warmups and 20 eligible single-repetition measurements, deterministic aggregate JSON/CSV, and raw evidence chain. Do not use the pilot as final repeated timing, variance, or selector-evaluation evidence.
- Observed planning result: CPU16 wins at 1,024 and 3,025 configurations in both N₂ and H₂O; L4 wins at 10,000, 30,276, and the full family sizes. This preregisters 55/100 half-determinants as crossover-adjacent and both full inputs as headline cases; it does not interpolate an unmeasured crossover.
- Frozen final protocol: `reports/phaseb_final_protocol.json` defines three same-campaign shards with one warmup per candidate/workload, five measured repetitions at the four crossover-adjacent and two full headline workloads, and three at the remaining four workloads: 104 total records, 20 warmups, and 84 measurements. All shards retain the exact official AMD commit/binaries, correctness manifest, solver settings, seeded candidate randomization, sequential node lock, 300-second timeout, memory/idleness checks, immutable resume, and stop-on-first-non-success behavior.
- Estimate and gate: the measured pilot projects 7.55063 minutes and approximately USD 0.21826; a 25% buffer projects 9.43829 minutes and USD 0.27283 at the repository-recorded list rate. This replaces the pre-pilot estimate. Do not launch any final shard until the user grants fresh explicit approval.
