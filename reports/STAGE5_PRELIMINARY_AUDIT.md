# Stage 5 preliminary engineering and scientific audit

## Status and scope

This is an internal engineering/scientific audit of the corrected Phase A Stage 5 evaluation. It is preliminary in the project-wide sense: it covers one authentic Fe₄S₄ family on one heterogeneous node and therefore does not establish cross-family generalization. Within that boundary, the corrected artifacts listed below are the authoritative Stage 5 Phase A evidence.

No SBD solver was run to create Stage 5. The evaluator uses 30 already-immutable, timing-eligible Stage 4 measurements. The only timed Phase A addition was a bounded CPU-side selector-overhead measurement; it did not launch a solver or GPU kernel.

This document is not an abstract, an 800-word submission summary, poster copy, poster source, or another student-authored submission. It supplies auditable facts and internal interpretation only. The student retains responsibility for submission prose, final interpretation, and all poster work.

## Official implementation and node provenance

The active implementation is exclusively the official `AMD-HPC/amd-sbd` repository:

| Item | Recorded value |
|---|---|
| Upstream URL | `https://github.com/AMD-HPC/amd-sbd` |
| Upstream commit | `729cfa3a5011fb805eb9e686a7711f6919836dcb` |
| Source state | Same clean, unmodified checkout for CPU and GPU executables |
| Toolchain | NVIDIA HPC SDK 26.5 |
| Direct compiler | `/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/compilers/bin/nvc++`, `nvc++ 26.5-0` |
| MPI wrapper | `/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/comm_libs/mpi/bin/mpic++`, backed by the same `nvc++` |
| MPI implementation | NVIDIA HPC-X 2.50 / Open MPI `5.0.10rc2` |
| GPU compilation | SDK-bundled CUDA 13.2, L4 target `sm_89`/`cc89` |
| CPU compilation | NVHPC OpenMP with `-tp=native` |
| CPU candidate | `amd-cpu-16`, one MPI rank and 16 CPU threads |
| GPU candidate | `amd-l4-default`, one MPI rank and one host thread |
| Host | `instance-20260731-140922`; machine fingerprint `37271488aa0cf91c3b79fd6e6bfba01cbe06a18898d2f98069a88ad84af6bbf8` |
| Heterogeneous node | 16 physical/32 logical Intel Xeon CPUs and one NVIDIA L4 |

The system CUDA 12.9 installation is not the compiler path for the primary AMD GPU executable. The retained RIKEN checkout and its earlier CUDA/Thrust probe are historical fallback evidence only; no RIKEN executable or timing contributes here.

Exact primary build artifacts are:

| Candidate | Path | Bytes | SHA-256 |
|---|---|---:|---|
| CPU16 | `build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu` | 797,304 | `190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07` |
| L4 GPU | `build/upstream/amd-729cfa3a-nvhpc-26.5/diag_gpu` | 2,021,216 | `8f1481b6bcb4ddf3326453fd3a7c03dc36e29034629f46c5e982a4c17e43bc07` |

## Immutable Stage 4 evidence used by Stage 5

Stage 4 is complete. Its frozen campaign contains 48 unique immutable raw records: 10 timing-ineligible warm-ups and 38 timing-eligible measured records. All 48 completed successfully, passed correctness, and have unique physical and logical trial IDs. The CPU and GPU each account for 24 records.

The Stage 5 balanced view uses measured repetition indices 0, 1, and 2 for every problem/candidate pair:

- 30 immutable timing measurements;
- five nested Fe₄S₄ determinant-prefix instances;
- two candidates per instance;
- three repetitions per instance/candidate;
- 10 median candidate rows used for training and evaluation;
- no warm-up or pilot timing in the model input.

A raw record may belong to more than one named Stage 4 analysis view, but it contributes at most once to any one statistic, policy row, or model input. No raw measurement was edited, deleted, interpolated, or regenerated for Stage 5.

Frozen source artifacts are:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `reports/stage4_protocol.json` | 3,633 | `29431c68e84cee75a280c5b5faf3d2a15f1eb2ec2c16f4f5ce37796ef5f307f6` |
| `reports/stage4_completion.json` | 72,167 | `7fefb110d29b0bfae2ece24a3506bd6fa53e6e81257f57779ce2067e9910ee36` |
| `results/processed/stage4_final.json` | 265,132 | `58c6b6bc2454de9237a102a3d3d6b3628d0bb98b0f0758cf0353d9edc64885aa` |
| Stage 3 correctness gate, `reports/stage3_calibration_manifest.json` | — | `6fcc273d84f65d20185c0abcba9b750a29c2d64a87c982e500a4be5cdd93bdec` |

