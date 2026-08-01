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

## 2026-08-01 — Initial derived-size CPU/GPU correctness calibration and resume anomaly

- Purpose: Establish identical-input CPU/GPU convergence, energy, iteration, and density agreement for the four non-full Fe₄S₄ prefixes before any timing protocol.
- Configuration identifier: `stage3-amd-fe4s4-derived-calibration`; official AMD commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`; NVIDIA HPC SDK 26.5 CPU16/GPU binaries; method 0, block 10, iteration allowance 6, tolerance `1e-8`, no reference value, zero warmups, one correctness repetition.
- Safety: project/upstream were clean; L4 was idle with 22,564 MiB free, 34 °C, and 0% utilization; host load was 0.04 with about 122 GiB available. All eight trials ran sequentially under the node lock.
- Clean accepted record pairs: size 32 `a0975487...c57d`/`2681cbbb...d143`; size 55 `51132580...b338`/`ee44ef1c...c933`; size 100 `7e9ff4fe...5186`/`a24a1104...fca7`; size 174 `d2dc37a2...f3439`/`cea5de6f...6b69` (CPU/GPU).
- Outcomes: all records have `project_git_dirty=false`, status/scientific success true, unchanged inputs, verified artifacts, complete host monitoring, and GPU process/device observation. Iteration counts match by pair: 22, 26, 27, and 46. CPU reference energies are `-326.5622181729457`, `-326.5689554798624`, `-326.5847957019396`, and `-326.6593248445312 Ha`. Maximum pairwise energy relative error is `1.044324529657896e-15`; maximum density absolute difference is `8.046341370970822e-13`; all residuals are at most `1e-8`.
- Timing boundary: diagnostic wall values ranged from 1.411/1.626 s at size 32 to 30.383/8.865 s at size 174 (CPU/GPU). Every record has `timing_eligible=false`; no speedup or benchmark conclusion is drawn.
- Resume anomaly: the immediate new-process rerun saw the first eight untracked raw records as project dirt, derived new logical identities, and launched eight duplicates instead of reusing. Duplicate IDs are `9c0536bf...8246`, `1dd8836d...22f6`, `b412bebe...bb08`, `a17813d5...18a8`, `bdf7baac...4838`, `b37ffb07...bc52`, `0d9e1df5...4777`, and `47cc860c...1967`; all say `project_git_dirty=true` and are excluded.
- Decision: Preserve all 16 immutable records. Fix and test the narrow source-dirty rule, commit it, then rerun the now-five-size calibration and prove `launched=0` on exact resume before creating pilot evidence.

## 2026-08-01 — Definitive five-size official AMD CPU/GPU correctness calibration

- Purpose: Establish the definitive correctness gate for all five Fe₄S₄ determinant-prefix sizes before any pilot timing evidence is admitted.
- Configuration identifier: `stage3-amd-fe4s4-calibration`; project commit `7bdb03d`; official `AMD-HPC/amd-sbd` at pinned commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`; CPU and NVIDIA OpenMP-offload GPU executables built through the single NVIDIA HPC SDK 26.5 toolchain.
- Scope and execution: sizes 32, 55, 100, 174, and 244 were each run on the CPU and GPU candidates for 10 total correctness trials. All 10 records were clean, successful, and numerically correct. The immediate exact resume launched 0 trials and reused all 10 immutable records.
- Correctness manifest: `reports/stage3_calibration_manifest.json`, schema 2, SHA-256 `6fcc273d84f65d20185c0abcba9b750a29c2d64a87c982e500a4be5cdd93bdec`, validates all five identical-input CPU/GPU pairs.
- Pairwise agreement: maximum energy relative error `1.044e-15`; maximum absolute density difference `8.046e-13`; every final residual was at most `1e-8`; CPU and GPU iteration counts matched exactly for every size.
- Full-size check: at size 244, CPU energy was `-326.6982536731583 Ha`, GPU energy was `-326.6982536731581 Ha`, and both candidates completed 50 iterations.
- Diagnostic-only walls (CPU/GPU seconds): size 32 `1.413/1.627`; size 55 `2.418/1.932`; size 100 `5.636/2.968`; size 174 `29.663/8.774`; size 244 `78.438/17.366`.
- Timing boundary: these are correctness-run diagnostics only. They are not timing evidence and support no speedup, crossover, or performance claim.
- Decision: Accept the schema-2 manifest as the correctness gate for the five-size pilot. Continue exclusively with the official AMD implementation; no RIKEN executable was used in this calibration.

