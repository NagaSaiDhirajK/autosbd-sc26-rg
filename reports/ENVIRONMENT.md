# Environment and toolchain record

This report preserves the initial Stage 0 audit below and appends the installed Stage 1/2 state. Statements that a dependency was initially missing are historical observations, not the current environment.

Audit time: 2026-07-31 around 22:04 UTC

Working directory: `/home/nagan/autosbd-sc26-rg`

Git HEAD: `3a523a2` (`main`, tracking `origin/main`)

Repository state at audit: clean tracked tree; untracked `AutoSBD_SC26_Codex_Handoff.md`

No package installation, download, clone, compilation, GPU kernel, or benchmark was performed during this audit.

## Capacity and topology

| Item | Observed value |
|---|---|
| OS/kernel | Ubuntu 22.04.5 LTS; Linux 6.8.0-1064-gcp x86_64 |
| Host | `instance-20260731-140922` |
| CPU | Intel Xeon virtual CPU @ 2.20 GHz |
| CPU topology | 1 socket, 16 physical cores, 2 threads/core, 32 online logical CPUs, 1 NUMA node |
| CPU cache | L1d 512 KiB total, L1i 512 KiB total, L2 16 MiB total, L3 38.5 MiB |
| RAM | 125 GiB total; 122 GiB available; no swap |
| Repository filesystem | 97 GiB total; 79 GiB available; 19% used |
| GPU | NVIDIA L4, persistence mode on |
| VRAM | 23,034 MiB total; 22,564 MiB free |
| GPU audit state | 31 C, P8, 0% utilization, no running processes; 14.59 W / 72 W in structured query |
| Initial benchmark VRAM ceiling | `min(20 GiB, 80% of current free)` = about 18,051 MiB at audit; recalculate before every run |
| NVIDIA driver | 580.173.02 |
| Driver CUDA compatibility | 13.0 |
| CUDA toolkit | nvcc 12.9.41 |

The driver-reported CUDA compatibility level and installed toolkit version are allowed to differ. No corrective action is needed for 13.0 versus 12.9.

## Tool readiness

| Tool/dependency | State at audit |
|---|---|
| Git | present, 2.34.1 |
| GCC | present, 12.3.0 |
| G++ / C++ build essentials | missing |
| CMake | missing |
| Ninja | missing |
| `pkg-config` | missing |
| OpenMPI / `mpicxx` | missing |
| Clang++ | missing; not part of the initial install proposal |
| NVIDIA `nvc++` | missing; NVIDIA HPC SDK is not approved or proposed |
| CUDA nvcc | present, 12.9.41 |
| Nsight Systems | present, 2025.1.3 |
| Nsight Compute | present, 2025.2.0.0 |
| BLAS/LAPACK/OpenBLAS shared libraries | not detected by `ldconfig`; development packages absent |
| Python | present, 3.10.12 |
| Python venv/ensurepip | not usable; `ensurepip` missing and `python3-venv` not installed |
| Python pip | system `python3 -m pip` unavailable |
| jq | present, 1.6 |
| tmux | present, 3.2a |

APT package indexes appear incomplete or stale: before an update, `apt-cache policy` returned no candidate for several standard build packages. Consequently, exact candidate versions and download/installed sizes must be checked after `apt-get update` and before installation.

The configured Ubuntu archive mirror is `us-east1.gce.archive.ubuntu.com`, while cached archive lists still use `us-central1.gce.archive.ubuntu.com`; this explains why current candidates are missing and makes `apt-get update` necessary. A local source named `cudnn-local-ubuntu2404-9.13.0` is also enabled even though the host is Ubuntu 22.04. Do not modify that source or install/upgrade CUDA/cuDNN incidentally for AutoSBD; flag unexpected CUDA/cuDNN package changes during the APT simulation.

Because the VM has no swap, later wrappers must enforce host-memory estimation/monitoring as well as the GPU guard rather than relying on swap-backed recovery.

## Proposed initial system dependency commands—not yet run

These intentionally omit Clang and NVIDIA HPC SDK. Existing Git, jq, and tmux need not be reinstalled.

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends -y \
  build-essential \
  cmake \
  ninja-build \
  pkg-config \
  openmpi-bin \
  libopenmpi-dev \
  libopenblas-dev \
  liblapack-dev \
  liblapacke-dev \
  python3-venv \
  python3-pip