## Leakage controls and splits

All candidates and all selected repetitions for an instance remain in the same split. Models and threshold rules fit only training instances. The split manifest reports `leakage_check: PASS`.

The primary split is a strict largest-size holdout:

- training instances: `fe4s4-prefix-0032`, `fe4s4-prefix-0055`, `fe4s4-prefix-0100`, and `fe4s4-prefix-0174`;
- test instance: `fe4s4-prefix-0244`;
- 24 training source records and six test source records;
- empty train/test source-record intersection.

The secondary sensitivity consists of five leave-one-problem-instance-out folds. Each fold has four training instances/24 source records and one test instance/six source records. Every fold has an empty train/test source-record intersection. These five predictions are grouped sensitivity evidence, not five independent chemical-family tests.

## Corrected threshold protocol

The threshold fitter registers candidates in deterministic order:

1. `always_gpu`, with `threshold_n_configurations: null`;
2. geometric midpoints between adjacent unique training sizes, in ascending order;
3. `always_cpu`, with `threshold_n_configurations: null`.

A finite midpoint selects CPU at or below the threshold and GPU above it. Exact objective ties retain the first registered candidate. For the primary training split, the complete candidate set and training geometric-mean selected/oracle objective are:

| Kind | Adjacent training sizes | Threshold | Training objective |
|---|---|---:|---:|
| `always_gpu` | — | `null` | 1.0373518839278586 |
| `geometric_midpoint` | 1,024 and 3,025 | 1,760 | 1.0 |
| `geometric_midpoint` | 3,025 and 10,000 | 5,500 | 1.0593608655455071 |
| `geometric_midpoint` | 10,000 and 30,276 | 17,400 | 1.2571905675114605 |
| `always_cpu` | — | `null` | 1.7089723454138952 |

The primary and all-five-instance deployment fits both select the 1,760 midpoint. The deployment registration additionally contains the 42,456 midpoint between 30,276 and 59,536 configurations. Fold-specific fits are expected to differ because each uses only its four training instances: leaving out 1,024 selects `always_gpu`; leaving out 3,025 selects 3,200; the other three folds select 1,760.

## Policy set and metric definitions

There are six unique policies, in the registered reporting order:

1. fixed CPU16;
2. fixed L4 GPU;
3. training-only static size threshold;
4. size-only tree ablation;
5. AutoSBD full-feature tree;
6. measured feasible oracle.

`upstream_default: fixed_gpu` remains in provenance metadata only. It is absent from prediction, metric, summary, ablation, and plotting rows, so it is not counted as a seventh baseline.

The tables use the following definitions:

- normalized runtime: selected median wall time divided by feasible-oracle median wall time;
- normalized regret: `(selected - oracle) / oracle`;
- geometric speedup versus a fixed baseline: baseline median divided by selected median;
- selection accuracy and within-5% rates use every requested instance as the denominator; invalid selections count as incorrect;
- regret distributions are over valid selections only.

## Primary largest-size holdout result

The primary held-out instance is `fe4s4-prefix-0244`, with 59,536 configurations. Its balanced-view CPU16 median is `78.40097830099694 s`; its L4 GPU median and feasible-oracle time are `17.261023300001398 s`.

| Policy | Correct | Within 5% | GM selected/oracle | GM oracle/selected | Median regret | P90 regret | Maximum regret | GM speedup vs CPU | GM speedup vs GPU | Invalid/failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed CPU16 | 0/1 | 0/1 | 4.542081714297355 | 0.2201633662494988 | 3.542081714297355 | 3.542081714297355 | 3.542081714297355 | 1.0 | 0.2201633662494988 | 0/0 |
| Fixed L4 GPU | 1/1 | 1/1 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 4.542081714297355 | 1.0 | 0/0 |
| Static threshold | 1/1 | 1/1 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 4.542081714297355 | 1.0 | 0/0 |
| Size-only tree | 1/1 | 1/1 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 4.542081714297355 | 1.0 | 0/0 |
| Full-feature tree | 1/1 | 1/1 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 4.542081714297355 | 1.0 | 0/0 |
| Feasible oracle | 1/1 | 1/1 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 4.542081714297355 | 1.0 | 0/0 |

This one held-out point establishes that the learned policies and the training-only threshold choose the correct backend for the largest nested variant. It does not establish performance on a held-out chemical family.

## Corrected leave-one-instance-out sensitivity

