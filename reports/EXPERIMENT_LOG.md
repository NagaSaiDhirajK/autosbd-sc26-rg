# Experiment log

## 2026-07-31 — Stage 0 status

- Purpose: Record whether any scientific/performance experiment occurred during the environment audit.
- Configuration identifier: not applicable
- Result paths: `reports/ENVIRONMENT.md`
- Outcome: No SBD executable was cloned, compiled, or run. No CPU/GPU timing, correctness, profiling, or tuner experiment exists yet.
- Anomalies: none; missing dependencies are setup findings, not experimental results.
- Decision: Do not make performance or correctness claims until Stage 1 reproduces identical-input CPU/GPU outputs.

## 2026-07-31 — RIKEN CPU N₂ `1em3` correctness smoke

- Purpose: Verify that the pinned RIKEN CPU application parses an authentic bundled input, converges under an explicit residual tolerance, and establishes a comparison value for the GPU backend.
- Configuration identifier: `stage1-riken-cpu-n2-1em3-r1-t1-bit20`
- Input: N₂/6-31g; 239 alpha and 239 beta half-determinants; 57,121 product states; FCIDUMP SHA-256 `dee67eb5...efcf33`; determinant SHA-256 `73a28f6e...18dd2`.
- Candidate: one MPI rank, one OpenMP thread, one OpenBLAS thread, matrix-free Davidson, block 10, up to four restarts, tolerance `1e-8`, shuffle off, `bit_length=20`.
- Result paths: `logs/stage1_riken_cpu_n2_1em3.stdout.log`, `logs/stage1_riken_cpu_n2_1em3.stderr.log`, `logs/stage1_riken_cpu_n2_1em3.time.log`.
- Outcome: exit 0; final residual `9.745846817253461e-09`; energy `-109.0416210980518 Ha`; wall 40.90 s; peak RSS 37,472 KiB; no GPU allocation.
- Anomaly: RIKEN `v1.3.0` README lists `-109.041511 Ha`; later AMD-synchronized documentation lists `-109.04162110 Ha`, agreeing with the run.
- Decision: Accept as the CPU comparison run. Do not treat it as final timing data because it predates the immutable benchmark harness.
- Supersession: Retained as historical RIKEN feasibility evidence only; this is not the primary AMD CPU baseline or primary CPU/GPU validation result.

## 2026-07-31 — AMD Fe₄S₄ preliminary convergence attempts

- Purpose: Bound the official AMD artifact sample and determine settings needed for a strict paired correctness run.
- Input: official Fe₄S₄ artifact; 244 half-determinants per spin and 59,536 product states; hashes recorded in `reports/BUILD_PROVENANCE.md`.
- Attempt 1: AMD CPU, one thread, four-restart allowance. It reached residual `0.03715544425092371` after four Davidson steps in about 101 s and was intentionally terminated with exit 143 because projected completion exceeded the five-minute pilot budget. Logs: `logs/stage1_amd_cpu_fe4s4.*`.
- Attempt 2: AMD CPU, 16 physical threads, four-restart allowance. It exited 0 in 62.77 s but exhausted the allowance at residual `1.7589424916975e-7`, above the requested `1e-8`; energy was `-326.698253673155 Ha`. Logs: `logs/stage1_amd_cpu_fe4s4_t16.*`.
- Decision: Preserve both as non-passing attempts. Increase the restart allowance to six without changing the residual threshold or other solver options.

## 2026-07-31 — Primary AMD CPU/GPU Fe₄S₄ correctness

- Purpose: Validate the official AMD-HPC CPU and NVIDIA OpenMP-offload GPU backends from the same exact source on identical authentic input.
- Configuration identifier: `stage1-amd-fe4s4-r1-method0-block10-i6-tol1e-8-bit20`.
- Candidate settings: one MPI process; CPU uses 16 bound OpenMP threads; GPU uses one host thread and the single L4; method 0; block 10; six-restart allowance; tolerance `1e-8`; shuffle off; `bit_length=20`; RDM off.
- Safety: preflight confirmed an idle L4 with 22,564 MiB free; the conservative 512 MiB estimate was below the 18,051 MiB cap. Across 75 canonical samples, GPU use peaked at 206 MiB, 100% utilization, 41 °C, and 42.23 W.
- CPU outcome: exit 0; residual `8.931146441578446e-09`; energy `-326.6982536731583 Ha`; wall 78.15 s; peak RSS 47,080 KiB.
- GPU outcome: exit 0; residual `8.931494922593578e-09`; energy `-326.6982536731581 Ha`; wall 17.22 s; peak RSS 147,536 KiB. Its log explicitly records mandatory target offload and device 0; sampled utilization reached 100%.
- Agreement: energy relative error `6.959745663982201e-16`; density maximum absolute error `2.7017277304253184e-13`; all criteria in `reports/stage1_amd_correctness.json` pass.
- Determinism: the first and canonical-rerun GPU residual/energy/density tuples have identical SHA-256 `327d85fe353535712d82a919dff94380c27d9eefb5a917edd75b097a435edcbf`.
- Result paths: `logs/stage1_amd_cpu_fe4s4_t16_i6.*`, `logs/stage1_amd_gpu_fe4s4_i6_rerun1.*`, and `reports/stage1_amd_correctness.json`.
- Anomaly: the upstream density formatter omits a final `]`; the tracked comparison parser adds only that missing delimiter before parsing and does not alter any value.
- Decision: Stage 1 same-source AMD CPU/GPU correctness passes. Treat observed wall times as smoke evidence, not final benchmark data.

