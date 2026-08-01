# Internal Stage 2 engineering and Stage 3 calibration results

Status date: 2026-08-01

This is an internal, traceable evidence report. It is not an abstract, submission summary, poster, or source of ready-to-submit student prose.

## Outcome

Stage 2 is complete. Stage 3 workload preparation, five-size correctness calibration, and the bounded CPU16/GPU pilot are complete. The single-run and sequential sweep harnesses produce atomic, immutable schema-v2 JSON records; enforce official AMD source/build provenance and node safety; distinguish process success from scientific success; and resume exact trials without rewriting raw records.

The standard-library suite passes all 96 tests. Coverage includes strict config loading, feature extraction, workload preparation, SBD parsing, process-group timeout cleanup, telemetry failure modes, schema-v1 compatibility, schema-v2 identity validation, stale claim recovery, node-lock contention, input mutation, artifact hashing, exact resume/new attempts, official upstream/binary rejection, multi-input validation, the calibration-manifest timing gate, and deterministic timing aggregation.

The mock smoke sweep exercises five terminal behaviors: one success, one scientific nonconvergence, one nonzero process failure, one timeout with child cleanup, and one simulated OOM. Re-running the same sweep reuses all five immutable trial IDs.

## Authentic official AMD correctness pair

Both candidates used the official `AMD-HPC/amd-sbd` `sc26-artifacts` commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`, built from the same unmodified checkout with NVIDIA HPC SDK 26.5. The input was the upstream Fe₄S₄ sample: 36 orbitals, 244 alpha and 244 beta half-determinants, and 59,536 product configurations. CPU and GPU used identical solver parameters and determinant/FCIDUMP hashes.

| Recorded field | CPU, 16 threads | NVIDIA L4 GPU |
|---|---:|---:|
| Schema-v2 trial ID | `9f9031146690fe8afd04b94fced38551c7863ea95d62ff35404f022895055d1d` | `1b7be4e302c4b8185d7960e04af7bf42abc4b41c49dfb0d3727a790383de6125` |
| Status / correct | success / true | success / true |
| Davidson iterations | 50 | 50 |
| Final residual | `8.931146441578446e-09` | `8.931494922593578e-09` |
| Final energy (Ha) | `-326.6982536731583` | `-326.6982536731581` |
| End-to-end wall (s) | `78.72754408099718` | `17.221985976000724` |
| Solver-reported time (s) | `76.066536` | `15.509004` |
| Peak sampled host RSS (MiB) | `47.6484375` | `145.0859375` |
| Peak sampled GPU allocation (MiB) | not applicable | `198` |
| Resource samples | 783 | 115 |
| Timing eligible | false | false |

Cross-backend acceptance passed all four checks:

- both final residuals are at most `1e-8`;
- energy absolute error is `2.2737367544323206e-13 Ha`;
- energy relative error is `6.959745663982201e-16`, below `1e-10`; and
- maximum absolute density difference is `2.7017277304253184e-13`, below `1e-10` (density L2 error `4.126804786123131e-13`).

GPU monitoring was complete, observed the solver's GPU allocation, and recorded mandatory target offload to device 0. Both inputs remained byte-identical across the initial, before-launch, and after-run SHA-256 checks. The stdout, stderr, and resource CSV for each trial are independently hash-linked from its raw JSON record.

Machine-readable comparison: `reports/stage2_amd_correctness.json`. Hash-linked evidence manifest: `reports/stage2_amd_validation_manifest.json`. Immutable records are under `results/raw/`.

## Timing eligibility

The durations above are correctness-smoke diagnostics, not benchmark results. These trials had zero warmups, protocol purpose `correctness`, and were executed against an uncommitted Stage 2 worktree before the correctness manifest was linked as prior protocol evidence. Schema v2 therefore records `timing_eligible=false` for both.

No final CPU/GPU speedup, crossover, selector benefit, or headline performance claim can be derived from this pair. A bounded pilot and later repeated final protocol are still required before performance conclusions.

## Definitive five-size correctness calibration

Five exact nested prefixes of the official Fe₄S₄ alpha-determinant list were checked with the same FCIDUMP, solver identity, official AMD commit, and NVIDIA HPC SDK 26.5 CPU/GPU binaries. All ten clean records succeeded and converged. An immediate identical rerun returned `launched=0` and `reused=10`, proving exact cross-process resume after the narrow generated-record cleanliness fix.

| Determinants | Configurations | Iterations | CPU energy (Ha) | Energy relative difference | Density max abs difference | Diagnostic wall CPU/GPU (s) |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 1,024 | 22 | `-326.5622181729457` | `0` | `5.997e-13` | `1.413 / 1.627` |
| 55 | 3,025 | 26 | `-326.5689554798624` | `5.222e-16` | `8.046e-13` | `2.418 / 1.932` |
| 100 | 10,000 | 27 | `-326.5847957019396` | `1.044e-15` | `6.466e-13` | `5.636 / 2.968` |
| 174 | 30,276 | 46 | `-326.6593248445312` | `3.480e-16` | `5.375e-13` | `29.663 / 8.774` |
| 244 | 59,536 | 50 | `-326.6982536731583` | `6.960e-16` | `2.702e-13` | `78.438 / 17.366` |

Every residual is at most `1e-8`, CPU/GPU iteration counts match exactly, and GPU preflight, process monitoring, mandatory offload, device assignment, input integrity, binary identity, and run-artifact hashes all pass. The deterministic schema-v2 gate is `reports/stage3_calibration_manifest.json`, SHA-256 `6fcc273d84f65d20185c0abcba9b750a29c2d64a87c982e500a4be5cdd93bdec`.

These wall values are correctness diagnostics only. All ten source records have `purpose=correctness` and `timing_eligible=false`; the table establishes no speedup or crossover claim. `configs/stage3_pilot.yaml` links each exact reference and input to the manifest and specifies one warmup plus one measured repetition for each backend, sequentially and in randomized order.

## Bounded Stage 3 crossover pilot

The pilot ran from clean project commit `2ddbb40953e36194531fcd48966ecacaefb09959` with the same official AMD source, exact CPU/GPU binaries, calibrated references, and five-input validation manifest. All 20 sequential trials succeeded and passed correctness, input-integrity, monitoring, and provenance gates. Ten warmups are explicitly timing-ineligible; ten measured trials are eligible. An immediate exact rerun launched zero solvers and reused all 20 records.

| Configurations | CPU16 wall (s) | L4 GPU wall (s) | CPU/GPU wall ratio | Pilot winner |
|---:|---:|---:|---:|---|
| 1,024 | `1.411639` | `1.626366` | `0.867971` | CPU16 |
| 3,025 | `2.417825` | `1.936307` | `1.248678` | GPU |
| 10,000 | `5.635353` | `2.835080` | `1.987723` | GPU |
| 30,276 | `29.978079` | `8.816813` | `3.400104` | GPU |
| 59,536 | `78.545336` | `17.269417` | `4.548233` | GPU |

This single measured repetition locates an observed winner flip between 1,024 and 3,025 configurations. It provides no variance, IQR, confidence interval, exact threshold, or final speedup claim. Candidate order was randomized within each workload/phase block; sizes remained ascending and all warmups preceded measurements. The prefixes are correlated variants of one Fe₄S₄ family.

The deterministic aggregation is `results/processed/stage3_pilot.json` (SHA-256 `0e5a6ce892377125f988a9cdc4a793e4071053d1cc8fefb151a8e324bbd001f6`) with companion `results/processed/stage3_pilot.csv` (SHA-256 `816a4c1afac501006ed4d0a656da12d7c83db0abc8bbc9620a17ff4a56f9d35c`). The next bounded step measures CPU 1/4/8-thread candidates at the three smallest sizes and prunes them under the predeclared rule in D-024 before final repetitions are frozen.