```

After the metadata update, first run an APT simulation and report its package count, download size, installed-size change, and any unexpected removals before executing the install command. Python package selection will be made only after upstream requirements are inspected; no broad Python stack is proposed yet.

## Readiness conclusion

Hardware capacity is sufficient for Stage 1 inspection and later bounded L4 experiments. At the initial audit, compilation was blocked pending the standard C++/CMake/MPI/BLAS/Python environment documented below. The AMD NVIDIA OpenMP-offload route was uncertain because neither Clang nor `nvc++` was present and was governed by the 60-minute pivot rule.

## Stage 1 dependency installation

Installation time: 2026-07-31 around 22:19 UTC

APT metadata refresh downloaded 49.0 MB. The transaction installed 83 new packages, upgraded 0, removed 0, downloaded 108 MB, and added approximately 451 MB. The simulation and completed transaction made no CUDA toolkit, driver, or cuDNN change. Disk availability after installation was 78 GiB.

| Installed component | Version |
|---|---|
| build-essential | 12.9ubuntu3 |
| G++ / MPI wrapper compiler | GCC 11.4.0 |
| CMake | 3.22.1 |
| Ninja | 1.10.1 |
| pkg-config | 0.29.2 |
| OpenMPI runtime/development | 4.1.2-2ubuntu1 |
| OpenBLAS development | 0.3.20+ds-1 |
| LAPACK/LAPACKE development | 3.10.0-2ubuntu1 |
| system Python pip | 22.0.2 |
| Python venv metapackage | 3.10.6-1~22.04.1 |

The project-local `.venv` uses Python 3.10.12 with bootstrap packages `pip==26.2`, `setuptools==83.0.0`, `wheel==0.47.0`, and `packaging==26.2`. At this point in Stage 1, scientific Python dependencies remained intentionally uninstalled; the Stage 2 package state is recorded below.

The standard build environment is ready. The statement above that NVIDIA OpenMP target offload was unavailable describes the initial audit and was superseded by the user-authorized SDK installation below.

## NVIDIA HPC SDK installation

Installation time: 2026-07-31 from 22:35 to 22:42 UTC

The official NVIDIA APT package `nvhpc-26-5` version `26.5-0` installed successfully. The transaction added one package, upgraded or removed none, held seven unrelated packages back, downloaded 5,095 MB, and added approximately 14.8 GB (`Installed-Size: 14,463,145 KiB`). It installed no driver package and changed no existing CUDA/cuDNN package. Approximately 59 GiB remained on the repository filesystem after installation.

| Component | Verified value |
|---|---|
| NVIDIA C++ compiler | `nvc++ 26.5-0` at `/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/compilers/bin/nvc++` |
| Bundled CUDA toolkit | CUDA 13.2, nvcc `V13.2.78` |
| MPI wrapper | `/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/comm_libs/mpi/bin/mpic++`; backend `nvc++` |
| MPI implementation | NVIDIA HPC-X 2.50 / Open MPI `5.0.10rc2` |
| CUDA-aware MPI | built with CUDA 13.2; `opal_built_with_cuda_support=true` and `opal_cuda_support=true` |
| L4 target support | `-gpu=cc89` accepted by `nvc++` and verified in the built cubin |

The NVHPC compiler-bin and MPI-bin directories must both be in `PATH` when invoking the bundled MPI wrapper. `scripts/build_upstream.sh` supplies that environment itself. NVIDIA OpenMP target offload is now available; Clang is not required for the selected build.

## Stage 2 Python and harness environment

Update date: 2026-08-01

The Stage 2 package metadata is in `pyproject.toml`, and the runtime dependency is pinned as `PyYAML==6.0.2` in `requirements-lock.txt`. The harness otherwise uses the Python 3.10 standard library. `pytest` is not required or installed; the verified source-layout test command is:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

It completed 67 tests successfully in 4.310 seconds on this node. The tests use mock processes for success, scientific nonconvergence, nonzero exit, timeout/process-group cleanup, and simulated OOM; they do not launch a GPU kernel.

The project currently runs directly from `src/` through `PYTHONPATH=src`; an editable package installation is not required for the documented scripts. Runtime commands are available through `scripts/run_one.py` and `scripts/run_sweep.py`, with corresponding package entry points declared as `autosbd-run-one` and `autosbd-run-sweep` for an installed package.

## Selected primary compiler path

There is one primary NVIDIA HPC SDK path, not separate RIKEN and AMD toolchains. The official AMD CPU and GPU executables are both compiled from commit `729cfa3a5011fb805eb9e686a7711f6919836dcb` using NVIDIA HPC SDK 26.5:

- compiler: `/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/compilers/bin/nvc++`;
- MPI wrapper: `/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/comm_libs/mpi/bin/mpic++` with the same `nvc++` backend;
- GPU compilation: SDK-bundled CUDA 13.2 targeting the L4's `sm_89`/`cc89`;
- CPU compilation: NVHPC OpenMP with `-tp=native` from the same AMD source checkout.

The system CUDA 12.9 toolkit remains installed but is not the compiler path used for the primary AMD GPU binary. The older RIKEN CUDA/Thrust probe is historical fallback evidence only and contributes no executable, workload, or measurement to the Stage 2 primary runner result.

Before every authentic run, the runner rechecks the GPU query, idleness, free VRAM, temperature, power, CPU load, core availability, and estimated memory. GPU admission uses `min(20 GiB, 80% of current free VRAM)`. A node-wide lock prevents CPU and GPU candidates from overlapping, and final timings must remain sequential.