## 2026-08-01 — Stage 3 five-size official AMD CPU/GPU pilot

- Purpose: Run the warmup-enabled, manifest-gated five-size pilot needed to locate a provisional CPU/GPU crossover bracket and decide whether the candidate axis is ready to freeze for Stage 4.
- Configuration identifier: `stage3-amd-fe4s4-derived-pilot`; project commit `2ddbb40953e36194531fcd48966ecacaefb09959`; official pinned `AMD-HPC/amd-sbd` CPU16 and NVIDIA OpenMP-offload GPU artifacts built through the single NVIDIA HPC SDK 26.5 toolchain.
- Command: `PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage3_pilot.yaml --require-all-success`.
- Initial execution: exit 0; `launched=20`, `reused=0`, and `success=20`.
- Exact resume: the unchanged command exited 0 with `launched=0`, `reused=20`, and `success=20`; no solver was relaunched.
- Evidence audit: all 20 immutable records are correct, manifest-valid, clean, input-stable, and linked to hash-valid record/build/stdout/stderr/resource artifacts. All GPU records additionally contain complete idle-preflight, mandatory-device, process-observation, allocation, and telemetry evidence.
- Eligibility: all 10 warmups have `timing_eligible=false`; all 10 measured records have `timing_eligible=true` and satisfy every runner gate.
- Blocking/randomization: CPU and GPU candidate order was randomized within each workload/phase block using the fixed protocol seed, while trials remained sequential under the node lock.

| Product configurations | CPU wall (s) | GPU wall (s) | CPU/GPU wall ratio |
| ---: | ---: | ---: | ---: |
| 1,024 | 1.411638932 | 1.626366254 | 0.867971 |
| 3,025 | 2.417824946 | 1.936307472 | 1.248678 |
| 10,000 | 5.635352831 | 2.835080121 | 1.987723 |
| 30,276 | 29.978079477 | 8.816812631 | 3.400104 |
| 59,536 | 78.545336090 | 17.269417439 | 4.548233 |

- Internal pilot observation: CPU had the lower measured wall time at 1,024 configurations and GPU had the lower measured wall time at 3,025 configurations, so the observed crossover bracket is 1,024–3,025 for these exact candidates and conditions only.
- Limitations: each candidate has one measured repetition, so there is no uncertainty estimate and no final speedup claim. All five sizes are nested selected-subspace variants of one Fe₄S₄ family, not independent chemical families.
- Decision: The Stage 3 exit criterion is met. Run the missing CPU thread-count pilot at sizes 32, 55, and 100 before freezing Stage 4 configurations; do not treat this pilot as final repeated timing evidence.

## 2026-08-01 — Stage 3 official AMD CPU-thread pilot and exact resume

- Purpose: Close the missing CPU thread-count axis required by D-024 and decide which CPU candidates enter the frozen Stage 4 protocol.
- Configuration identifier: `stage3-amd-fe4s4-derived-thread-pilot`; clean project commit `63c7fba3dcfc50a09dd849b1ada539ce31073cc9`; official pinned `AMD-HPC/amd-sbd` CPU artifact built with NVIDIA HPC SDK 26.5; CPU candidates use 1, 4, and 8 threads at determinant-prefix sizes 32, 55, and 100.
- Command: `PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage3_thread_pilot.yaml --require-all-success`.
- Initial execution: exit 0 after approximately 4.1 minutes; `launched=18`, `reused=0`, and `success=18`.
- Exact resume: the unchanged command exited 0 with `launched=0`, `reused=18`, and `success=18`; no solver was relaunched.
- Eligibility and integrity: all nine warmups have `timing_eligible=false`; all nine measured records have `timing_eligible=true`. Every record is successful, correct, clean, manifest-valid, input-stable, completely host-monitored, and bound to the official AMD/NVHPC provenance.

| Determinant count | CPU1 wall (s) | CPU4 wall (s) | CPU8 wall (s) | CPU16 pilot wall (s) | GPU pilot wall (s) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 32 | 4.825855236 | 2.214880025 | 1.612398808 | 1.411638932 | 1.626366254 |
| 55 | 18.586236788 | 5.528790712 | 3.319506759 | 2.417824946 | 1.936307472 |
| 100 | 67.193500417 | 17.886046947 | 9.549780616 | 5.635352831 | 2.835080121 |