## 2026-07-31 — Stage 2 mock harness and resume smoke

- Purpose: Verify terminal-state classification, bounded process termination, immutable record creation, and exact-trial resume without consuming scientific benchmark resources.
- Configuration identifier: `stage2-mock-smoke`, schema v1 initially and schema v2 after hardening.
- Input: repository-local tiny FCIDUMP/determinant fixture; mock process only, never presented as an authentic SBD performance workload.
- Outcomes: each completed smoke launched five distinct trials and classified one success, two failures (exit-zero nonconvergence and nonzero process exit), one timeout, and one explicit OOM. The immediate rerun launched zero processes and reused all five records by trial ID.
- Test evidence: initial smoke roots `/tmp/autosbd-stage2-smoke.4cDvC2` and `/tmp/autosbd-stage2-smoke.ePZCXD` passed 47 and 48 tests. Hardened smoke root `/tmp/autosbd-stage2-smoke.4XQRJS` passed 62 tests and the same launch/resume assertions. A later full suite passed 67/67 tests; `logs/test_full_v2.log`.
- Decision: The mock fixture is harness validation only. It contributes no CPU/GPU timing, speedup, or solver-correctness evidence.

## 2026-07-31 — First Stage 2 official AMD Fe₄S₄ wrapper pair (schema v1)

