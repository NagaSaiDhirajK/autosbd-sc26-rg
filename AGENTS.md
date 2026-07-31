# AutoSBD repository instructions

## Mission

Build a credible, reproducible, single-node CPU/GPU runtime selector for authentic Selected-Basis Diagonalization (SBD) workloads. The original contribution is the benchmark harness, pre-execution features, memory-feasibility guard, interpretable selector, held-out evaluation, and analysis—not a new eigensolver or an upstream GPU port.

## Student-ownership boundary

- Never draft, write, rewrite, or generate the student's abstract, 800-word submission summary, poster, poster source, poster copy, or other student-authored submission material.
- Do not create a representative or final poster, even if an older plan requests one.
- Internal engineering/scientific reports, evidence tables, reproducibility artifacts, project organization, and submission checklists are allowed. Leave all student-submission prose and final interpretation to the student.
- Explain generated code and analysis so the student can inspect, reproduce, and defend every component.

## Scope and scientific integrity

- Reuse and cite authentic upstream SBD implementations; never implement a substitute SBD/Davidson solver or benchmark an unrelated toy kernel.
- Pin upstream source by commit/tag and record URL, SHA, build flags, licenses, input hashes, and patches.
- Never fabricate, interpolate, silently alter, hand-edit, or delete raw measurements. Raw per-run records are immutable.
- Validate CPU/GPU correctness on identical inputs before treating timings as valid.
- Prevent evaluation leakage: keep repetitions of an instance/configuration in one split, learn thresholds and models on training data only, and make held-out regret/speedup the primary evidence.
- Describe this machine accurately as one heterogeneous node with an NVIDIA L4; do not imply multi-node or exascale results.

## Upstream and pivot policy

1. Inspect both `AMD-HPC/amd-sbd` and `r-ccs-cms/sbd` before choosing.
2. Try the AMD CPU target first and verify the NVIDIA OpenMP-offload compiler requirements from source.
3. Do not install NVIDIA HPC SDK without explicit approval.
4. After at most 60 minutes of focused AMD GPU build work, pivot to `r-ccs-cms/sbd` tag `v1.3.0` if no working NVIDIA GPU build exists. Record the evidence and rationale.

## Work protocol

- Before every command/tool batch, tell the user the goal, necessity, exact actions, expected duration/resource impact, affected files, and whether approval is needed.
- After every batch, report exit status, evidence, file changes, checks, resource use, interpretation, and next action.
- Append executed shell commands and outcomes to `reports/COMMAND_LOG.md`; experiment purpose/config/results/anomalies to `reports/EXPERIMENT_LOG.md`; consequential choices to `reports/DECISIONS.md`.
- Save verbose outputs under `logs/` and report only useful excerpts. Redact credentials and tokens.
- Use bounded commands during setup and a five-minute per-run pilot timeout unless evidence justifies a change.
- Do not repeat an unchanged failing command more than once.

## Approval and safety gates

Obtain explicit approval before package installation; downloads over 500 MiB; multi-gigabyte toolchains; benchmarks over 10 minutes; sweeps estimated above USD 1; replay-heavy profiling; cloud/IAM/firewall/billing changes; paid APIs; QPU use; pushing or publishing.

Before each benchmark, verify the GPU is idle; capture free VRAM, temperature, power, and CPU load; estimate memory; skip candidates above 80% of current free VRAM; monitor peak host/GPU memory; enforce timeout; atomically record success or failure; and resume by immutable trial ID. Default to at most about 20 GiB of L4 VRAM. Do not run final timing configurations concurrently.

Preserve user changes, avoid destructive Git commands, do not commit without reviewing scope, and never push without approval. At the end of each work session, remind the user to stop the GCP VM unless a job is intentionally running.