- Alternate/CPU16 wall ratios by size 32/55/100: CPU1 `3.418619/7.687172/11.923566`; CPU4 `1.569013/2.286679/3.173900`; CPU8 `1.142218/1.372931/1.694620`.
- D-024 audit: CPU16 is the fastest CPU at all three tested sizes. No alternate is at least 10% faster than CPU16, and adding any dominated alternate leaves the candidate-set CPU/GPU oracle unchanged. At size 32, CPU1 and CPU4 individually lose to GPU while CPU16 wins; this substitution does not change the full candidate-set oracle because CPU16 remains available and faster.
- Limitations: each candidate has one measured repetition, the CPU16/GPU baseline and thread pilot are separate committed batches, and all sizes are nested variants of one Fe₄S₄ family. These values support candidate pruning only, not a final timing or general performance claim.
- Decision: Prune CPU1, CPU4, and CPU8; retain CPU16 and GPU; freeze the Stage 4 candidate axis. No RIKEN executable was used.

## 2026-08-01 — Preliminary Stage 5 single-family held-out evaluation

- Purpose: execute and inspect the frozen selector evaluation before applying completion-handoff Phase A hardening.
- Inputs: 30 immutable timing-eligible Stage 4 measurements: five nested Fe4S4 determinant-prefix sizes, two official AMD candidates, and repetitions 0–2 only.
- Split integrity: primary training uses four instances/24 records and holds out `fe4s4-prefix-0244`/6 records; five leave-one-instance-out folds each use 24/6 records; every train/test record-ID intersection is empty.
- Preliminary primary outcome: at 59,536 configurations, CPU median wall time is `78.40097830099694 s` and GPU median is `17.261023300001398 s`. GPU, threshold, both trees, and oracle have zero regret; fixed-CPU normalized regret is `3.542081714297355`.
- Preliminary sensitivity outcome: the threshold is correct on 5/5 instances with zero regret. Full and size-only trees make identical choices, are correct on 4/5, and miss only the 3,025-configuration GPU winner; maximum normalized regret is `0.25943483534277495` and geometric selected/oracle runtime is `1.0472132783479557`.
- Validity: zero invalid selections and zero failures. The full-feature tree does not outperform the size-only tree on this dataset.
- Defects found: threshold candidates used implicit observed-size boundaries instead of explicit sentinels/geometric midpoints, and `upstream_default` was emitted as a seventh policy identical to fixed GPU.
- Evidence status: these preliminary artifact hashes are superseded by the Phase A correction run and are not final Stage 5 evidence. No new SBD solver benchmark ran.

## 2026-08-01 — Corrected Stage 5 held-out evaluation and inference overhead

- Purpose: complete Phase A with exact threshold semantics, six nonduplicated policies, complete summary fields, and deployment-overhead evidence.
- Data: unchanged balanced view of 30 immutable Stage 4 measurements, 10 candidate medians, five nested Fe4S4 sizes, and one authentic problem family. All splits remain grouped by instance with zero train/test record overlap.
- Primary largest-size holdout: at 59,536 configurations, fixed GPU, the 1,760-configuration training-only threshold, both trees, and oracle select GPU with zero regret. Fixed CPU has normalized regret `3.542081714297355`. Every policy decision is valid and no failure occurs.
- Corrected leave-one-instance-out sensitivity: fixed GPU is correct on 4/5 with geometric selected/oracle runtime `1.0297715282069095` and maximum regret `0.15798890949019462`; static threshold is 3/5 with geometric ratio `1.078390418002942` and maximum regret `0.25943483534277495`; both full and size-only trees are 4/5 with geometric ratio `1.0472132783479557` and maximum regret `0.25943483534277495`. Full and size-only tree decisions are identical, so richer features show no measured benefit in this dataset.
- Threshold representation: candidates are explicit always-GPU, adjacent geometric midpoints, and always-CPU; sentinel thresholds are JSON null. Deployment and primary training select midpoint 1,760.
- Overhead protocol: 1,000/10,000 hot warmup/measured iterations and 10/100 load-plus-selection warmup/measured iterations. Hot median/p90/p95 are `38.65/42.6673/48.7131 us`; cold diagnostic median/p90/p95 are `929.11/936.1551/939.67855 us`. Hot median is `0.002739337080263366%` of the shortest `1.4109253030037507 s` SBD median.
- Resources: overhead run wall time `1.53 s`, maximum RSS `114,560 KiB`, no GPU use; L4 remained idle before and after.
- Evidence: evaluation SHA `9b2f163e6267f2ec3b3eb2c04f76405ca96c30f16dcfbf1c789a1173cb1e3b6e`; models SHA `85f8a84e1d40163b9971ba8d9d9fab47dd049adf036b95c5f0b8f6c11884eb1c`; policy-summary SHA `7bfff41c644886884b6524d64a16e41df542b79a7767484a28c94474d1ddd9c0`; immutable overhead raw SHA `ea293deabbd2c904e1b432a88075c750db9ef7eb595d58d8a45fc452e1c4d356`; processed overhead JSON/CSV SHAs `ddb33f39682d5c1318c3e2d65560bb8e9232309cc522324670565c928cee10cf` and `678b45509c1733ffd4d22541496be2644c77fbc81b922e8ba13c877982104fbc`.
- Boundary: these results describe one heterogeneous node and one authentic family. Leave-one-instance-out is sensitivity evidence, not independent-family generalization.

