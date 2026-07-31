# AutoSBD project context

Status date: 2026-07-31

Submission deadline supplied by the handoff: 2026-08-08

Current phase: Stage 1 upstream reproduction is complete and Stage 2 harness implementation is next. Both upstream repositories are pinned. NVIDIA HPC SDK 26.5 builds official AMD-HPC `sc26-artifacts` CPU and L4 GPU executables from the same unmodified commit, and identical-input Fe₄S₄ residual, energy, and density validation passes. Earlier RIKEN builds and a CPU smoke run remain historical fallback evidence, not the primary pipeline.

## Research objective

AutoSBD asks whether inexpensive features available before execution can select the fastest feasible multicore-CPU or GPU configuration for Selected-Basis Diagonalization while preserving accuracy and avoiding GPU-memory failures. SBD is the dominant classical eigensolver workload within Sample-Based Quantum Diagonalization (SQD).

The minimum contribution is:

1. a reproducible harness around existing, cited SBD implementations;
2. a structure-aware feature representation and deterministic feasibility guard;
3. a small interpretable runtime selector;
4. held-out comparison against fixed CPU, fixed GPU, upstream/default, a training-only static threshold, and the measured oracle; and
5. analysis of crossover behavior, normalized regret, memory safety, correctness, and inference overhead on one CPU/L4 node.

This is not a new SBD solver, a claim to the upstream GPU port, a deep-learning project, a real-QPU experiment, or a multi-node scalability study.

## Scientific motivation

The OpenMP-offload SBD work reports sensitivity to determinant representation (`bit_length`), cache footprint, shuffling/load balance, problem size, and decomposition choices. CPU execution can be competitive for small workloads, GPU caching trades capacity for speed, and the configuration space currently requires experimentation. AutoSBD tests whether measured, pre-execution structure can turn that gap into a safe runtime choice.

Parameter names and meanings must be verified from the exact checked-out source before wrappers or configuration schemas expose them.

## Primary sources and upstream software

- Walkup et al., *Scaling Sample-Based Quantum Diagonalization on GPU-Accelerated Systems using OpenMP Offload*, arXiv:2601.16169: https://arxiv.org/abs/2601.16169
- Doi et al., *GPU-Accelerated Selected Basis Diagonalization with Thrust for SQD-based Algorithms*, arXiv:2601.16637: https://arxiv.org/abs/2601.16637
- Robledo-Moreno et al., *Chemistry Beyond the Scale of Exact Diagonalization on a Quantum-Centric Supercomputer*, arXiv:2405.05068: https://arxiv.org/abs/2405.05068
- AMD-HPC SBD, primary implementation pinned to official `sc26-artifacts`: https://github.com/AMD-HPC/amd-sbd
- RIKEN/IBM SBD, secondary historical fallback pinned to tag `v1.3.0`: https://github.com/r-ccs-cms/sbd
- Qiskit SQD addon: https://github.com/Qiskit/qiskit-addon-sqd
- Qiskit HPC-ready SQD addon: https://github.com/Qiskit/qiskit-addon-sqd-hpc
- Qiskit C API HPC demo: https://github.com/qiskit-community/qiskit-c-api-demo

## Current machine

- GCP host `instance-20260731-140922`, expected machine class `g2-standard-32`
- Intel Xeon virtual CPU at 2.20 GHz: 16 physical cores, 2 threads/core, 32 logical CPUs, one NUMA node
- 125 GiB RAM, no swap; 122 GiB available at audit
- NVIDIA L4: 23,034 MiB total, 22,564 MiB free at audit; no active GPU process
- NVIDIA driver 580.173.02; driver-reported CUDA compatibility 13.0
- CUDA toolkit/nvcc 12.9.41; the differing driver/toolkit numbers are expected and require no repair
- Ubuntu 22.04.5 LTS; GCC 12.3.0; Python 3.10.12
- 79 GiB free on the repository filesystem at audit

See `reports/ENVIRONMENT.md` for the full initial readiness assessment.

## Required experimental design

Correctness precedes performance. CPU and GPU must run the same authentic input and agree on convergence plus final eigenvalue/energy within the upstream tolerance, or initially relative error at most `1e-10` if no official tolerance exists.

Every process invocation must produce one atomic, immutable JSON record containing trial identity, timestamps, repository/upstream/build provenance, hardware/software identity, input SHA-256, workload features, candidate settings, command, timings, numerical result/correctness, resource peaks, timeout/OOM/exit state, and log paths. Failed and skipped candidates remain data.

The initial candidate layer is CPU threads `{1, 4, 8, 16}` after affinity validation and one upstream-default GPU candidate. Cache, `bit_length`, shuffle, decomposition, MPI, or other axes are added only after the CPU/GPU pipeline is complete and only when the selected upstream source truly exposes them.

Workloads should come from upstream tests/examples or associated authentic chemistry inputs. Prefer at least three independent families; otherwise use grouped instances plus a strict largest-size holdout and disclose the limitation. Scale geometrically to find the crossover without spending credits only on larger GPU-dominant cases.

Final timing uses end-to-end wall time, separate warm-ups, randomized configuration order, three broad-grid repetitions, five repetitions near crossover/headline cases, median plus IQR, no concurrent final runs, and only selected profiling after stable timings exist.

## Tuner and evaluation

Each training row represents:

`pre-execution problem features + candidate features -> log1p(measured runtime)`

A deterministic memory/validity guard filters candidates first. The primary model is a shallow `DecisionTreeRegressor`; an ensemble is optional and secondary. Enumerate feasible candidates and select the lowest predicted runtime while measuring inference overhead.

Keep repetitions grouped. Prefer leave-one-family-out, otherwise `GroupKFold` by instance, plus largest-size extrapolation. Fit all preprocessing, thresholds, and model choices using training data only.

Required metrics are end-to-end runtime, geometric-mean speedup, selection accuracy with near-tie caveat, normalized regret, median/high-percentile regret, invalid/OOM selection rate, inference overhead, correctness failure rate, and generalization by held-out family/size.

## Staged execution and stopping points

- Stage 0: audit and durable context; stop for installation/Stage 1 approval.
- Stage 1: pin/inspect both upstreams, reproduce authentic CPU/GPU correctness, and record build provenance.
- Stage 2: implement/test immutable single-run and resumable sweep harnesses.
- Stage 3: catalog authentic workloads and run an approved geometric pilot.
- Stage 4: freeze configuration and collect approved final data.
- Stage 5: train and evaluate the leakage-safe tuner and baselines.
- Stage 6: generate traceable engineering/scientific reports, tables, and figures; audit claims and reproducibility.
- Stages 7–8 submission authorship: reserved for the student. Codex may organize evidence and checklists, but must not write or generate the abstract, summary, poster, or other submission content.

## Minimum engineering definition of done

A fresh shell reproduces the documented build; identical-input CPU/GPU correctness passes; runs are bounded/resumable/immutable; records contain complete provenance; evaluation has no train/test leakage; raw data regenerates tables and figures; claims exclude failed/profiled/cherry-picked results; licenses and citations are correct; tests plus a clean smoke run pass; and the final internal report lists commands, changes, tests, results, failures, estimates, limitations, and next actions.
