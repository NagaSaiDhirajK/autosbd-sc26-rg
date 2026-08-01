# Internal engineering, repeated-timing, and selector results

Status date: 2026-08-01

This is an internal, traceable evidence report. It is not an abstract, submission summary, poster, or source of ready-to-submit student prose.

## Outcome

Stages 2–4 and the current single-family Stage 5 evaluation are complete. Phase B1 provenance, unchanged-input compatibility, and smallest-case N₂/H₂O CPU/GPU correctness also pass. Phase B2 preparation now provides ten deterministic N₂/H₂O workloads, family-aware future raw identities, and external Fe₄S₄ augmentation without rewriting history. The harness enforces official AMD source/build provenance and node safety, distinguishes process success from scientific success, and resumes exact trials without rewriting raw records. Stage 4 contributes repeated eligible Fe₄S₄ timing; corrected Stage 5 artifacts provide grouped size-held-out evaluation and selector-overhead evidence. New-grid correctness, N₂/H₂O timing, and multifamily evaluation remain pending.

The standard-library suite passes all 155 tests. Coverage includes strict config loading, feature extraction, workload preparation, SBD parsing, process-group timeout cleanup, telemetry failure modes, schema-v1 compatibility, schema-v2/v3 identity validation, stale claim recovery, node-lock contention, input mutation, artifact hashing, exact resume/new attempts, official upstream/binary rejection, multi-input validation, family-aware calibration-manifest timing gates, deterministic aggregation, grouped evaluation, corrected threshold candidates, unique-policy artifacts, inference-overhead accounting, strict Phase B input/provenance/registry validation, and density-length enforcement.

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

No final CPU/GPU speedup, crossover, selector benefit, or headline performance claim can be derived from this pair alone. The separately gated pilot and repeated Stage 4 protocol provide the timing evidence reported below; they do not retroactively change this pair's ineligible status.

## Phase B1 authentic N₂/H₂O correctness

The exact smallest complete N₂/6-31G and H₂O/cc-pVDZ datasets retained from `r-ccs-cms/sbd` tag `v1.3.0` were consumed unchanged by the same official `AMD-HPC/amd-sbd` commit and existing NVIDIA HPC SDK 26.5 CPU16/GPU artifacts used elsewhere in this project. The RIKEN checkout supplied licensed data only; no RIKEN executable was built or run. Both CPU/GPU pairs used identical solver settings and exact matching input descriptions.

| Family | Configurations | Iterations | CPU/GPU energy (Ha) | CPU/GPU residual | Energy relative difference | Density max abs difference | Peak host RSS CPU/GPU (MiB) | Peak GPU allocation (MiB) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| N₂ / 6-31G | 57,121 | 18 | `-109.0415109298453 / -109.0415109298453` | `9.7461579e-9 / 9.7462004e-9` | `0` | `3.1974e-14` | `35.324 / 131.488` | `194` |
| H₂O / cc-pVDZ | 75,625 | 19 | `-76.23593762863838 / -76.23593762863834` | `6.3507189e-9 / 6.3507321e-9` | `5.5922e-16` | `1.9984e-14` | `41.410 / 138.066` | `196` |

All four records are terminal successes from clean project commit `b0324dd011b87c13a0902ada46f5a44f62a543a6`. Each residual is at most `1e-8`; iteration counts match exactly within a family; density lengths equal `NORB` (18 and 24); energy and density differences are below `1e-10`; inputs are unchanged across initial, before-launch, and after-run checks; and stdout, stderr, and resource artifacts verify against their recorded hashes. Both GPU trials required target offload, printed the exact device-assignment evidence, were observed allocating on the L4, and have complete host/GPU telemetry. The L4 was idle at every preflight.

The four immutable record IDs are:

- N₂ CPU `16cda11507164d29f1528889b61d9a1560105fe96791edf75e2187922c36f0a8` and GPU `3c190b275f4c7521631b333a22dad44249d57b7f13ca1715a4e4644e2670af23`;
- H₂O CPU `52b394f95cad7a1fca0d929ef1e099780ffb730c3156b48afa8d2270fef748d0` and GPU `15c1e429c88423849e587e132bbf588caa1545cc9e27270a63f4a23d2d0de716`.

The deterministic combined gate is `reports/phaseb_n2_h2o_correctness_manifest.json`, SHA-256 `fc73db40f756384e86852e8a7a12ec00fe8838db25683681aa12eceb9bdf38c5`. An immediate identical builder invocation reported `status=unchanged`. These trials used zero warmups, one repetition, and purpose `correctness`; all have `timing_eligible=false`. Their diagnostic wall fields are excluded from performance analysis. The manifest validates only these two exact input hashes, not larger lists or future derived prefixes.

