# AutoSBD SC26 Completion Handoff v2

Repository: `NagaSaiDhirajK/autosbd-sc26-rg`  
Prepared: August 1, 2026  
Submission deadline: August 8, 2026  

## How to use this handoff

Open the remote repository root `~/autosbd-sc26-rg` in VS Code, start a new Codex workspace chat, enter `/plan`, and paste the complete **Codex execution prompt** below. The prompt is designed to continue from the existing repository rather than rebuild it.

Do not paste only the figure list. The scientific fixes, dataset expansion, evaluator repair, and figures must be completed in that order.

---

# Codex execution prompt

Continue the existing AutoSBD SC26 project in the currently open repository. Read `AGENTS.md`, `PROJECT_CONTEXT.md`, `README.md`, `reports/RESULTS.md`, `reports/LIMITATIONS.md`, `reports/DECISIONS.md`, and all Stage 4/5 code and configurations before changing anything. Preserve existing immutable raw measurements and all user changes.

## 1. Current verified repository state

Do not repeat completed work unless a verification fails.

The primary upstream is the unmodified official `AMD-HPC/amd-sbd` `sc26-artifacts` commit:

```text
729cfa3a5011fb805eb9e686a7711f6919836dcb
```

Both CPU16 and NVIDIA L4 executables were built from that commit with NVIDIA HPC SDK 26.5. The Stage 4 repeated campaign is complete, despite stale documentation saying otherwise.

Verified Stage 4 evidence:

- 48 immutable runs;
- 10 warm-ups;
- 38 timing-eligible measurements;
- five nested Fe₄S₄ determinant-prefix sizes;
- CPU/GPU numerical agreement;
- no OOM, timeout, or correctness failure;
- CPU16 wins at 1,024 configurations;
- L4 wins at 3,025, 10,000, 30,276, and 59,536 configurations.

Median timings:

| Configurations | CPU16 median | L4 median | CPU/GPU | Winner |
|---:|---:|---:|---:|---|
| 1,024 | 1.411 s | 1.629 s | 0.866 | CPU16 |
| 3,025 | 2.416 s | 1.921 s | 1.258 | L4 |
| 10,000 | 5.634 s | 2.840 s | 1.983 | L4 |
| 30,276 | 29.969 s | 8.777 s | 3.415 | L4 |
| 59,536 | 78.401 s | 17.261 s | 4.542 | L4 |

Stage 5 evaluator code exists, but generated evaluation artifacts are absent from the committed repository. The current evaluator reduces 30 measured records to 10 candidate medians and trains each largest-size-holdout fold on only eight rows. It is a valid preliminary size-extrapolation test, not comprehensive training.

The current figure pipeline generates only two SVGs: CPU/GPU crossover and GPU memory guard. It must be expanded substantially, but only with traceable data.

## 2. Required communication protocol

Before every command or edit batch, report:

```text
WORK BLOCK
Goal:
Scientific/engineering reason:
Exact commands or files to edit:
Expected duration:
Expected CPU/GPU/RAM/disk and cloud-cost impact:
Evidence expected:
Approval required: yes/no
```

After every batch, report:

```text
RESULT
Exit status:
Evidence observed:
Files changed:
Tests/checks:
Runtime/resource use:
Scientific interpretation:
Uncertainty or limitation:
Next action:
```

Append exact commands and outcomes to `reports/COMMAND_LOG.md`, experimental decisions to `reports/EXPERIMENT_LOG.md`, and consequential scope/claim decisions to `reports/DECISIONS.md`. Save verbose logs under `logs/`.

Never silently launch a sweep. Obtain approval before any sweep expected to exceed 30 minutes or USD 1, any dataset/tool download over 500 MiB, or any new compiler/toolchain installation.

## 3. Phase A — finish and audit the existing Stage 5 immediately

### A1. Run the frozen evaluator

First verify the worktree, environment, source hashes, and Stage 4 completion claims. Then run:

```bash
cd ~/autosbd-sc26-rg
PYTHONPATH=src .venv/bin/python scripts/evaluate_tuner.py \
  --config configs/stage5_size_heldout.yaml \
  --output-dir results/processed/stage5
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

Inspect rather than merely list:

- `evaluation.json`;
- `balanced_dataset.json`;
- `models.json`;
- `split_manifest.json`;
- `policy_summary.json` and `.csv`;
- `policy_predictions.csv`;
- `selector_ablation.csv`.

Create `reports/STAGE5_PRELIMINARY_AUDIT.md` containing factual internal evidence:

- learned full-tree and size-only-tree nodes;
- primary largest-size holdout result;
- five leave-one-instance-out folds;
- choices for every policy;
- normalized regret and speedups;
- whether full features improve over size-only;
- whether either tree improves over the static threshold;
- all invalid/failure counts;
- precise sample counts after median aggregation.

Do not call this cross-family evidence.

### A2. Fix inference-overhead evaluation

The Stage 5 YAML promises `inference_overhead`, but the evaluator does not measure it. Implement two separately reported measurements:

1. **hot selection latency:** feature transformation, feasibility filtering, candidate prediction, and argmin with an already loaded model;
2. **cold load plus selection latency:** deserialize/load the saved model and perform one selection.

Requirements:

- use `time.perf_counter_ns()`;
- warm up before measurement;
- hot path: at least 10,000 measured iterations, or enough for stable timing under two seconds;
- cold path: at least 100 iterations if file I/O is included;
- consume/check selected candidates so the loop is not vacuous;
- report median, p90, p95, minimum, maximum, and iteration count in microseconds;
- compare hot inference time with the shortest measured SBD runtime as a percentage;
- write `inference_overhead.json` and `.csv`;
- add deterministic tests by testing structure/invariants, not exact wall-clock values.

If reliable cold-load timing is unnecessary for the deployment model, retain it as a secondary diagnostic and make hot selection the primary overhead.

### A3. Align the static-threshold protocol

The YAML registers geometric midpoints plus always-CPU/always-GPU candidates, while the implementation currently tries `min(size)-1` plus observed sizes. Make registration and implementation exactly match.

Preferred representation:

```text
always_gpu
geometric midpoint between each adjacent unique training size
always_cpu
```

Represent sentinel policies with explicit `kind` values and JSON `null` thresholds, not non-finite numbers. The selection rule remains CPU at or below a finite midpoint and GPU above it. Add tests that verify training-only fitting, exact candidates, deterministic tie breaking, and behavior on unseen sizes.

### A4. Remove the false extra baseline

`upstream_default` is currently an alias of `fixed_gpu`. Keep the alias in provenance if useful, but do not count or plot it as an independent baseline. Primary policy comparisons must be:

- fixed CPU16;
- fixed L4 GPU;
- training-only static size threshold;
- size-only tree;
- AutoSBD full-feature tree;
- measured feasible oracle.

### A5. Repair stale documents

Update the following after Stage 5 preliminary outputs exist:

- `README.md`;
- `PROJECT_CONTEXT.md`;
- `reports/RESULTS.md`;
- `reports/LIMITATIONS.md`;
- test counts and current-stage status;
- evidence map and reproduction commands.

State that Stage 4 is complete. State exact Stage 5 results rather than saying only that implementation exists. Keep the one-family limitation explicit until Phase B finishes.

### Phase A exit gate

Do not proceed to a new benchmark campaign until:

- Stage 5 preliminary artifacts exist and validate;
- inference overhead exists;
- threshold protocol matches the YAML;
- baseline alias is not double-counted;
- tests pass;
- stale documentation is corrected.

Commit locally only after reviewing the diff. Do not push without user approval.

## 4. Phase B — add two independent authentic chemistry families

This is the highest-value scientific improvement.

The pinned `r-ccs-cms/sbd` `v1.3.0` repository contains authentic inputs that use the same SBD tensor-product-basis FCIDUMP and half-determinant concepts:

1. `data/n2`: N₂ in the 6-31G basis. Its upstream README reports a 239-half-determinant `1e-3` case with 57,121 product configurations and a PySCF-generated FCIDUMP/reference context.
2. `data/h2o`: H₂O in the cc-pVDZ basis. Its upstream README reports a 275-half-determinant `1e-3` case with 75,625 product configurations and a PySCF-generated FCIDUMP/reference context.

Source:

```text
https://github.com/r-ccs-cms/sbd/tree/v1.3.0/data/n2
https://github.com/r-ccs-cms/sbd/tree/v1.3.0/data/h2o
```

Do not assume filenames from this handoff. Discover and verify them in the exact pinned checkout.

### B1. Provenance and compatibility gate

Before copying/generating anything:

1. verify the retained RIKEN checkout is exactly `v1.3.0` and record its commit SHA;
2. record Apache-2.0 license and source URLs;
3. inventory exact N₂/H₂O FCIDUMP and determinant files with sizes and SHA-256 hashes;
4. compare their format with the Fe₄S₄ input accepted by the pinned AMD executable;
5. run the smallest full upstream N₂/H₂O input on CPU and GPU under correctness-only status;
6. require convergence plus CPU/GPU energy, residual, iteration, and density agreement using existing project criteria;
7. do not use any timing until the validation manifest covers those exact input hashes.

If the exact AMD binary cannot accept these formats without source modification, stop and report the incompatibility. Do not silently switch solvers, because cross-family timing must remain on the same implementation.

### B2. Derived size grid

For each family, generate deterministic nested prefixes from the smallest official determinant list. Target half-determinant counts:

```text
32, 55, 100, 174, full official count
```

This gives approximately:

```text
1,024; 3,025; 10,000; 30,276; and 57,121–75,625 configurations
```

For every derived file record:

- family (`fe4s4`, `n2`, `h2o`);
- molecule and basis;
- parent file path/SHA;
- prefix rule and half-determinant count;
- output SHA;
- FCIDUMP SHA;
- electron/orbital counts;
- expected product configurations;
- license/source citation.

Use the existing immutable workload preparation style. Add `family_id` as a required pre-execution field throughout config validation, raw records, aggregates, evaluation datasets, and figure trace tables.

The derived prefixes are workload-size variants, not independently certified chemistry solutions. CPU/GPU agreement is the correctness criterion for prefixes. For the full official smallest list, record upstream reference energy only as contextual evidence, not an independent guarantee unless the exact solver settings match.

### B3. Pilot and timing protocol

For N₂ and H₂O:

1. correctness-only CPU/GPU pair at all five sizes;
2. one warm-up per candidate/size;
3. one measured pilot repetition to verify runtime and crossover coverage;
4. three measured repetitions broadly;
5. five measured repetitions only near a family-specific winner flip or headline case;
6. sequential execution under the existing node lock;
7. same CPU affinity and same AMD build as Fe₄S₄;
8. randomized candidate order within workload blocks;
9. preserve all skips/failures.

Before launching, estimate total runtime and cloud cost from the pilot. Stop for approval.

Do not rerun completed Fe₄S₄ Stage 4 evidence unless the new schema absolutely requires it. Prefer a deterministic migration/augmentation layer that adds `family_id=fe4s4` while preserving source record identities and hashes.

### Phase B exit gate

Proceed only if all three families have:

- the same AMD CPU/GPU executable provenance;
- exact input provenance;
- correctness manifests;
- at least three timing-eligible repetitions for each retained candidate/size;
- no unexplained parser/convergence difference.

## 5. Phase C — modest configuration-space expansion

Independent families are more important than many weakly tested knobs. Add only parameters truly exposed by the pinned AMD executable and documented by its exact app README/source.

Candidate axes to investigate, in order:

1. backend: CPU16 versus L4;
2. shuffle: `0` versus `1`;
3. `bit_length`: default 20 versus a valid structure-matched value derived from the exact representation;
4. one cache mode only if a real, documented runtime/compile control exists;
5. no MPI decomposition expansion unless time remains after multi-family evaluation.

### C1. Parameter validity

For `bit_length`, inspect the pinned source to determine whether it describes alpha/beta half strings, interleaved full strings, or both. Do not assume that the value equals spatial orbitals or spin orbitals. Add unit tests for representation size and accepted values.

### C2. Pruning experiment

Use one small, one crossover, and one large case per family with one repetition for all valid parameter combinations. Prune a configuration only when it is:

- invalid;
- consistently dominated within its backend;
- scientifically redundant; or
- too memory-expensive for the final budget.

Record pruning in `reports/CONFIGURATION_PRUNING.md`. Retain at most four final candidates unless evidence strongly justifies more. A realistic set could contain the best CPU policy and two or three GPU representation/load-balance policies.

If shuffle and `bit_length` have the same winner for every family/size, retain the dominant values and keep the final research claim as cross-family CPU/GPU selection. Do not imply tuning complexity that the data does not show.

## 6. Phase D — Stage 5 v2 cross-family evaluator

Create a new versioned configuration rather than overwriting the preliminary Fe₄S₄ evaluation:

```text
configs/stage5_multifamily.yaml
results/processed/stage5_multifamily/
```

### D1. Dataset contract

Each median candidate row must contain:

- `family_id`;
- problem instance and input SHA;
- molecule/basis metadata;
- size and structural features;
- candidate/backend/parameter features;
- median end-to-end runtime and source record IDs;
- memory estimates/caps;
- correctness/eligibility assertions.

No family identity, molecule name, input hash, or post-execution telemetry may be used as a predictor. They are grouping/provenance fields only.

### D2. Primary split

Use leave-one-chemistry-family-out evaluation:

```text
fold 1: train N2 + H2O, test Fe4S4
fold 2: train Fe4S4 + H2O, test N2
fold 3: train Fe4S4 + N2, test H2O
```

All sizes, candidates, and repetitions of the held-out family remain exclusively in the test fold. The primary metrics aggregate predictions across the three held-out families.

Secondary evaluations:

- largest-size-within-each-family holdout;
- leave-one-instance-out sensitivity;
- per-family performance breakdown.

### D3. Models and baselines

Use fixed, preregistered small models:

- full-feature `DecisionTreeRegressor`, suggested `max_depth=3`, `min_samples_leaf=2` if training-row count supports it;
- size/backend-only tree ablation;
- optional random forest only as secondary sensitivity, never the headline if interpretability is lost.

No held-out hyperparameter tuning. Freeze model parameters before inspecting test results.

Compare:

- fixed CPU16;
- fixed GPU/default best retained GPU config;
- static threshold fitted on training families only;
- size-only tree;
- AutoSBD full-feature tree;
- measured feasible oracle.

If multiple retained GPU configurations exist, define fixed GPU as one preregistered default rather than the best test-time GPU.

### D4. Required metrics

Produce globally and per held-out family:

- geometric-mean selected/oracle runtime;
- geometric-mean speedup versus fixed CPU and fixed GPU;
- median, p90, and maximum normalized regret;
- exact-selection accuracy;
- within-5%-of-oracle rate;
- invalid/OOM/failure/correctness-failure rates;
- hot and cold inference overhead;
- full-tree versus size-only ablation;
- bootstrap confidence intervals across independent problem instances when statistically meaningful.

Do not bootstrap individual repetitions as though independent. Resample at the family or problem-instance level and label small-sample intervals cautiously.

### D5. Evidence-based claim gate

The strongest allowed claim depends on results:

1. If all family-held-out folds are valid and AutoSBD beats fixed policies with low regret:

   > AutoSBD is an interpretable, structure-aware CPU–GPU runtime selector evaluated through leave-one-chemistry-family-out testing on three authentic SBD workload families.

2. If full features beat size-only/static threshold consistently:

   > Pre-execution structural features improve cross-family selection beyond problem size alone.

3. If configuration knobs show instance-dependent winners:

   > AutoSBD selects both backend and a modest set of representation/load-balance configurations.

4. If the full tree does not beat size-only:

   > The study demonstrates cross-family CPU/GPU crossover selection but does not establish added benefit from structural features.

Never claim universal SBD tuning, multi-node scaling, or proven memory-failure avoidance unless directly tested.

## 7. Phase E — comprehensive deterministic figure system

The user wants numerous professional and technically rich figures. Generate a broad **internal scientific figure catalog**, then select only the clearest figures for the student-authored poster. Complexity must come from multi-dimensional evidence, traceability, and careful composition—not decorative 3D effects or chart clutter.

### E1. Figure infrastructure

Create or extend:

```text
scripts/make_all_figures.py
src/autosbd/figure_registry.py
src/autosbd/figure_data.py
src/autosbd/figure_renderers.py
configs/figures.yaml
figures/main/
figures/supplemental/
figures/diagnostic/
tables/figures/
reports/FIGURE_CATALOG.md
reports/figure_manifest.json
```

Every figure must have:

- stable figure ID and descriptive filename;
- SVG and PDF vector output;
- 300-DPI PNG preview;
- one companion CSV or strict JSON table containing plotted values;
- source artifact paths and SHA-256 hashes;
- generator Git commit and configuration hash;
- explicit inclusion/exclusion rules;
- short internal factual caption;
- limitations/interpretation note;
- deterministic output where practical.

Never fabricate a figure when source data is missing. Mark it `blocked_missing_data` in the catalog and state exactly what experiment would unlock it.

Use a consistent accessible design system:

```text
CPU              #0072B2  blue
GPU              #D55E00  vermillion
AutoSBD          #009E73  green
Size-only        #E69F00  orange
Static threshold #56B4E9  sky blue
Oracle           #CC79A7  purple
Neutral          #666666
```

Use DejaVu Sans or another guaranteed embeddable font. Main single-panel size approximately 7.2×4.6 inches; composite plate approximately 14.4×8.5 inches. Use consistent line widths, marker shapes in addition to colors, units, panel labels `(a)`, `(b)`, etc., and readable text at final poster scale.

Avoid:

- 3D bars/surfaces when two-dimensional encodings suffice;
- pie/donut charts;
- radar charts;
- dual y-axes unless there is no defensible alternative;
- smoothing or interpolation across unmeasured points;
- unlabeled logarithmic axes;
- error bars that mix repetitions with independent instances;
- presenting profiled runs as timing evidence.

### E2. Required main scientific figures

Generate these as individual outputs and also as selected multi-panel composite plates.

#### F01 — AutoSBD end-to-end architecture

Professional vector schematic:

```text
SBD input + FCIDUMP
  -> pre-execution structural features
  -> deterministic memory/validity filter
  -> runtime predictions for each candidate
  -> selected CPU/GPU/configuration
  -> SBD execution
  -> immutable evidence record
