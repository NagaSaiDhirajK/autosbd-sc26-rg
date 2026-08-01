# AutoSBD Figure Catalog

## Generated Figures

- `cpu_gpu_crossover`
  - title: Stage4 CPU/GPU crossover landscape
  - outputs: `figures/cpu_gpu_crossover.svg`, `figures/cpu_gpu_crossover.pdf`, `figures/cpu_gpu_crossover.png`
  - data: `results/processed/figure_data/cpu_gpu_crossover.csv`
  - source: `results/processed/stage4_final.json` + `results/raw`
  - status: generated

- `gpu_memory_guard`
  - title: GPU memory guard
  - outputs: `figures/gpu_memory_guard.svg`, `figures/gpu_memory_guard.pdf`, `figures/gpu_memory_guard.png`
  - data: `results/processed/figure_data/gpu_memory_guard.csv`
  - source: `results/processed/stage4_final.json` + `results/raw`
  - status: generated

- `cpu_thread_scaling`
  - title: CPU thread-scaling pilot
  - outputs: `figures/cpu_thread_scaling.svg`, `figures/cpu_thread_scaling.pdf`, `figures/cpu_thread_scaling.png`
  - data: `results/processed/figure_data/cpu_thread_scaling.csv`
  - source: `results/raw`
  - status: generated

- `inference_overhead`
  - title: Inference overhead
  - outputs: `figures/inference_overhead.svg`, `figures/inference_overhead.pdf`, `figures/inference_overhead.png`
  - data: `results/processed/figure_data/inference_overhead.csv`
  - source: `results/processed/stage5_multifamily/inference_overhead.csv`
  - status: generated

- `multifamily_holdout_generalization`
  - title: Multifamily held-out generalization
  - outputs: `figures/multifamily_holdout_generalization.svg`, `figures/multifamily_holdout_generalization.pdf`, `figures/multifamily_holdout_generalization.png`
  - data: `results/processed/figure_data/multifamily_holdout_generalization.csv`
  - source: `results/processed/stage5_multifamily/policy_summary.csv`
  - status: generated

- `multifamily_policy_regret`
  - title: Multifamily policy regret
  - outputs: `figures/multifamily_policy_regret.svg`, `figures/multifamily_policy_regret.pdf`, `figures/multifamily_policy_regret.png`
  - data/trace: `results/processed/figure_data/multifamily_figure_trace.json`
  - source: `results/processed/stage5_multifamily/policy_summary.csv`, `results/processed/stage5_multifamily/policy_predictions.csv`
  - status: generated

- `multifamily_instance_decisions`
  - title: Multifamily instance decision matrix
  - outputs: `figures/multifamily_instance_decisions.svg`, `figures/multifamily_instance_decisions.pdf`, `figures/multifamily_instance_decisions.png`
  - data/trace: `results/processed/figure_data/multifamily_figure_trace.json`
  - source: `results/processed/stage5_multifamily/policy_summary.csv`, `results/processed/stage5_multifamily/policy_predictions.csv`
  - status: generated

- `numerical_parity`
  - title: Numerical parity
  - outputs: `figures/numerical_parity.svg`, `figures/numerical_parity.pdf`, `figures/numerical_parity.png`
  - data: `results/processed/figure_data/numerical_parity.csv`
  - source: `results/raw`
  - status: generated

- `run_eligibility_flow`
  - title: Run eligibility flow
  - outputs: `figures/run_eligibility_flow.svg`, `figures/run_eligibility_flow.pdf`, `figures/run_eligibility_flow.png`
  - data: `results/processed/figure_data/run_eligibility_counts.csv`
  - source: `results/processed/stage4_final.json` + `results/raw`
  - status: generated

## Blocked or Unimplemented Figures

- `F01`: AutoSBD end-to-end architecture
  - blocked: not implemented in current figure pipeline

- `F02`: Experimental provenance and evidence DAG
  - blocked: no DAG generator implemented

- `F03`: Cross-family CPU/GPU runtime scaling
  - blocked: current Stage4 dataset supports limited representative workloads only

- `F04`: CPU/GPU speedup and crossover landscape
  - blocked: current output is limited to Stage4 crossover analysis, not full family×size winner map

- `F05`: Held-out policy performance
  - blocked: partial support exists from multifamily regret summaries, but the exact family-aggregated layout is not rendered

- `F06`: Policy regret distribution
  - blocked: not implemented

- `F07`: Interpretable model and decision logic
  - blocked: requires model visualization beyond current pipeline

- `F08`: Structural-feature ablation
  - blocked: not implemented

- `F09`: Per-family runtime small multiples
  - blocked: not implemented

- `F10`: Runtime variability
  - blocked: not implemented

- `F11`: Empirical scaling slope
  - blocked: not implemented

- `F12`: End-to-end versus solver time
  - blocked: not implemented

- `F13`: Absolute and relative speedup matrix
  - blocked: not implemented

- `F14`: CPU thread-scaling pilot
  - supported: generated as `cpu_thread_scaling`

- `F15`: Measured versus predicted runtime
  - blocked: not implemented

- `F16`: Prediction residual diagnostics
  - blocked: not implemented

- `F17`: Selection matrix
  - blocked: not implemented

- `F18`: Fold-by-fold generalization
  - blocked: not implemented

- `F19`: Model stability
  - blocked: not implemented

- `F20`: Inference overhead
  - supported: generated as `inference_overhead`

- `F21`: Learning-curve sensitivity
  - blocked: not implemented

- `F22`: Workload structural fingerprint heatmap
  - blocked: not implemented

- `F23`: Feature correlation and collinearity
  - blocked: not implemented

- `F24`: Dataset coverage map
  - blocked: not implemented

- `F25`: bit_length sensitivity
  - blocked: current records contain only a single unique `bit_length`, so no sensitivity can be shown

- `F26`: shuffle sensitivity
  - blocked: current records contain only `shuffle=false`, so no matched experiment exists

- `F27`: Configuration winner map
  - blocked: not implemented

- `F28`: Configuration-pruning Pareto plot
  - blocked: not implemented

- `F29`: Numerical parity
  - supported: generated as `numerical_parity`

- `F30`: Davidson convergence diagnostics
  - blocked: no iteration or residual history is available in raw records

- `F31`: GPU memory guard
  - partially supported by current GPU memory guard figure; full cross-family extension not available with current data

- `F32`: GPU telemetry timeline
  - blocked: raw records lack time-series telemetry fields for utilization, memory, power, and temperature

- `F33`: Host-resource timeline
  - blocked: raw records lack host RSS/CPU utilization timeline data

- `F34`: Run eligibility and outcome flow
  - supported: generated as `run_eligibility_flow`

- `F35`: Benchmark campaign timeline
  - blocked: not implemented

- `F36`: Claim-to-evidence matrix
  - blocked: not implemented

## Notes

- Generated figures were produced deterministically from existing Stage4 and multifamily artifacts.
- Raw data support is sufficient for the nine generated figures listed above.
- Additional handoff figures remain either unimplemented or data-limited; the most concrete data-blocked cases are F25/F26 (single-valued parameter coverage) and F30–F33 (missing telemetry/convergence history).
