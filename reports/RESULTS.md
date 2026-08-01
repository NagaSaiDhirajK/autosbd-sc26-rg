# Internal Stage 2 engineering and correctness results

Status date: 2026-08-01

This is an internal, traceable evidence report. It is not an abstract, submission summary, poster, or source of ready-to-submit student prose.

## Outcome

Stage 2 is complete. The single-run and sequential sweep harnesses produce atomic, immutable schema-v2 JSON records; enforce official AMD source/build provenance and node safety; distinguish process success from scientific success; and resume exact trials without rewriting raw records.

The standard-library suite passes all 67 tests. Coverage includes strict config loading, feature extraction, SBD parsing, process-group timeout cleanup, telemetry failure modes, schema-v1 compatibility, schema-v2 identity validation, stale claim recovery, node-lock contention, input mutation, artifact hashing, exact resume/new attempts, official upstream/binary rejection, and the validation-manifest timing gate.

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

No final CPU/GPU speedup, crossover, selector benefit, or headline performance claim can be derived from this pair. Stage 3 must first prepare the workload scale, run a bounded pilot, and freeze a clean manifest-linked timing protocol.
