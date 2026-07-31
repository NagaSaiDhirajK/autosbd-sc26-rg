# AutoSBD for SC26: Codex Project Handoff and Eight-Day Execution Plan

Prepared for the remote GCP workspace `~/autosbd-sc26-rg` on July 31, 2026.

## How to use this document

1. Open the repository root in the remote VS Code window.
2. Open the Codex sidebar and start a new local workspace chat.
3. Type `/plan`, then paste everything in **Master prompt for Codex** below.
4. Let Codex complete **Stage 0 only** and review its report before authorizing package installation or a benchmark sweep.
5. Keep the same chat for implementation. Start a new chat after large context compactions only after `AGENTS.md`, `PROJECT_CONTEXT.md`, and the experiment logs exist in the repository.

Codex reads repository-level `AGENTS.md` automatically. The master prompt therefore tells it to create concise durable instructions there and to put the longer scientific context in `PROJECT_CONTEXT.md`.

---

# Master prompt for Codex

You are the principal software/research engineering agent for an undergraduate ACM Student Research Competition submission to SC26. Work directly in the currently open remote repository, which is expected to be `~/autosbd-sc26-rg`. The submission deadline is **August 8, 2026**. Today is **July 31, 2026**. The immediate goal is a credible, reproducible, narrowly scoped result suitable for the submission; later optimization is secondary.

## 1. Project identity and research question

Working title:

> **AutoSBD: Structure-Aware CPU–GPU Runtime Autotuning for Selected-Basis Diagonalization in Sample-Based Quantum Workflows**

Research question:

> Can inexpensive, pre-execution features of an SBD problem predict whether a multicore CPU or GPU execution configuration will be fastest, while avoiding GPU-memory failures and preserving numerical accuracy?

Primary hypothesis:

> A small, interpretable runtime model trained on measured SBD runs can outperform fixed CPU-only, GPU-only, and static-threshold policies by learning the CPU–GPU crossover and configuration sensitivities associated with problem size, determinant representation, cache footprint, and load distribution.

The original contribution is **not** a new SBD solver and **not** the upstream GPU port. The original contribution is:

1. a reproducible benchmark harness over existing, cited SBD implementations;
2. a structure-aware feature representation and feasibility guard;
3. an interpretable runtime selector/autotuner;
4. a held-out evaluation against fixed policies and an oracle;
5. analysis of the crossover, regret, memory boundary, and tuner overhead on one heterogeneous node.

Use **AutoSBD** in code and prose because the tuned kernel is Selected-Basis Diagonalization. Explain that SBD is the dominant classical eigensolver workload inside Sample-Based Quantum Diagonalization (SQD).

## 2. Scientific basis and gap

Treat the following as primary sources and cite them in the repository and submission:

- Walkup et al., “Scaling Sample-Based Quantum Diagonalization on GPU-Accelerated Systems using OpenMP Offload,” arXiv:2601.16169: https://arxiv.org/abs/2601.16169
- Doi et al., “GPU-Accelerated Selected Basis Diagonalization with Thrust for SQD-based Algorithms,” arXiv:2601.16637: https://arxiv.org/abs/2601.16637
- Robledo-Moreno et al., “Chemistry Beyond the Scale of Exact Diagonalization on a Quantum-Centric Supercomputer,” arXiv:2405.05068 / Science Advances 2025: https://arxiv.org/abs/2405.05068
- AMD-HPC SBD fork: https://github.com/AMD-HPC/amd-sbd
- RIKEN/IBM SBD implementation; pin tag `v1.3.0` when reproducing the GPU paper: https://github.com/r-ccs-cms/sbd
- Qiskit SQD addon: https://github.com/Qiskit/qiskit-addon-sqd
- Qiskit HPC-ready SQD addon: https://github.com/Qiskit/qiskit-addon-sqd-hpc
- Qiskit C API HPC demo: https://github.com/qiskit-community/qiskit-c-api-demo

The OpenMP-offload paper explicitly reports that:

- GPU performance is sensitive to `bit_length`, whereas CPU performance is much less sensitive.
- For H2O/cc-pVDZ, changing `bit_length` from 20 to 48 reduces the determinant-cache representation from three 64-bit words to one and improves GPU performance.
- shuffling tends to improve CPU load balance, while the GPU tends to be slightly faster without shuffling.
- small problems, especially below roughly `10^5` configurations in that study, may run efficiently on CPUs because the GPU lacks enough work.
- persistent determinant caching exchanges memory capacity for speed.
- multiple work/memory decomposition options create a large parameter space that currently requires experimentation; the paper says more general guidance built into the program would be useful.

This is the direct motivation for AutoSBD. Verify every parameter name and meaning against the exact checked-out source before implementing a wrapper. Never infer CLI flags from the paper alone.

## 3. Fixed hardware and current environment