- Purpose: Integrate the official same-source AMD CPU/GPU correctness case with immutable records, preflight safety checks, monitoring, parsing, and exact resume.
- Configuration identifier: `stage2-amd-fe4s4`, CPU candidate `amd-cpu-16`, GPU candidate `amd-l4-default`; method 0, block 10, iteration allowance 6, tolerance `1e-8`, carryover ratio 0.5, `bit_length=20`, one MPI rank, zero warmups, one correctness repetition.
- Provenance: official `https://github.com/AMD-HPC/amd-sbd`, `sc26-artifacts` commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`; CPU/GPU binaries built from that same unmodified source with NVIDIA HPC SDK 26.5. CPU SHA-256 `190525bd...0ef07`; GPU SHA-256 `8f1481b6...3bc07`.
- Input: official Fe₄S₄ sample, 36 orbitals, 244 strings per spin, 59,536 product configurations. FCIDUMP SHA-256 `9a74e203...1b6e93`; determinant SHA-256 `b1aa7e60...8f68`.
- Safety: both preflights found the L4 idle with 22,564 MiB free, 34 °C, and about 16.52 W; the cap was `min(20 GiB, 80% of free VRAM)`. Runs were sequential and bounded by 300 s.
- CPU record: `results/raw/3d550a2669c8c2d2b7cdc6f824d08f94c6d424c954160e3aa2fee18f9cd96bc1.json`; exit 0, residual `8.931146441578446e-09`, energy `-326.6982536731583 Ha`, 78.5377 s wall, 75.87626 s solver, 47.640625 MiB peak RSS.
- GPU record: `results/raw/0aa87a7deb05704f0dea7afc3d3ec382214d4d68c7ba4666fd6c7e89a8203ca5.json`; exit 0, residual `8.931494922593578e-09`, energy `-326.6982536731581 Ha`, 17.1397 s wall, 15.494857 s solver, 198 MiB peak GPU memory, 145.042969 MiB peak RSS. Mandatory offload and device 0 were observed.
- Agreement: energy relative error `6.959745663982201e-16`; density maximum absolute error `2.7017277304253184e-13`; both residuals pass `1e-8`.
- Resume: exact reruns reused both records without launching a solver.
- Anomaly: schema v1 marked both records `timing_eligible=true` despite a dirty project tree and zero warmups. Raw records are immutable, so this defect is documented rather than edited.
- Decision: Retain the v1 pair as historical correctness evidence, but exclude both timings from every performance analysis.

## 2026-08-01 — Stage 2 harness hardening audit

- Purpose: Resolve an independent audit of provenance, concurrency, identity, telemetry, input integrity, artifact preservation, and timing eligibility before any pilot or final benchmark.
- Configuration identifier: schema v2 harness hardening.
- Implemented controls: content-bound logical identity plus attempt-bound trial ID; backward-compatible v1 loading; exclusive claims with same-host dead/PID-reuse recovery; project-wide node run lock; official AMD URL/commit/clean-worktree enforcement; exact binary hashes and build flags; direct `nvc++ 26.5` compiler identity; fail-closed GPU process query; preflight GPU-idle requirement for CPU and GPU candidates; GPU monitor completeness only after observing the allocated process; semantic input hashes before launch and after run; immutable orphan-artifact handling; size/SHA-256 links for stdout, stderr, and resource logs; explicit protocol purpose and correctness-validation manifest.
- Intermediate anomaly: the first full integration run after stricter gates had 10 errors among 61 tests because older fixtures assumed eligibility without a validation manifest and constructed now-invalid identities. The failure is retained in `logs/telemetry_harden_full_tests.log`; tests were corrected to express the stricter contract.
- Outcomes: schema/claim 11/11 passed, process/system telemetry 17/17 passed, hardened runner 13/13 passed, and final complete suite 67/67 passed.
- Decision: Schema v2 supersedes schema v1 for all new trials. No existing raw record was modified or removed.

## 2026-08-01 — Hardened Stage 2 official AMD Fe₄S₄ correctness (schema v2)

- Purpose: Re-run the authentic same-input AMD pair through the final hardened wrapper and generate hash-linked correctness evidence before pilot timing.
- Configuration identifier: `stage2-amd-fe4s4`, protocol purpose `correctness`, zero warmups, one repetition; solver/candidates/input identical to the schema-v1 pair.
- CPU record: `results/raw/9f9031146690fe8afd04b94fced38551c7863ea95d62ff35404f022895055d1d.json`; logical trial `1cee69f5...68868`; exit 0, residual `8.931146441578446e-09`, energy `-326.6982536731583 Ha`, 78.727544 s wall, 76.066536 s solver, 47.648438 MiB peak RSS.
- GPU record: `results/raw/1b7be4e302c4b8185d7960e04af7bf42abc4b41c49dfb0d3727a790383de6125.json`; logical trial `e22bc2c0...e490`; exit 0, residual `8.931494922593578e-09`, energy `-326.6982536731581 Ha`, 17.221986 s wall, 15.509004 s solver, 198 MiB peak GPU memory, 145.085938 MiB peak RSS.
- Safety and integrity: both preflights successfully queried an idle L4 with 22,564 MiB free and applied an 18,928,055,091-byte GPU cap. Initial, before-launch, and after-run hashes match. GPU monitoring was complete and observed the trial process; mandatory offload and device 0 were parsed.
- Agreement: all checks in `reports/stage2_amd_correctness.json` pass; energy relative error `6.959745663982201e-16`, density maximum absolute error `2.7017277304253184e-13`, density L2 error `4.126804786123131e-13`.
- Evidence manifest: `reports/stage2_amd_validation_manifest.json` binds exact input hash `cca24426...49e03`, source commit, binary hashes, v1/v2 records, run artifacts, solver settings, and numerical criteria.
- Timing eligibility: both records correctly set `timing_eligible=false` because this was a zero-warmup correctness protocol, `correctness_validated=false`, and the harness worktree was dirty. The observed wall/solver values diagnose execution only and are not final timing data.
- Decision: Correctness gate passes for the exact official AMD CPU/GPU artifacts. A later clean, warmup-enabled, manifest-linked pilot/final protocol is required before performance analysis.

## 2026-08-01 — Stage 3 official AMD Fe₄S₄ workload preparation

- Purpose: Prepare deterministic size variants for later cross-backend calibration without changing the official upstream input or making a performance measurement.
- Configuration identifier: `amd-sbd-fe4s4-derived-determinant-prefixes`, manifest schema 1.
- Source: official `AMD-HPC/amd-sbd` commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`; `AlphaDets.txt` SHA-256 `b1aa7e60...8f68`; read-only Fe₄S₄ FCIDUMP SHA-256 `9a74e203...1b6e93`.
- Outputs: exact nested prefixes with 32, 55, 100, 174, and 244 determinant strings under `data/derived/amd_fe4s4_prefixes/`; manifest SHA-256 `47b62521b5b369f2a7c3af52ae805073451b23b457a8e044ff9fa27a2f6d47e8`.
- Geometry: 1,024; 3,025; 10,000; 30,276; and 59,536 product configurations respectively. These are one Fe₄S₄ family with altered selected subspaces, not independent chemical families.
- Outcome: generation and immediate read-only `--check` passed; no solver, GPU kernel, timing, or energy reference was produced in this step.
- Decision: Commit the generator, manifest, data, tests, and correctness-only calibration config before running calibration so the runner captures a clean project state.