```

Show the separation between upstream SBD and the original AutoSBD layer. Include training path from benchmark database to runtime model and deployment path without post-execution features.

#### F02 — Experimental provenance and evidence DAG

Multi-level directed graph from upstream commits and input hashes through derived prefixes, correctness manifests, raw records, aggregates, evaluation splits, tables, and final figures. Annotate immutable/hash-checked boundaries.

#### F03 — Cross-family CPU/GPU runtime scaling

Faceted log-log plot with Fe₄S₄, N₂, and H₂O panels. Show raw measured repetitions faintly, medians prominently, IQR bars, CPU/GPU curves, and observed winner-flip brackets without fitted smoothing.

#### F04 — CPU/GPU speedup and crossover landscape

Two panels:

- CPU16/GPU median runtime ratio versus configurations for each family;
- winner map with family on y-axis, workload size on x-axis, color/marker indicating oracle candidate and numeric speedup.

Include horizontal parity line at 1.

#### F05 — Held-out policy performance

Grouped dot/bar plot of normalized runtime for fixed CPU, fixed GPU, static threshold, size-only tree, AutoSBD, and oracle. Show global family-held-out aggregate plus each held-out family. Include uncertainty only at independent-instance level.

#### F06 — Policy regret distribution

Raincloud/strip-and-box or ECDF plot of normalized regret across held-out instances, with individual points retained. Add p50/p90 annotations. Do not use a violin alone with so few samples.

#### F07 — Interpretable model and decision logic

Composite:

- exported shallow decision tree with thresholds/leaf runtime;
- simplified decision regions over configurations and one dominant structural feature;
- per-leaf training/test sample counts.

If the tree changes by fold, show a consensus/stability table rather than pretending one fold's tree is universal.

#### F08 — Structural-feature ablation

Compare full tree, size-only tree, and static threshold on regret and speedup. Add feature permutation/importance only on training folds and clearly label limitations of tree impurity importance.

### E3. Runtime and scaling figures

#### F09 — Per-family runtime small multiples

One panel per family with CPU/GPU medians, raw repetitions, and crossover annotations.

#### F10 — Runtime variability

Coefficient of variation/IQR divided by median by backend, family, and size. This supports measurement stability.

#### F11 — Empirical scaling slope

Local secant slopes between adjacent measured sizes for CPU and GPU, by family. Do not fit one global exponent unless diagnostics justify it.

#### F12 — End-to-end versus solver time

Stacked or paired plot of solver-reported time and wrapper/initialization overhead by backend/size/family. Never infer transfer time by subtraction unless fields support it.

#### F13 — Absolute and relative speedup matrix

Heatmap/table with median CPU time, GPU time, absolute seconds saved, CPU/GPU ratio, and winner for every family/size.

#### F14 — CPU thread-scaling pilot

CPU1/4/8/16 runtime and parallel efficiency for available pilot sizes. Label it pilot/pruning evidence, not final general scaling.

### E4. Tuner figures

#### F15 — Measured versus predicted runtime

Log-log parity plot with out-of-fold predictions only, colored by backend/configuration and shaped by held-out family. Show parity and ×2 bands.

#### F16 — Prediction residual diagnostics

Residual versus predicted runtime and residual versus size, using only held-out predictions. Identify systematic extrapolation errors.

#### F17 — Selection matrix

Grid of family × size showing oracle, AutoSBD choice, size-only choice, and static-threshold choice, with mismatches outlined.

#### F18 — Fold-by-fold generalization

Three-panel leave-one-family-out summary: regret, speedup, and accuracy/within-5% rate per held-out family.

#### F19 — Model stability

Heatmap/table of features and split thresholds used across folds, plus selected candidate stability. Do not imply statistical significance from only three folds.

#### F20 — Inference overhead

Hot selection and cold load-plus-selection latency distributions in microseconds, with an inset showing overhead as a percentage of the smallest SBD runtime.

#### F21 — Learning-curve sensitivity

Only if multi-family data exists: train on increasing numbers of grouped problem instances, evaluate on untouched grouped instances, repeat over deterministic group subsets. Label as sensitivity, not a population learning curve.

### E5. Configuration and feature figures

#### F22 — Workload structural fingerprint heatmap

Z-scored pre-execution features by family/size with hierarchical clustering only as a descriptive ordering. Include raw-value companion table.

#### F23 — Feature correlation and collinearity

Spearman correlation heatmap plus a compact table of near-collinear pairs. Explicitly show why the original Fe₄S₄-only features could not establish structure beyond size.

#### F24 — Dataset coverage map

Family, basis, orbitals/electrons, determinant count, work proxy, cache estimate, and measured candidate coverage. Use a bubble/heatmap matrix rather than a decorative map.

#### F25 — `bit_length` sensitivity

If tested: normalized runtime and representation/cache bytes versus valid `bit_length`, faceted by backend/family/size.

#### F26 — Shuffle sensitivity

If tested: paired runtime ratios for shuffle off/on across matched trials, separated by CPU/GPU and family.

#### F27 — Configuration winner map

If more than two candidates survive: family × size grid showing the oracle backend/configuration and margin to second best.

#### F28 — Configuration-pruning Pareto plot

Runtime versus memory/feasibility for pilot candidates, showing dominated and retained choices. Only use comparable matched inputs.

### E6. Correctness, resources, and reproducibility figures

#### F29 — Numerical parity

CPU versus GPU final energy/residual parity, plus absolute/relative difference by family/size. Use scientific notation and acceptance thresholds.

#### F30 — Davidson convergence diagnostics

If iteration history is logged: residual norm versus iteration for representative small/crossover/large cases on CPU and GPU. If only final residual exists, do not invent curves; render a final-residual panel instead.

#### F31 — GPU memory guard

Extend the existing figure across all families: measured peak, known estimate, padded guard, and admission cap. State that the boundary was not reached unless new evidence changes this.

#### F32 — GPU telemetry timeline

For representative small/crossover/large unprofiled runs, show utilization, memory, power, and temperature versus time in aligned panels. Do not mix samples from different clocks without normalization.

#### F33 — Host-resource timeline

Representative CPU and GPU runs: process RSS and aggregate CPU utilization versus time. Explain sampling limitations.

#### F34 — Run eligibility and outcome flow

Flow diagram from all attempted runs through warm-up/measured, process success, correctness, monitoring, timing eligibility, and final inclusion. Include exact counts and no fake Sankey widths if not supported.

#### F35 — Benchmark campaign timeline

Chronological plot of trials by family, candidate, phase, duration, and status. Useful for proving sequential execution and absence of overlap.

#### F36 — Claim-to-evidence matrix

Matrix connecting each allowed claim to source experiments, artifact hashes, figures, and limitations. Use check/partial/not-supported states.

### E7. Composite plates

In addition to F01–F36, produce these professional composite layouts:

- `P01_system_and_method`: F01 + F02 + dataset summary;
- `P02_performance`: F03 + F04 + F13;
- `P03_autotuner`: F05 + F06 + F07 + F08;
- `P04_generalization`: F15 + F16 + F17 + F18;
- `P05_structure_and_config`: F22 + F23 + F25/F26/F27 as available;
- `P06_correctness_and_resources`: F29 + F31 + F32 + F34.

The student will choose approximately five to eight clear figures/panels for the actual poster. Do not cram all outputs onto the poster.

### E8. Figure QA

Automated tests/checks must verify:

- expected source record counts and SHA claims;
- no pilot/profiled/ineligible run enters final timing figures;
- every plotted median maps to exact source trial IDs;
- error bars are computed from the declared unit;
- log axes contain only positive values;
- no NaN/Inf in CSV/JSON/SVG labels;
- figure IDs and filenames are unique;
- SVG/PDF/PNG outputs exist and are nonempty;
- output manifests hash all generated artifacts;
- captions do not overstate claim boundaries;
- rerunning on unchanged inputs is deterministic where practical.

Run visual QA by opening every composite PNG and a contact sheet. Inspect label clipping, overlapping legends, tiny fonts, color contrast, and scientific-notation readability. Do not call the figure suite complete solely because files were generated.

## 8. Phase F — documentation and final internal evidence package

Update:

- `README.md` with current results and one-command reproduction;
- `PROJECT_CONTEXT.md` with multi-family status;
- `reports/RESULTS.md` with Stage 4, preliminary Stage 5, and Stage 5 v2 metrics;
- `reports/LIMITATIONS.md` with remaining scope boundaries;
- `reports/FIGURE_CATALOG.md` with status/source/interpretation for F01–F36;
- `reports/CLAIM_EVIDENCE_MATRIX.md`;
- `reports/REPRODUCIBILITY_CHECKLIST.md`;
- `reports/FINAL_INTERNAL_HANDOFF.md`.

`FINAL_INTERNAL_HANDOFF.md` must report:

1. exact Git commit and dirty/clean status;
2. all upstream/input/build SHAs;
3. tests and smoke checks;
4. workload/family/candidate/repetition counts;
5. exact held-out metrics;
6. strongest supported claim and rejected stronger claims;
7. figure catalog and recommended poster shortlist;
8. unresolved failures/blocked figures;
9. reproduction commands and approximate runtime;
10. cloud time/cost estimate;
11. next work after submission.

Do not write the student's abstract, summary, or poster copy. Internal factual captions and evidence explanations are allowed; the student must write and interpret the submitted material.

## 9. Schedule and hard priority order

### August 1

- run/audit preliminary Stage 5;
- implement overhead;
- fix threshold and baseline alias;
- repair stale docs.

### August 2

- verify N₂/H₂O provenance and AMD compatibility;
- generate prefix workloads;
- run all correctness calibrations;
- freeze multi-family protocol.

### August 3–4

- run multi-family pilot and final repeated CPU/GPU timing;
- perform configuration-axis pruning only after timing coverage exists.

### August 4–5

- run Stage 5 v2 leave-one-family-out evaluation;
- run ablations and inference overhead;
- freeze allowed claims.

### August 5–6

- generate F01–F36 as data permits;
- build composite plates and contact sheet;
- visual QA and traceability audit.

### August 6–7

- finish internal evidence package;
- student authors the poster and 800-word summary using verified evidence;
- student selects the clearest five to eight figures/panels.

### August 8

- final result/reference/AI-policy/submission QA;
- submit with buffer;
- archive exact submitted files and repository commit.

## 10. Stop and pivot rules

- If N₂/H₂O do not run unmodified through the same AMD binaries, do not combine cross-solver timings. Retain Fe₄S₄ and narrow the claim.
- If multi-family correctness is not complete by August 3, stop configuration expansion.
- If multi-family timing is incomplete by August 5, finish the strongest honest CPU/GPU cross-family subset; do not create missing values.
- If full features do not beat size-only/static threshold, report that result and remove the structure-improvement claim.
- If `bit_length`/shuffle are consistently dominated or unreliable, prune them and call the system a CPU/GPU runtime selector.
- If figure source data is absent, mark the figure blocked; never simulate evidence.
- The submission deadline takes priority over profiler experiments, extra models, and decorative figures.

## 11. First response and first work block

Your first response must:

1. summarize the verified current state in five bullets;
2. show the exact Phase A work block and cost/resource impact;
3. inspect `git status`, current commit, Stage 4 completion hashes, Python/scikit-learn version, and GPU idleness;
4. run the existing Stage 5 evaluator and tests if the gates pass;
5. inspect and report actual preliminary selector outcomes;
6. stop before any new workload download or benchmark sweep and ask for approval for the next clearly bounded batch.

Do not respond only with a plan. Execute Phase A evaluation and report evidence.

# End Codex execution prompt

---

# Student-facing claim guide

The project can make a meaningfully larger claim only if the corresponding gate passes.

## Strongest realistic claim

If Fe₄S₄, N₂, and H₂O all run through the same AMD CPU/GPU binaries and leave-one-family-out evaluation succeeds:

> AutoSBD is an interpretable CPU–GPU runtime selector evaluated across three authentic Selected-Basis Diagonalization chemistry workload families using leave-one-family-out testing.

## Additional claim requiring ablation evidence

Only if the full-feature model consistently improves over size-only and the static threshold:

> Structural pre-execution features improve selection beyond configuration count alone.

## Additional claim requiring configuration evidence

Only if `bit_length`, shuffle, or another verified knob has instance-dependent winners:

> AutoSBD jointly selects backend and a modest representation/load-balance configuration.

## Claims that remain unsupported

- universal SBD autotuning;
- generalization to arbitrary molecules/hardware;
- multi-node or multi-GPU scalability;
- QPU speedup or quantum advantage;
- proven avoidance of real GPU OOMs unless near-capacity cases are measured;
- comprehensive tuning of all `(a,b,t,r)`/MPI decomposition choices.

# Recommended poster figure shortlist

From the large internal catalog, the likely strongest poster set is:

1. F01 AutoSBD architecture;
2. F03 cross-family CPU/GPU runtime scaling;
3. F04 speedup/crossover landscape;
4. F05 held-out policy performance;
5. F06 regret distribution;
6. F07 decision logic;
7. F08 structural ablation;
8. F29/F31 correctness and memory-safety evidence.

Use fewer if readability suffers. The numerous remaining figures provide reviewer defense, supplemental evidence, and future poster revisions.