Known VM state from July 31, 2026:

- Google Cloud `g2-standard-32`
- one NVIDIA L4, 23,034 MiB visible VRAM
- 32 vCPUs / approximately 16 physical CPU cores and 128 GiB system RAM
- Ubuntu 22.04 Deep Learning VM
- NVIDIA driver 580.173.02
- `nvidia-smi` reports CUDA compatibility 13.0
- `nvcc` is CUDA toolkit 12.9.41
- GCC 12.3.0
- Python 3.10.12
- estimated instance rate shown in the portal: about USD 1.74/hour, funded by finite trial credit

The CUDA driver capability and installed CUDA toolkit version are allowed to differ. Do not try to “fix” this merely because `nvidia-smi` prints 13.0 while `nvcc` prints 12.9.

At Stage 0, verify rather than assume the presence of `git`, `cmake`, `ninja`, `mpicxx`, `clang++`, `nvc++`, `nsys`, `ncu`, BLAS/LAPACK, and sufficient disk space.

## 4. Hard scope boundaries

### Minimum publishable result by August 6

Produce all of the following:

1. one authentic upstream SBD CPU executable and one GPU executable, or a single executable with verified CPU/GPU backends;
2. numerical agreement on the same inputs;
3. a benchmark harness that produces immutable per-run records;
4. at least three problem families or, if authentic family diversity is unavailable, clearly labeled authentic inputs with several nontrivial sizes and a size-held-out evaluation;
5. a CPU–GPU crossover plot;
6. an interpretable tuner trained only on training runs;
7. comparisons with fixed CPU, fixed GPU, an upstream/default policy, a static threshold learned only from training data, and the measured oracle;
8. regret, speedup, memory-safety, and tuner-overhead results on held-out inputs;
9. scripts that reproduce tables and plots from raw results;
10. an honest limitations section.

### Stretch goals only after the minimum result exists

- cache on/off selection;
- `bit_length` and shuffle selection if exposed and correct in the chosen implementation;
- CPU thread-count tuning;
- selected single-node MPI decomposition options;
- a second GPU architecture;
- multi-node experiments;
- real QPU sampling.

### Explicit non-goals before submission

- Do not write an SBD or Davidson solver from scratch.
- Do not train a neural network.
- Do not use real QPU time; use upstream or stored/simulated bitstrings and authentic Hamiltonian inputs.
- Do not claim multi-node scalability from one node.
- Do not claim a broadly general quantum advantage.
- Do not optimize unrelated toy matrix multiplication merely because it is easy to benchmark.
- Do not fabricate, interpolate, or hand-edit measurements.

## 5. Mandatory communication and reporting protocol

The user is learning and must know what is happening. Never silently run a command batch, dependency installation, benchmark sweep, or code-generation step.

Before each tool/command batch, report:

```text
WORK BLOCK
Goal:
Why this is necessary:
Commands/actions to be run:
Expected duration:
Expected CPU/GPU/RAM/disk impact:
Files expected to change:
Approval needed: yes/no, and why
```

After each batch, report:

```text
RESULT
Exit status:
What happened:
Important evidence/output:
Files created or modified:
Tests/checks passed or failed:
Measured runtime/resource use, if applicable:
Interpretation:
Next proposed action:
```

Also append durable summaries to:

- `reports/COMMAND_LOG.md`: UTC timestamp, working directory, exact command, exit code, duration, short outcome. Redact credentials and tokens.
- `reports/EXPERIMENT_LOG.md`: hypothesis/purpose, config identifier, result paths, anomalies, decision.
- `reports/DECISIONS.md`: consequential design choices and why they were made.

Do not dump thousands of console lines into chat. Save full logs under `logs/` and report the relevant tail plus the log path.

If a command fails, explain the likely cause from evidence. Do not repeat the same command unchanged more than once.

## 6. Cost and safety gates

The VM consumes limited credits whenever it is running. Optimize researcher time and cloud time.

Require explicit user approval before:

- a package download or dataset download likely larger than 500 MiB;
- installing NVIDIA HPC SDK or another multi-gigabyte toolchain;
- any benchmark expected to run longer than 10 minutes;
- any sweep expected to cost more than roughly USD 1 of VM time;
- any profiler run that may replay kernels many times;
- changing firewall, IAM, cloud billing, or service-account configuration;
- invoking paid external APIs or a QPU.

During setup, cap individual commands at 10 minutes with `timeout` when safe. During pilot benchmarking, default to a 5-minute per-run timeout. Only raise it for selected final cases after evidence from the pilot.

Before every benchmark:

1. confirm no unrelated GPU process with `nvidia-smi`;
2. record free VRAM, GPU temperature, power state, and CPU load;
3. estimate memory from input dimensions and selected cache representation;
4. skip candidates estimated to exceed 80% of currently free VRAM;
5. run the candidate as a subprocess with a timeout;
6. monitor peak VRAM and host RSS;
7. atomically write a result record even on timeout, OOM, or nonzero exit;
8. continue resumably without rerunning completed trial IDs.

Use at most about 20 GiB of the 23 GiB L4 VRAM unless an evidence-based revision is approved. Avoid concurrent final-timing runs. Never delete raw result files. Never run destructive Git commands. Never expose secrets in source, logs, or chat.

At the end of every work session, remind the user to stop the VM in the GCP console if no job is intentionally running. Do not assume a budget alert automatically stops compute.

## 7. Repository and provenance structure

First inspect the existing repository and preserve user work. If it is empty, create the following incrementally; do not create placeholder-heavy boilerplate that is never used.

```text
autosbd-sc26-rg/
├── AGENTS.md
├── PROJECT_CONTEXT.md
├── README.md
├── LICENSE
├── CITATION.cff
├── .gitignore
├── pyproject.toml
├── CMakeLists.txt                 # only if our wrapper needs CMake
├── external/                      # pinned upstream submodules or documented clones
├── src/autosbd/                   # tuner and experiment code
├── include/                       # C++ wrapper headers, only if needed
├── scripts/
│   ├── audit_environment.sh
│   ├── build_upstream.sh
│   ├── smoke_test.sh
│   ├── run_one.py
│   ├── run_sweep.py
│   ├── train_tuner.py
│   ├── evaluate_tuner.py
│   └── make_figures.py
├── configs/
│   ├── smoke.yaml
│   ├── pilot.yaml
│   └── final.yaml
├── tests/
├── data/
│   ├── README.md
│   ├── raw/                       # generally gitignored; provenance manifests tracked
│   └── processed/
├── results/
│   ├── raw/                       # immutable one-record-per-run files
│   └── processed/
├── models/
├── figures/
├── logs/
└── reports/
    ├── COMMAND_LOG.md
    ├── ENVIRONMENT.md
    ├── EXPERIMENT_LOG.md
    ├── DECISIONS.md
    ├── RESULTS.md
    └── LIMITATIONS.md
```

Use a Git submodule at an exact commit/tag when practical. If a submodule is impractical, record upstream URL, exact commit SHA, tag, patches, compiler flags, and license in `external/README.md`. Never edit upstream code without keeping a minimal patch file and describing it. Preserve Apache or other upstream notices.

Create a clean Git commit after each completed stage, but do not push or publish without the user's approval. Use descriptive commits such as `chore: capture L4 environment`, `feat: add resumable benchmark harness`, and `analysis: evaluate held-out tuner`.

## 8. Upstream implementation decision, with a strict pivot rule

Do not guess which repository will build most easily on this L4. Inspect both.

### Preferred scientific path

The AMD-HPC fork is the most direct implementation for the paper that explicitly identifies runtime-parameter sensitivity and the need for built-in guidance. Inspect it first. Build its CPU target first. Then determine exactly what compiler it expects for NVIDIA OpenMP target offload.

Check:

```bash
command -v mpicxx || true
command -v nvc++ || true
command -v clang++ || true
clang++ --version 2>/dev/null || true
nvc++ --version 2>/dev/null || true
```

Do not assume GCC 12 can build NVIDIA OpenMP target offload. Do not install the NVIDIA HPC SDK without approval.

### Practical fallback

If a working NVIDIA GPU build of AMD-HPC/amd-sbd is not obtained within **60 minutes of focused build work**, pivot to `r-ccs-cms/sbd` pinned to `v1.3.0`. That release corresponds to the published Thrust GPU implementation and is a better match for the installed `nvcc` toolchain. Record the failed attempt and pivot rationale; it is not a project failure.

Select the implementation that provides:

1. the same authentic input on CPU and GPU;
2. a numerically comparable output;
3. stable CLI or callable interfaces;
4. at least one meaningful decision axis, initially CPU versus GPU;
5. reasonable build and run time on the L4 VM.

Only after a complete CPU/GPU/tuner pipeline exists should you revisit additional parameters from the AMD implementation.

## 9. Environment setup principles

Stage 0 is read-only. Suggested audit commands:

```bash
set -o pipefail
pwd
git rev-parse --show-toplevel 2>/dev/null || true
git status --short --branch 2>/dev/null || true
uname -a
cat /etc/os-release
lscpu
free -h
df -h .
nvidia-smi
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.free,temperature.gpu,power.draw,power.limit --format=csv
nvcc --version
gcc --version
g++ --version
python3 --version
cmake --version 2>/dev/null || true
ninja --version 2>/dev/null || true
mpicxx --version 2>/dev/null || true
nsys --version 2>/dev/null || true
ncu --version 2>/dev/null || true
git --version
```