| Policy | Correct | Within 5% | GM selected/oracle | GM oracle/selected | Median regret | P90 regret | Maximum regret | GM speedup vs CPU | GM speedup vs GPU | Invalid/failures |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed CPU16 | 1/5 | 1/5 | 2.0779687720600366 | 0.4812391858077009 | 0.9834842404051707 | 3.0910759721114305 | 3.542081714297355 | 1.0 | 0.4955664118022451 | 0/0 |
| Fixed L4 GPU | 4/5 | 4/5 | 1.0297715282069095 | 0.9710891907656941 | 0.0 | 0.09479334569411678 | 0.15798890949019462 | 2.0178930132961637 | 1.0 | 0/0 |
| Static threshold | 3/5 | 3/5 | 1.078390418002942 | 0.9273079427503517 | 0.0 | 0.21885646500174283 | 0.25943483534277495 | 1.9269169471184666 | 0.954915317324435 | 0/0 |
| Size-only tree | 4/5 | 4/5 | 1.0472132783479557 | 0.954915317324435 | 0.0 | 0.155660901205665 | 0.25943483534277495 | 1.9842842093619764 | 0.9833446056293694 | 0/0 |
| Full-feature tree | 4/5 | 4/5 | 1.0472132783479557 | 0.954915317324435 | 0.0 | 0.155660901205665 | 0.25943483534277495 | 1.9842842093619764 | 0.9833446056293694 | 0/0 |
| Feasible oracle | 5/5 | 5/5 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 2.0779687720600366 | 1.0297715282069095 | 0/0 |

The threshold result is the corrected 3/5 value. A superseded preliminary run incorrectly reported 5/5 because it used observed sizes as implicit boundaries instead of the registered midpoint/sentinel protocol.

## Per-instance sensitivity decisions

`C` denotes `amd-cpu-16`; `G` denotes `amd-l4-default`. Times are balanced-view medians from repetitions 0–2. Each row is the test prediction from the fold that excludes that entire instance from training.

| Held-out instance | Configurations | CPU median (s) | GPU median (s) | Fixed CPU | Fixed GPU | Threshold | Size tree | Full tree | Oracle |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `fe4s4-prefix-0032` | 1,024 | 1.4109253030037507 | 1.6338358529974357 | C | G | G | C | C | C |
| `fe4s4-prefix-0055` | 3,025 | 2.41789160999906 | 1.9198227190063335 | C | G | C | C | C | G |
| `fe4s4-prefix-0100` | 10,000 | 5.633911507997254 | 2.8404115309967892 | C | G | G | G | G | G |
| `fe4s4-prefix-0174` | 30,276 | 29.969004751001194 | 8.776808773000084 | C | G | G | G | G | G |
| `fe4s4-prefix-0244` | 59,536 | 78.40097830099694 | 17.261023300001398 | C | G | G | G | G | G |

The threshold misses 1,024 with normalized regret `0.15798890949019462` and 3,025 with regret `0.25943483534277495`. Both trees miss only 3,025, with regret `0.25943483534277495`. Every decision is memory-feasible and valid; there are zero invalid selections and zero execution/correctness failures in both the primary and sensitivity views.

## Primary tree structures and ablation finding

Both trees are `sklearn.tree.DecisionTreeRegressor` models from scikit-learn 1.7.1 with fixed `max_depth=2`, `min_samples_leaf=1`, and `random_state=1729`. Each primary model trains on eight candidate rows from four instances.

The size-only tree has seven nodes, four leaves, and actual depth two:

| Node | Type | Feature/rule | Left/right | Samples or leaf value |
|---:|---|---|---|---|
| 0 | Split | `log1p_n_configurations <= 9.764292240142822` | 1 / 4 | 8 samples |
| 1 | Split | `log1p_n_configurations <= 8.61271858215332` | 2 / 3 | 6 samples |
| 2 | Leaf | — | — | `1.0372496685631867` |
| 3 | Leaf | — | — | `1.618887065830696` |
| 4 | Split | `backend_gpu <= 0.5` | 5 / 6 | 2 samples |
| 5 | Leaf | — | — | `3.4329868575630655` |
| 6 | Leaf | — | — | `2.280013129469629` |

The full-feature tree also has seven nodes, four leaves, and actual depth two:

| Node | Type | Feature/rule | Left/right | Samples or leaf value |
|---:|---|---|---|---|
| 0 | Split | `beta_single_edge_density <= 0.23863771557807922` | 1 / 4 | 8 samples |
| 1 | Split | `cpu_threads <= 8.5` | 2 / 3 | 2 samples |
| 2 | Leaf | — | — | `2.280013129469629` |
| 3 | Leaf | — | — | `3.4329868575630655` |
| 4 | Split | `beta_double_edge_density <= 0.5909090787172318` | 5 / 6 | 6 samples |
| 5 | Leaf | — | — | `1.0372496685631867` |
| 6 | Leaf | — | — | `1.618887065830696` |

Leaf values are predicted `log1p(median end-to-end wall time in seconds)`. The full and size-only trees make identical primary and sensitivity decisions and have identical aggregate metrics. Therefore, the richer pre-execution feature set shows no measured advantage over size plus backend on this dataset. Because these are nested variants of one family, correlated connectivity features may act as size proxies; the selected full-tree splits are not evidence of a transferable causal mechanism.

## Inference overhead

The primary overhead is hot selection with an already loaded deployment full tree. It includes pre-execution feature-vector construction, memory-feasibility filtering, both candidate predictions, and deterministic argmin. The secondary diagnostic reads and strictly deserializes the complete saved `models.json`, retrieves the deployment tree, and performs the same selection. Both use `time.perf_counter_ns()` and consume every selected candidate.

| Measurement | Warm-up | Measured | Minimum (µs) | Median (µs) | P90 (µs) | P95 (µs) | Maximum (µs) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Hot selection | 1,000 | 10,000 | 37.701 | 38.65 | 42.667300000000004 | 48.71309999999999 | 214.577 |
| Load plus selection | 10 | 100 | 909.477 | 929.1099999999999 | 936.1551000000001 | 939.67855 | 948.61 |

The shortest measured SBD candidate median in the balanced dataset is CPU16 on `fe4s4-prefix-0032`, `1.4109253030037507 s`. The hot median is `0.002739337080263366%` of that runtime. Hot selections were consumed as 6,000 CPU and 4,000 GPU results, with checksum `bb968d15ea964a8d16916f4419484bdd436dc2efc83465b1bf1f86623d3d2cd8`; load-plus-selection consumed 60 CPU and 40 GPU results, with checksum `2c7771b0aeabcd435b3742cc0fcca7d76d7644160db1b0e17642d154f89ae3e8`.

The load-plus-selection number is an object-cold diagnostic, not a storage-cache-cold result: file I/O is included, but OS page-cache state was not controlled. The overhead run took 1.53 seconds, reached 114,560 KiB maximum RSS, and used no GPU. The L4 remained idle before and after.

Overhead evidence is bound by run ID `50b9351e5d3ab74fdb71a8915acdcd682891d736b58db1e86ef64d400c2fb6b4`. Its immutable raw record is `results/raw/inference_overhead/50b9351e5d3ab74fdb71a8915acdcd682891d736b58db1e86ef64d400c2fb6b4.json`, 155,300 bytes, SHA-256 `ea293deabbd2c904e1b432a88075c750db9ef7eb595d58d8a45fc452e1c4d356`.

## Corrected Stage 5 artifact inventory

The Stage 5 config is `configs/stage5_size_heldout.yaml`, SHA-256 `21ad73381a156d424cd762a18a2fb3b897e074824665d96d6e631837021eb0f1`. The final corrected artifacts are:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `results/processed/stage5/balanced_dataset.json` | 22,825 | `7c71c1abdab856b066dbe9e1652cbf1e696e2c1e798fb11ac66326c8cbce90d3` |
| `results/processed/stage5/evaluation.json` | 344,894 | `9b2f163e6267f2ec3b3eb2c04f76405ca96c30f16dcfbf1c789a1173cb1e3b6e` |
| `results/processed/stage5/models.json` | 108,238 | `85f8a84e1d40163b9971ba8d9d9fab47dd049adf036b95c5f0b8f6c11884eb1c` |
| `results/processed/stage5/split_manifest.json` | 18,983 | `86499f6504a2924445067780b5804d543d193d98d9a875a28d87f94871675aaa` |
| `results/processed/stage5/policy_predictions.csv` | 29,850 | `f8ed3cd3030542788e63db03aca9e4b7448f812a691148a15aecab5fff4f4095` |
| `results/processed/stage5/policy_summary.csv` | 2,290 | `91f1e99a272271755b7c9ccb07f20b70ed42affc3bac3ceb4214d192e1df820e` |
| `results/processed/stage5/policy_summary.json` | 9,791 | `7bfff41c644886884b6524d64a16e41df542b79a7767484a28c94474d1ddd9c0` |
| `results/processed/stage5/selector_ablation.csv` | 1,388 | `32d4cf826714a16cc053fed9c7347884e81321ed14b4917d2cf29426a01cae78` |
| `results/processed/stage5/inference_overhead.json` | 5,345 | `ddb33f39682d5c1318c3e2d65560bb8e9232309cc522324670565c928cee10cf` |
| `results/processed/stage5/inference_overhead.csv` | 1,079 | `678b45509c1733ffd4d22541496be2644c77fbc81b922e8ba13c877982104fbc` |

