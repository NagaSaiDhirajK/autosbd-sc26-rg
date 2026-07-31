# Stage 0 environment audit

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

Hardware capacity is sufficient for Stage 1 inspection and later bounded L4 experiments. Compilation is blocked until the standard C++/CMake/MPI/BLAS/Python environment is installed. The AMD NVIDIA OpenMP-offload route remains uncertain because neither Clang nor `nvc++` is present; this is expected and governed by the 60-minute pivot rule.