After reporting the audit and receiving approval, install only missing requirements. Likely system dependencies, subject to upstream instructions, are:

```text
build-essential, cmake, ninja-build, git, pkg-config, tmux,
OpenMPI development/runtime, OpenBLAS/LAPACK development headers,
python3-venv, python3-pip, jq
```

Create a project-local `.venv`. Keep dependencies minimal and pinned after the first working environment. Likely Python packages are NumPy, pandas, SciPy, scikit-learn, Matplotlib, PyYAML, psutil, pytest, and optionally `nvidia-ml-py`/PyArrow if justified. Do not install PyTorch; it is unnecessary for an interpretable tabular tuner.

Capture exact packages and compiler versions in `reports/ENVIRONMENT.md`, `requirements-lock.txt` or a lock file, and a machine-readable environment JSON.

## 10. Benchmark record schema

Each process invocation must produce one immutable JSON record, later aggregated into Parquet/CSV. Include at least:

```text
schema_version
trial_id
timestamp_utc
hostname
project_git_commit
upstream_url
upstream_git_commit
build_id
compiler_and_flags
gpu_name
driver_version
cuda_toolkit_version
cpu_model
physical_cores
problem_family
problem_instance
input_sha256
seed
n_orbitals or n_spin_orbitals
n_alpha_strings
n_beta_strings
n_configurations
estimated_work
estimated_cache_bytes
backend
cpu_threads
mpi_ranks
bit_length, shuffle, cache_mode, decomposition  # only when truly exposed
warmup_or_measured
repetition
command
wall_time_s
initialization_time_s
solver_time_s
matvec_time_s
transfer_time_s
iterations
energy_or_eigenvalue
reference_value
relative_error
correct
peak_host_rss_mb
peak_gpu_memory_mb
timeout
oom
exit_code
stdout_log
stderr_log
notes
```

Use `input_sha256`, Git SHAs, and build IDs so that every plotted point is traceable. Never overwrite a record with the same `trial_id`; skip or version it explicitly.

## 11. Correctness protocol

Performance numbers are invalid until correctness is established.

1. Run the smallest upstream CPU test/reference.
2. Run the same case through the GPU backend.
3. Compare final energy/eigenvalue, convergence status, and iteration count.
4. Use the upstream project's official tolerances when provided. Otherwise begin with relative error `<= 1e-10`, matching the validation reported in the OpenMP paper, and loosen only with documented numerical justification.
5. Test timeout and failed-process handling in the wrapper.
6. Test result-schema validation.
7. Test deterministic reruns where the upstream implementation supports fixed seeds.
8. Add unit tests for feature extraction, memory estimation, candidate enumeration, model selection, grouped splitting, and regret computation.

Do not use energy equality alone if one run silently failed to converge.

## 12. Workload selection

Prioritize authentic inputs already distributed by the selected SBD repository or its associated Qiskit demo. Record their license and provenance. Start tiny and scale adaptively.

Preferred hierarchy:

1. upstream unit/sample inputs for smoke tests;
2. upstream chemistry inputs representing more than one molecule/problem family;
3. documented subsamples or prefixes generated from authentic determinant/configuration sets;
4. controlled synthetic configurations only when necessary and always labeled synthetic.

Do not call a random sparse matrix an SQD workload. Do not require a real QPU: this project studies the classical SBD backend, and stored or simulated samples are valid if disclosed.

Construct a pilot grid that crosses the region in which CPU and GPU trade places. Use geometric size steps rather than a dense uniform sweep. A starting pattern might be approximately `10^3`, `3×10^3`, `10^4`, `3×10^4`, `10^5`, `3×10^5`, and larger only if memory/runtime allow; use actual valid subspace sizes supported by the data.

## 13. Candidate configurations

Implement candidates in layers:

### Layer A: required

- CPU backend with a small thread set such as `{1, 4, 8, 16}` after confirming physical-core topology;
- GPU backend on the single L4 using the upstream default.

### Layer B: after Layer A works

- determinant cache on/off if exposed;
- `bit_length` candidates valid for the actual number of spin orbitals;
- shuffle on/off;
- one or two upstream work-distribution methods.

### Layer C: stretch

- multiple MPI ranks on one node;
- `(a,b,t,r)` or equivalent decomposition parameters;
- multi-GPU/multi-node.

Do not run multiple MPI ranks that contend for the same L4 unless the upstream implementation documents this and a controlled test shows it is meaningful.

For CPU timings, use explicit affinity when supported:

```bash
export OMP_PLACES=cores
export OMP_PROC_BIND=close
export OMP_DYNAMIC=false
```

Record all thread and affinity settings.

## 14. Measurement protocol

Use the following protocol for every result intended for the poster:

