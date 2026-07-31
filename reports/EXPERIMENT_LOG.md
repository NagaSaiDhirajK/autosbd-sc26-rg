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
