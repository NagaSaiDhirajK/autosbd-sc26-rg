# Phase B N₂/H₂O pilot audit

## Status and evidence boundary

The manifest-linked Phase B pilot completed successfully on August 1, 2026. It
is valid planning and crossover-bracketing evidence for the exact N₂/6-31G and
H₂O/cc-pVDZ prefix grids. Each candidate/workload has only one measured
repetition, so these values are not final repeated timing evidence and do not
support a cross-family selector claim.

The active solver for every record is the official, unmodified
`AMD-HPC/amd-sbd` commit
`729cfa3a5011fb805eb9e686a7711f6919836dcb`. The retained
`r-ccs-cms/sbd` checkout supplied exact licensed input bytes only; no RIKEN
executable was built, run, timed, trained on, or selected.

## Traceable inputs and outputs

| Artifact | SHA-256 |
| --- | --- |
| Pilot config, `configs/phaseb_n2_h2o_grid_pilot.yaml` | `3519b8fd4e45d9a412dd85a1fae9c586ddf865c078ae4cbfeaa43ee1a5091d70` |
| Correctness manifest, `reports/phaseb_n2_h2o_grid_correctness_manifest.json` | `ba6bf82b63c9a8bdf2a5a513df914a9f1446605a0d4939cb53f7921527222829` |
| Pilot aggregate JSON, `results/processed/phaseb_n2_h2o_grid_pilot.json` | `576e87b67be2cb964bd1786bb754a7b619800523a3e29971bad97615199c9f5a` |
| Pilot aggregate CSV, `results/processed/phaseb_n2_h2o_grid_pilot.csv` | `f224bbf934cda56ae65cbc5eb2d56e2431cd4f61c8e8f2094dbca53116117a16` |
| CPU16 executable | `190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07` |
| L4 executable | `8f1481b6bcb4ddf3326453fd3a7c03dc36e29034629f46c5e982a4c17e43bc07` |

All 40 raw records use clean project commit
`f584f144a4bff480559ffeb57824a07b66ec6734`. Their total size is 747,294
bytes. The raw-evidence chain is
`8f9c93a036f74b6852d0388868883b6d8beeb6d1765f67af5f8a268836a61a78`,
defined as SHA-256 of canonical, key-sorted JSON over the aggregate's sorted
`[{trial_id,path,size_bytes,sha256}]` entries.

The schema-v3 aggregate was generated twice from the same explicit 40 paths.
The second invocation reported both outputs unchanged. It contains two family
summaries, ten workloads, twenty candidate groups, twenty included measured
records, and twenty excluded warmups. The schema-v2 Stage 3 candidate aggregate
remained byte-identical after the family-aware aggregation extension.

## Integrity audit

An independent read-only audit loaded all records through the strict record
validator and reconstructed the frozen config's exact logical and physical
trial identities without invoking the solver. It found:

- 40 unique schema-v3 trial IDs and 40 unique logical IDs;
- 20 CPU and 20 GPU records;
- 20 warmups, all timing-ineligible, and 20 measured records, all
  timing-eligible;
- exactly one CPU/GPU record for every family, workload, and phase;
- success, process success, scientific success, and `correct=true` on all 40;
- byte-valid build, input, stdout, stderr, resource-log, and correctness-manifest
  path/size/hash claims;
- unchanged inputs before launch and after execution;
- an idle L4 and a successful compute-process query before every trial;
- disabled target offload on CPU and mandatory device-0 offload, observed GPU
  allocation, and complete GPU monitoring on GPU;
- no timeout, OOM, skip, parse error, convergence error, overlap, or unexplained
  anomaly.

The campaign ran sequentially from `2026-08-01T16:18:06.021942Z` through
`2026-08-01T16:20:57.210461Z`, a 171.188519-second span, with zero overlapping
record intervals. Maximum final residual was
`9.746200382889772e-9`; maximum reference relative error was
`9.134172443598379e-16`.

## One-repetition timing diagnostics

`CPU/GPU` is CPU16 wall time divided by L4 wall time. Values above one favor
the GPU. These are single measured pilot observations, not medians across
independent repetitions.

| Family | Half determinants | Configurations | CPU16 wall (s) | L4 wall (s) | CPU/GPU | Observed winner |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| N₂ | 32 | 1,024 | 0.608429 | 0.883288 | 0.688823 | CPU16 |
| N₂ | 55 | 3,025 | 0.708497 | 0.863529 | 0.820467 | CPU16 |
| N₂ | 100 | 10,000 | 1.110155 | 1.000671 | 1.109410 | L4 |
| N₂ | 174 | 30,276 | 3.021159 | 1.173929 | 2.573544 | L4 |
| N₂ | 239 | 57,121 | 5.836347 | 1.328953 | 4.391689 | L4 |
| H₂O | 32 | 1,024 | 0.607913 | 0.843161 | 0.720993 | CPU16 |
| H₂O | 55 | 3,025 | 0.707753 | 1.002912 | 0.705698 | CPU16 |
| H₂O | 100 | 10,000 | 1.312102 | 0.995236 | 1.318383 | L4 |
| H₂O | 174 | 30,276 | 3.624827 | 1.309427 | 2.768254 | L4 |
| H₂O | 275 | 75,625 | 10.860245 | 1.765309 | 6.152036 | L4 |

Both families therefore bracket a candidate flip between 3,025 and 10,000
configurations. No crossover location is interpolated between those measured
points.

## Resources and cost

Peak recorded GPU allocation was 196 MiB and peak host RSS was 138.1875 MiB.
The minimum preflight free VRAM in raw records was 22,564 MiB. The separate
outer driver checks also remained idle and below 37 °C before launches. Total
solver-process wall fields summed to 78.958121 seconds; the conservative staged
driver span was 171.188519 seconds. At the repository-recorded list rate of
USD 1.734376528/hour, the observed pilot span costs approximately USD 0.08247.
This rate was not independently refreshed during the audit.

The frozen final protocol is `reports/phaseb_final_protocol.json`. It plans 104
sequential records: 20 excluded warmups and 84 measurements. Using pilot wall
times plus the pilot's observed per-record orchestration overhead projects
7.55063 minutes and USD 0.21826; a 25% buffer projects 9.43829 minutes and
USD 0.27283.

## Gate

The final campaign has not been launched. Decisions D-035 and D-036 require
fresh explicit approval after this measured estimate. The pilot remains
planning evidence even after final data exist; only eligible final repetitions
may supply final N₂/H₂O medians, variability, evaluation, or figure values.