1. build release mode with symbols where possible (`-O3`, appropriate architecture flag, no debug assertions unless upstream requires them);
2. use the same executable/build and input for comparisons whenever possible;
3. record an initial warm-up separately and exclude it from timing summaries;
4. use three measured repetitions in the broad sweep;
5. use five measured repetitions for crossover points and final headline cases;
6. randomize configuration order within a problem size to reduce thermal/order bias;
7. do not run other GPU jobs concurrently;
8. report the median and an uncertainty measure such as IQR; retain all repetitions;
9. record failures and OOMs rather than deleting them;
10. profile only a few representative small/crossover/large cases after stable timing exists.

Use end-to-end wall time as the primary user-facing metric. Also report solver/matvec time when the implementation exposes it. Do not compare a GPU kernel-only time against a CPU end-to-end time.

Use Nsight Systems first for a timeline and transfer/launch breakdown. Use Nsight Compute only on selected kernels because metric collection can replay kernels and heavily distort runtime. Profiler outputs are diagnostic and must not be mixed with unprofiled timing results.

## 15. Autotuner formulation

This is a small tabular learning problem, not deep learning.

Represent every benchmark row as:

```text
problem features + candidate configuration features -> measured log(runtime)
```

Problem features should be available before execution and may include:

- number of configurations;
- number of alpha and beta strings;
- number of orbitals/spin orbitals;
- `ceil(n_spin_orbitals / bit_length)` when applicable;
- estimated determinant-cache bytes;
- estimated excitation/work counts or density when cheaply computable;
- input-file size;
- CPU thread count/backend/configuration indicators;
- free VRAM and host-memory headroom.

Do not use post-execution features such as observed iteration runtime to make a pre-execution selection unless clearly presented as an online/adaptive extension.

### Selection model

Start with:

1. a deterministic feasibility filter based on estimated memory and known-invalid combinations;
2. a shallow `DecisionTreeRegressor` on `log1p(runtime)` for interpretability;
3. a `RandomForestRegressor` or histogram gradient boosting model only as a secondary accuracy comparison if data volume supports it.

At inference, enumerate feasible candidates, predict each candidate's runtime, and choose the lowest prediction. Measure inference overhead.

### Data splitting

Prevent leakage. Repetitions of the same instance/configuration must remain in the same split. Prefer:

- leave-one-problem-family/molecule-out evaluation when at least three independent families exist; or
- `GroupKFold` grouped by problem instance; and
- a size extrapolation test in which the largest sizes are held out.

Fit preprocessing, hyperparameters, crossover thresholds, and the model on training data only. Use nested or fixed minimal hyperparameters rather than optimizing repeatedly on the test set.

### Baselines

Evaluate against:

- fixed upstream/default configuration;
- always CPU using a fixed reasonable thread count;
- always GPU using the upstream GPU default;
- a one-dimensional static size threshold fitted on training data only;
- the per-instance measured oracle.

### Metrics

Report:

- end-to-end runtime and geometric-mean speedup;
- selection accuracy, while noting that near-ties make accuracy imperfect;
- normalized regret `(selected_time - oracle_time) / oracle_time`;
- median and high-percentile regret;
- OOM/invalid selection rate;
- tuner inference overhead;
- correctness failure rate;
- generalization by held-out family and size.

The most defensible headline is a held-out regret/speedup claim, not raw training accuracy.

## 16. Figures and tables required

Generate figures entirely from tracked scripts and processed data. Every figure should have a companion CSV/JSON table.

Minimum figures:

1. **CPU–GPU crossover:** median end-to-end runtime versus number of configurations on log-log axes, with variability.
2. **Policy comparison:** normalized runtime or speedup for CPU, GPU, static threshold, AutoSBD, and oracle on held-out workloads.
3. **Regret:** distribution or per-instance plot of normalized regret.
4. **Memory boundary:** measured/estimated peak VRAM versus problem size, showing skipped or failed configurations.
5. **Interpretable decision logic:** shallow tree, decision regions, or feature importance—only if scientifically meaningful.

Minimum tables:

- hardware/software environment;
- workload characteristics and provenance;
- final performance and correctness summary;
- ablation showing what the tuner gains from structure/memory features over size alone.

Use colorblind-safe colors, readable fonts, units, descriptive captions, and no unsupported smoothing.

## 17. Eight-day staged execution schedule

### Stage 0 — July 31: audit and durable instructions

Actions:

1. inspect repository state and run the read-only environment audit;
2. report missing tools and disk/VRAM headroom;
3. create concise `AGENTS.md`, detailed `PROJECT_CONTEXT.md`, `reports/ENVIRONMENT.md`, and `reports/DECISIONS.md`;
4. propose the exact dependency installation command;
5. stop and request approval before installing.

Exit criterion: the user can see the environment, project scope, risks, and exact next command.

### Stage 1 — July 31/August 1: reproduce upstream CPU and GPU