## 2026-08-01 — Phase B1 static N₂/H₂O provenance and compatibility gate

- Purpose: determine whether exact authentic N₂/6-31G and H₂O/cc-pVDZ inputs retained from pinned RIKEN `v1.3.0` can enter correctness-only runs through the same official AMD CPU16 and NVIDIA OpenMP-offload GPU implementation used by the existing pipeline.
- Source-data identity: `https://github.com/r-ccs-cms/sbd.git`, exact tag `v1.3.0`, commit `b71e1c3ed857fcb4fb05731dc285831c1afe9ebd`, clean checkout, Apache-2.0 license. This checkout supplies data only; its solver was not built or executed.
- Active implementation: official `AMD-HPC/amd-sbd` commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`; exact existing NVIDIA HPC SDK 26.5 CPU/GPU artifacts. No solver substitution or source patch is permitted.
- Inventory result: PASS. The fail-closed inventory validates 20 artifacts: one license, two README files, two FCIDUMPs, and 15 determinant lists. It verifies exact paths/URLs/sizes/hashes, checkout identity/cleanliness, complete family-directory coverage, FCIDUMP headers and five-field records, determinant width/population/uniqueness, and smallest closed-shell product counts.
- Smallest N₂ case: FCIDUMP SHA `dee67eb5e8aee2f099953a52d7910db59bc7b284ad03a8fa7ffd2a4ba8efcf33`; determinant SHA `73a28f6e6a26b06fbf4accf704f4112dca36ea53fe52ec40ed6379644b218dd2`; `NORB=18`, `NELEC=14`, 239 alpha strings, 57,121 product configurations.
- Smallest H₂O case: FCIDUMP SHA `a3c2302834a33dce7260e8050a3f5180e05dbba1bb748f3e2f6410a7eacbd94d`; determinant SHA `ea94906047a1d081d493066478e9f009c07cb4286541f1781060081205fd5a67`; `NORB=24`, `NELEC=10`, 275 alpha strings, 75,625 product configurations.
- Static compatibility result: PASS unchanged. The pinned AMD readers accept both exact FCIDUMP and determinant text formats; alpha strings are reused for beta in the intended closed-shell product space. No conversion, renaming, padding, truncation, reordering, source adaptation, or alternate solver is needed.
- Caveat: pinned AMD and RIKEN MPI FCIDUMP serialization precision differs. Upstream README energies therefore remain contextual provenance only; identical-input converged AMD CPU/GPU agreement is the acceptance test.
- Preparation anomaly: the first inventory validation exposed that both upstream README files lack a final newline. The manifest was corrected from newline-character counts to logical line counts without changing any upstream byte. Validation then passed.
- Runtime state: pending. No solver or GPU kernel ran in this block, and no wall time is timing evidence. The N₂/H₂O correctness configs remain `purpose: correctness`, `warmups: 0`, `repetitions: 1`, and `timing_eligible=false` by construction.
- Next gate: launch CPU first and stop on failure; only then launch the matching GPU. Require success, convergence, residual at most `1e-8`, exact iteration parity, energy relative error at most `1e-10`, density length equal to `NORB`, density maximum absolute difference at most `1e-10`, clean-tree/input/artifact integrity, and complete preflight/offload/monitoring evidence before producing the combined correctness manifest.