## Phase B2 multifamily preparation (no new solver result)

The N₂/6-31G and H₂O/cc-pVDZ determinant grids now contain nested counts `32, 55, 100, 174`, plus each full official smallest list (`239` and `275`). `data/derived/phase_b_prefixes/manifest.json`, SHA-256 `852c6c99b279610b413e29472e4839fc178fc63e094b01275f4bf3aaae57d373`, binds every output to its exact parent, FCIDUMP, molecule/basis, electron/orbital counts, product configurations, license, input-data commit, and the official-AMD-only solver boundary.

Future config-schema-2 trials emit raw schema 3 and bind `family_id`, molecule, and basis into logical identity; all historical schema-v2 records remain unchanged. `reports/stage4_fe4s4_family_registry.json`, SHA-256 `cfeb5f60e29d01068c68b9d348739fba4b4e204e5165edce899aff5dfa94395d`, maps the 48 frozen Stage 4 records to five exact Fe₄S₄ workloads while recording its basis as null/`upstream_not_reported`. The prepared correctness protocol is `configs/phaseb_n2_h2o_grid_correctness.yaml`.

This section reports preparation only. No new derived-prefix solver run has occurred; the eight non-full hashes have no dynamic correctness evidence; all ten inputs require the homogeneous v3 CPU/GPU gate before the pilot; and no timing or cross-family selector claim is supported yet.

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

The deterministic aggregation is `results/processed/stage3_pilot.json` (SHA-256 `0e5a6ce892377125f988a9cdc4a793e4071053d1cc8fefb151a8e324bbd001f6`) with companion `results/processed/stage3_pilot.csv` (SHA-256 `816a4c1afac501006ed4d0a656da12d7c83db0abc8bbc9620a17ff4a56f9d35c`).

## CPU-thread pruning pilot

The missing CPU1/4/8 layer was measured at the three smallest sizes from clean project commit `63c7fba3dcfc50a09dd849b1ada539ce31073cc9`. All 18 records succeeded and passed the same manifest, correctness, integrity, provenance, monitoring, and timing-eligibility gates. Nine warmups are excluded and nine measurements are included; exact rerun launched zero solvers and reused all 18 records.

| Configurations | CPU1 wall (s) | CPU4 wall (s) | CPU8 wall (s) | CPU16 wall (s) | GPU wall (s) | Candidate-set oracle |
|---:|---:|---:|---:|---:|---:|---|
| 1,024 | `4.825855` | `2.214880` | `1.612399` | `1.411639` | `1.626366` | CPU16 |
| 3,025 | `18.586237` | `5.528791` | `3.319507` | `2.417825` | `1.936307` | GPU |
| 10,000 | `67.193500` | `17.886047` | `9.549781` | `5.635353` | `2.835080` | GPU |

CPU16 is the fastest CPU at every tested size. Relative to CPU16, CPU8 is 14.2%, 37.3%, and 69.5% slower; CPU4 and CPU1 are slower still. None is at least 10% faster, and adding any dominated alternate changes no full candidate-set CPU/GPU winner. D-025 therefore prunes CPU1/4/8 and retains CPU16 plus the L4 GPU.

The combined 38-record pilot aggregation is `results/processed/stage3_candidate_pilot.json` (SHA-256 `3e066afa35217cddba203df33b294966ce24227fa59d3e2267b64fc4ac36d17c`) with companion CSV SHA-256 `b381cff4d7df939a9a5d593f4304ff4a6b4e253faeb728284ee91400eb479dee`. This is still single-repetition pruning evidence. The frozen Stage 4 design is `reports/stage4_protocol.json` (SHA-256 `29431c68e84cee75a280c5b5faf3d2a15f1eb2ec2c16f4f5ce37796ef5f307f6`): five measured repetitions at sizes 32/55, three at sizes 100/174/244, and one excluded warmup per workload/candidate.

## Repeated Stage 4 final timing

The three frozen shards completed sequentially with the official same-commit AMD CPU16 and L4 GPU binaries. All 48 immutable records passed the protocol, provenance, correctness, input-integrity, and monitoring checks: 10 warmups are excluded and 38 measured records are timing-eligible. There were no failures, timeouts, OOMs, or skips.