Actions:

1. pin and inspect both upstream repositories;
2. build the smallest CPU case;
3. attempt the AMD GPU path for at most 60 minutes;
4. pivot to RIKEN `v1.3.0` if necessary;
5. run the smallest authentic CPU/GPU case;
6. establish numerical agreement;
7. record full build provenance.

Exit criterion: repeatable CPU and GPU commands on one authentic input with validated output.

### Stage 2 — August 1/2: benchmark harness

Actions:

1. implement `run_one.py` with subprocess timeout, resource monitoring, atomic JSON output, and input hashing;
2. implement candidate enumeration and memory guard;
3. add unit tests and a smoke YAML;
4. run one CPU and one GPU trial through the wrapper;
5. implement `run_sweep.py` with resumability and randomized order.

Exit criterion: `scripts/smoke_test.sh` runs cleanly and produces schema-valid records for success and intentionally triggered failure/timeout paths.

### Stage 3 — August 2/3: workload corpus and pilot

Actions:

1. catalog authentic inputs and provenance;
2. create several valid sizes without altering physics silently;
3. run one repetition per candidate over a geometric pilot grid;
4. locate crossover and memory/runtime boundaries;
5. prune uninformative/unsafe candidates;
6. freeze `configs/final.yaml` before final measurement.

Exit criterion: at least one observed crossover or a well-supported finding that the available range is one-sided, plus a feasible final sweep.

### Stage 4 — August 3/4: final benchmark data

Actions:

1. run one warm-up and three measured repetitions for the broad grid;
2. run five repetitions around the crossover/headline cases;
3. preserve failures;
4. aggregate without modifying raw files;
5. perform selected Nsight Systems/Compute profiling after timings are complete.

Exit criterion: complete, traceable measurements with uncertainty and no unexplained correctness failures.

### Stage 5 — August 4/5: tuner and held-out evaluation

Actions:

1. implement feature extraction and grouped splits;
2. fit a size-only threshold baseline;
3. fit a shallow decision-tree runtime model;
4. optionally fit one ensemble comparison;
5. evaluate held-out policies, regret, speedup, failures, and overhead;
6. run ablations and robustness checks;
7. save model, split manifests, predictions, and tables.

Exit criterion: all headline claims are computed from untouched held-out data and can be reproduced by one command.

### Stage 6 — August 5/6: analysis and figures

Actions:

1. generate required plots and tables;
2. write `reports/RESULTS.md` and `reports/LIMITATIONS.md`;
3. audit each numerical claim back to raw trial IDs;
4. run repository tests from a clean state;
5. obtain Codex code review using `/review`, then address only evidence-backed issues.

Exit criterion: a compact result package ready to turn into poster content.

### Stage 7 — August 6/7: submission draft

Prepare:

- representative poster draft;
- 800-word ACM-format summary;
- reproducibility QR target or repository link if approved for public release;
- concise contribution statement separating upstream work from the student's work;
- AI-use acknowledgement and citations required by SC26.

The poster draft need not be final at submission, but it must be representative. Verify official submission fields in the SC26 portal; the public call currently describes the poster and 800-word summary as the two main components.

### Stage 8 — August 8: QA and submission

Actions:

1. verify ACM student membership and undergraduate-track eligibility;
2. validate author/advisor labels;
3. spell-check and reference-check;
4. verify every result against generated tables;
5. verify AI disclosure/citation;
6. export/check poster PDF at readable scale;
7. submit with time buffer;
8. archive exact submitted files and Git commit.

## 18. Pivot rules

Time is more valuable than technical ambition.

- If AMD GPU build is blocked after 60 minutes, use RIKEN `v1.3.0`.
- If full end-to-end SBD inputs cannot be made reliable by August 2, benchmark the authentic upstream SBD matvec/determinant-processing path exposed by its own tests/apps; do not substitute an unrelated toy kernel.
- If no problem-family diversity exists, use grouped instance splits plus strict largest-size holdout and state the limitation.
- If additional parameters are unreliable, publish a rigorous CPU–GPU selector rather than a fragile multi-parameter tuner.
- If the tuner does not beat the static threshold, report this honestly and frame the result as a characterization of crossover and the limits of learned selection; do not cherry-pick.
- If no crossover is observed, add smaller authentic workloads first. Do not spend credits only making already-GPU-dominant jobs larger.

## 19. Scientific integrity and SC26 presentation rules

- Clearly label upstream algorithms, code, and results.
- Never call upstream GPU acceleration the student's contribution.
- Do not state that the L4 is an exascale/HPC accelerator; describe it accurately as a single-node NVIDIA L4 evaluation platform.
- Frame the work as heterogeneous performance portability/runtime selection relevant to HPC workflows.
- Include the limitations: one CPU/GPU system, one node, no real QPU, limited workload families, and deadline-constrained tuning budget.
- Cite all software and data.
- The SC26 public call requires disclosure of AI-generated text in the acknowledgements and citation of the AI system in affected submission sections. Draft the disclosure, but the student must review and take responsibility for all content.
- The student must remain the intellectual owner: explain every generated component and keep a concise technical notebook.