## Defect and supersession record

Phase A found and fixed four evaluator/artifact defects:

1. The first wrapper invocation requested nonexistent `split_id` fields rather than the core split `name`. It failed before writing any artifact; the wrapper now uses `split.name`.
2. The preliminary threshold implementation tried `min(size)-1` plus observed sizes, despite the YAML registering geometric midpoints plus unconditional candidates. It now uses explicit `kind` values, exact adjacent midpoints, and JSON-null sentinel thresholds.
3. `upstream_default` duplicated `fixed_gpu` as a seventh prediction/metric row. It is now provenance-only; all comparison artifacts contain six unique policies.
4. Three summary columns were initially null because artifact-field names did not match the evaluator's metric keys. The mappings were corrected, typed non-null validation was added, and all 12 final summary rows contain complete values.

All hashes from the behaviorally incorrect preliminary artifact set are superseded and must not be cited as Stage 5 evidence. The first failed schema-wrapper attempt produced no partial files. The hashes in this audit are from the corrected, twice-regenerated evaluator output; the second identical evaluator invocation reported every deterministic artifact unchanged. The corrected complete test suite passed 123/123 tests, including focused threshold, alias, config-mutation, non-null-summary, and overhead-invariant coverage.

## Limitations and allowed interpretation

- This is one heterogeneous GCP node with one NVIDIA L4, not a multi-node, leadership-scale, or exascale system.
- The five instances are nested determinant prefixes of one authentic Fe₄S₄ workload. They span configuration count but are not five independent chemical families.
- The primary result contains one held-out largest-size instance. Its zero-regret learned decisions are exact for that instance but statistically narrow.
- Leave-one-instance-out results are small-sample sensitivity evidence. They are not independent-family validation.
- All learned policies use the same 30-measurement balanced view. Model selection, thresholds, and preprocessing remain training-only within each fold, but the evidence volume is small.
- The full-feature tree does not outperform the size-only tree. No claim of a feature-rich advantage is supported by this Phase A result.
- The static threshold does not dominate the fixed GPU or trees in corrected sensitivity; its 3/5 accuracy and nonzero regret must be retained rather than cherry-picked away.
- Overhead timing is node- and software-environment-specific. The load-plus-selection diagnostic does not control the OS page cache.
- Phase B may add authentic N₂/H₂O data only if the same exact official AMD executables accept the inputs and identical-input correctness passes. No result here authorizes switching to or timing the RIKEN solver.

## Reproduction and verification commands

Run the deterministic evaluator from the repository root:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_tuner.py \
  --config configs/stage5_size_heldout.yaml \
  --output-dir results/processed/stage5
```

An immediate identical invocation should report `changed=false` for all eight non-overhead artifacts.

Run the bounded overhead path with its recorded defaults:

```bash
PYTHONPATH=src .venv/bin/python scripts/measure_inference_overhead.py
```

Overhead samples are machine-state-sensitive; verify the GPU is idle and record host load before running. The immutable raw record and processed summary bind the exact model/dataset hashes and protocol.

Run the complete unit suite and verify artifact hashes:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
sha256sum reports/stage4_protocol.json \
  reports/stage4_completion.json \
  results/processed/stage4_final.json \
  configs/stage5_size_heldout.yaml \
  results/processed/stage5/* \
  results/raw/inference_overhead/*.json
```

Inspect exact policy rows, splits, and models without recomputation:

```bash
jq '.rows' results/processed/stage5/policy_summary.json
jq '{leakage_check, primary, secondary_leave_one_instance_out}' \
  results/processed/stage5/split_manifest.json
jq '{primary, deployment_models}' results/processed/stage5/models.json
jq '.' results/processed/stage5/inference_overhead.json
```

## Student handoff boundary

The student should use the repository artifacts and this audit to inspect, reproduce, and defend the work. The student must independently decide what claims are appropriate and write all submission material. No language in this internal report should be copied automatically into an abstract, 800-word summary, poster, or other student-owned deliverable.