| Configurations | CPU16 median (s) | CPU16 IQR (s) | L4 GPU median (s) | L4 GPU IQR (s) | Winner |
|---:|---:|---:|---:|---:|---|
| 1,024 | `1.410925` | `0.000740` | `1.628517` | `0.008686` | CPU16 |
| 3,025 | `2.416199` | `0.001738` | `1.920699` | `0.002750` | GPU |
| 10,000 | `5.633912` | `0.001334` | `2.840412` | `0.071125` | GPU |
| 30,276 | `29.969005` | `0.001376` | `8.776809` | `0.006735` | GPU |
| 59,536 | `78.400978` | `0.156180` | `17.261023` | `0.063130` | GPU |

The repeated medians retain the observed winner flip between 1,024 and 3,025 configurations for these candidates on this node. The aggregate is `results/processed/stage4_final.json`, SHA-256 `58c6b6bc2454de9237a102a3d3d6b3628d0bb98b0f0758cf0353d9edc64885aa`; its frozen protocol and completion manifests have SHA-256 values `29431c68e84cee75a280c5b5faf3d2a15f1eb2ec2c16f4f5ce37796ef5f307f6` and `7fefb110d29b0bfae2ece24a3506bd6fa53e6e81257f57779ce2067e9910ee36`.

## Corrected Stage 5 size-held-out evaluation

The evaluation deliberately uses a balanced view of repetitions 0–2: 30 Stage 4 measurements become 10 median candidate rows across five nested Fe₄S₄ sizes and two candidates. The primary split trains on four complete instances and holds out the largest; five leave-one-instance-out folds are secondary sensitivity analysis. All candidates and repetitions for an instance remain in one split, and every train/test record-ID intersection is empty.

On the 59,536-configuration primary holdout, fixed GPU, the static threshold, the size-only tree, the full tree, and the measured oracle all select the GPU with zero normalized regret. Fixed CPU16 has normalized regret `3.542081714297355`. The upstream default is recorded only as a provenance alias for fixed GPU and is not counted as a seventh policy.

| LOIO policy | Selection accuracy | Geometric selected/oracle runtime | Maximum normalized regret |
|---|---:|---:|---:|
| Fixed CPU16 | `0.2` | `2.0779687720600366` | `3.542081714297355` |
| Fixed GPU | `0.8` | `1.0297715282069095` | `0.15798890949019462` |
| Static geometric-midpoint threshold | `0.6` | `1.078390418002942` | `0.25943483534277495` |
| Size-only tree | `0.8` | `1.0472132783479557` | `0.25943483534277495` |
| Full tree | `0.8` | `1.0472132783479557` | `0.25943483534277495` |
| Measured feasible oracle | `1.0` | `1.0` | `0` |

There are no invalid selections and no failures. The full-feature tree does not outperform the size-only tree on this dataset. The threshold uses training-only `always_gpu`, adjacent-size geometric-midpoint, and `always_cpu` candidates with explicit JSON-null sentinel thresholds; its corrected LOIO result is not perfect.

The Stage 5 configuration SHA-256 is `21ad73381a156d424cd762a18a2fb3b897e074824665d96d6e631837021eb0f1`. Core artifacts are `results/processed/stage5/evaluation.json` (`9b2f163e6267f2ec3b3eb2c04f76405ca96c30f16dcfbf1c789a1173cb1e3b6e`), `models.json` (`85f8a84e1d40163b9971ba8d9d9fab47dd049adf036b95c5f0b8f6c11884eb1c`), and `policy_summary.json` (`7bfff41c644886884b6524d64a16e41df542b79a7767484a28c94474d1ddd9c0`).

## Selector inference overhead

With the deployment full tree already loaded, the measured hot path includes feature mapping, memory-feasibility filtering, both candidate predictions, and deterministic argmin. After 1,000 warmups, 10,000 iterations have median `38.65 us`, p90 `42.6673 us`, and p95 `48.7131 us`. The hot median is `0.002739337080263366%` of the shortest Stage 4 SBD median (`1.4109253030037507 s`).

The object-cold diagnostic reads and strictly deserializes `models.json` before selection. Across 100 iterations after 10 warmups its median is `929.11 us`; OS page-cache state is uncontrolled, so this is not a storage-cache-cold claim. Immutable raw samples are `results/raw/inference_overhead/50b9351e5d3ab74fdb71a8915acdcd682891d736b58db1e86ef64d400c2fb6b4.json`, SHA-256 `ea293deabbd2c904e1b432a88075c750db9ef7eb595d58d8a45fc452e1c4d356`. Processed JSON and CSV hashes are `ddb33f39682d5c1318c3e2d65560bb8e9232309cc522324670565c928cee10cf` and `678b45509c1733ffd4d22541496be2644c77fbc81b922e8ba13c877982104fbc`.