## 20. Definition of done

The code phase is done only when all of the following are true:

- a fresh shell can reproduce the build from documented commands;
- CPU and GPU correctness tests pass;
- benchmark runs are resumable, bounded, and immutable;
- every result contains complete provenance;
- the tuner is evaluated without train/test leakage;
- raw data regenerates all plots/tables;
- no headline claim depends on a failed, profiled, cherry-picked, or single unlabelled run;
- README explains setup, reproduction, expected runtime, and limitations;
- licenses/citations are correct;
- tests and a clean smoke run pass;
- the student receives a final report listing commands, changes, tests, results, failures, cost/time estimates, and next actions.

## 21. What to do in your first response

Do **Stage 0 only**.

1. Restate the project objective in two sentences.
2. Show the Stage 0 work block report.
3. Run only read-only repository/environment audit commands.
4. Report results and identify missing dependencies.
5. Propose the exact initial files and dependency command.
6. Create the durable instruction/context/log files if safe, then summarize their contents.
7. Stop before package installation, cloning large repositories, compiling, or benchmarking and request approval for Stage 1.

Do not merely return another high-level plan. Perform and report the Stage 0 audit now.

# End master prompt

---

# Reading sprint for the student

The goal is not to become an expert in all quantum chemistry, CUDA, and machine learning in eight days. The goal is to understand every term, design choice, graph, and claim in this project well enough to defend it.

## Priority 0: read before or during Stage 0 (30–45 minutes)

### Official SC26 ACM SRC call

Read the deadline, membership, authorship, poster format, originality, AI-text disclosure, and acceptance sections:

https://sc26.supercomputing.org/program/posters/acm-student-research-competition/

Write down:

- August 8 submission close;
- poster draft plus 800-word ACM-format summary;
- ACM membership at submission;
- undergraduate authorship/advisor labeling;
- AI-generated-text disclosure and citation requirement.

## Priority 1: understand the algorithm and gap today (2.5–3 hours)

### 1. IBM Quantum Learning: QDA introduction and SQD overview

- Course introduction: https://quantum.cloud.ibm.com/learning/courses/quantum-diagonalization-algorithms/introduction
- SQD overview: https://quantum.cloud.ibm.com/learning/courses/quantum-diagonalization-algorithms/sqd-overview

Focus on:

- eigenvalues/eigenvectors and ground-state energy;
- subspace methods;
- why samples define a selected subspace;
- what remains quantum and what runs classically;
- why diagonalization becomes the bottleneck.

Be able to explain in one minute: quantum sampling proposes important determinants; the classical SBD stage applies/diagonalizes the Hamiltonian in that selected space.

### 2. Core SQD paper

Robledo-Moreno et al.: https://arxiv.org/abs/2405.05068

Read:

- abstract and introduction;
- algorithm/workflow figure and caption;
- methods describing configuration recovery, subsampling, and diagonalization;
- performance/scaling discussion;
- limitations.

Do not try to reproduce the QPU experiment. Learn where SBD sits in the end-to-end workflow.

### 3. OpenMP GPU SBD paper — the project's central paper

Walkup et al.: https://arxiv.org/abs/2601.16169

Read closely:

- Sections I–III for motivation and CPU profile;
- Section IV, especially the four decomposition parameters and persistent determinant cache;
- Section V for flattened GPU data structures, Slater–Condon evaluation, and memory management;
- evaluation figures/tables;
- Discussion, especially small-problem behavior, cache capacity, `bit_length`, shuffle, and the statement that built-in guidance would be useful;
- Conclusions and Appendices A, B, and D.

Make a one-page glossary containing:

`Slater determinant`, `alpha/beta bitstring`, `selected basis`, `Davidson iteration`, `matrix-free matvec`, `Slater–Condon rules`, `configuration cache`, `bit_length`, `shuffle`, `MPI decomposition`, `OpenMP target offload`, `crossover`.

This paper is the research-gap defense. You should be able to point to the exact paragraph motivating automation.

## Priority 2: understand the alternative GPU implementation while Codex builds (1–1.5 hours)

### Thrust GPU SBD paper

Doi et al.: https://arxiv.org/abs/2601.16637

Read:

- abstract and introduction;
- Section II problem formulation;
- GPU-native data layout and matrix-vector implementation;
- persistent determinant cache;
- evaluation methodology and reported speedups;
- conclusion/limitations.

Compare it with the OpenMP paper:

- directive-based portability versus GPU-native Thrust primitives;
- same SBD bottleneck;
- cache/data-layout commonalities;
- why the implementation choice is upstream work, not our novelty.

Then inspect:

- https://github.com/AMD-HPC/amd-sbd
- https://github.com/r-ccs-cms/sbd/tree/v1.3.0

Read each README and the exact app README/build configuration Codex chooses. Understanding the actual CLI matters more than reading unrelated quantum papers.

## Priority 3: learn just enough CUDA/HPC performance analysis during pilot runs (2 hours)

### NVIDIA CUDA C++ Best Practices Guide

https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/

Read these concepts/sections, not the entire manual:

- heterogeneous application performance and profiling cycle;
- correct timing and asynchronous GPU execution;
- memory transfers and minimizing host–device movement;
- coalesced global-memory access;
- occupancy versus achieved performance;
- instruction throughput and divergence;
- effective bandwidth;
- verification and numerical accuracy.

Relate each concept to SBD: flattened determinant/excitation arrays improve access locality; persistent caches exchange VRAM for recomputation; small jobs underutilize the GPU.

### Nsight tools

- Nsight Systems CLI: https://docs.nvidia.com/nsight-systems/UserGuide/index.html#profiling-from-the-cli
- Nsight Compute CLI: https://docs.nvidia.com/nsight-compute/NsightComputeCli/index.html

Learn the distinction:

- Systems answers **where time goes** across CPU, CUDA calls, kernels, and transfers.
- Compute answers **why a selected kernel behaves as it does** using hardware metrics and may replay kernels.

Do not profile every benchmark run.

## Priority 4: understand the official software path while benchmark sweeps run (1–1.5 hours)

- Qiskit SQD documentation: https://qiskit.github.io/qiskit-addon-sqd/
- Official chemistry tutorial: https://quantum.cloud.ibm.com/docs/tutorials/sample-based-quantum-diagonalization
- HPC-ready C++ addon: https://qiskit.github.io/qiskit-addon-sqd-hpc/
- C++/MPI demo: https://github.com/qiskit-community/qiskit-c-api-demo

Focus on:

- postselection, subsampling, and configuration recovery;
- SBD integration boundary;
- why MPI/OpenMP/C++ are used in HPC workflows;
- which data in the chosen benchmark is sampled/configuration data versus Hamiltonian data.

## Priority 5: learn the tuner and evaluation during final measurements (1 hour)

Read:

- scikit-learn `DecisionTreeRegressor`: https://scikit-learn.org/stable/modules/generated/sklearn.tree.DecisionTreeRegressor.html
- `GroupKFold`: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html
- `RandomForestRegressor` only if used: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html

Be able to explain:

- why the target is `log(runtime)`;
- why the model evaluates every feasible candidate and chooses the minimum;
- why repetitions of the same input cannot be split across train and test;
- why a shallow tree is easier to defend than a neural network;
- selection accuracy versus normalized regret;
- why the oracle is an upper-bound reference, not a deployable policy.

## Priority 6: linear algebra/quantum chemistry only as needed

For this deadline, master these specific ideas:

1. Rayleigh quotient and ground-state eigenvalue.
2. Krylov/subspace iterative eigensolvers.
3. Davidson method at the level of: build a subspace, solve a projected eigenproblem, form a residual, precondition/expand, repeat.
4. Matrix-free Hamiltonian application.
5. Slater determinants and occupation-number bitstrings.
6. Slater–Condon selection rule intuition: determinants differing by more than two spin-orbital occupations have zero Hamiltonian coupling for the electronic Hamiltonian.

Use the definitions and references in the two SBD papers first. Do not spend a day on a general linear-algebra textbook before the build works.

## Daily defense exercise (15 minutes/day)

At the end of each day, answer aloud without notes:

1. What is SQD, and what part are we optimizing?
2. Why can CPU win for small cases and GPU for large cases?
3. Which problem features exist before execution?
4. What exactly is the tuner trained on?
5. How did we prevent leakage and OOM?
6. What is upstream work and what is our contribution?
7. What does each plot prove—and what does it not prove?
8. What are the three largest limitations?

If you cannot answer one, ask Codex to explain it using the exact source code and latest measurements, then update your glossary.

---

# Immediate user checklist

Before pasting the master prompt:

- Confirm the VM disk has enough free space and that the instance is the expected `g2-standard-32`.
- Confirm GCP billing alerts exist, but remember they do not automatically stop the VM.
- Join ACM as a student before submission if not already a member.
- Keep the project in the remote filesystem and initialize Git if it is not already a repository.
- Do not begin a large benchmark until the smoke test and correctness comparison pass.

The first evidence milestone is not “the tuner is trained.” It is: **the same authentic SBD input runs correctly on CPU and GPU, with traceable commands and comparable end-to-end timing.**
