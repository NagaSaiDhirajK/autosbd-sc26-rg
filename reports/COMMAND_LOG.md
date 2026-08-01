# Command log

Commands are recorded in UTC. Credentials and tokens must be redacted. Timings below are wall-clock durations reported by the command runner; commands within a parallel audit batch share the batch timestamp.

## 2026-07-31T22:03Z — Read project handoff, part 1

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 0.2 s
- Outcome: Read lines 1–240 of the user-supplied handoff; no files changed.

```bash
sed -n '1,240p' AutoSBD_SC26_Codex_Handoff.md
```


## 2026-07-31T22:03Z — Read project handoff, part 2

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 0.1 s
- Outcome: Read lines 241–520 of the handoff; no files changed.

```bash
sed -n '241,520p' AutoSBD_SC26_Codex_Handoff.md
```

## 2026-07-31T22:03Z — Read project handoff, part 3

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 0.1 s
- Outcome: Read lines 521–800, including the complete master prompt and Stage 0 instructions; no files changed.

```bash
sed -n '521,800p' AutoSBD_SC26_Codex_Handoff.md
```

## 2026-07-31T22:04Z — Repository audit

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: less than 0.01 s
- Outcome: Found tracked README/license and one untracked handoff; no `AGENTS.md` existed.

```bash
set -o pipefail
pwd
git rev-parse --show-toplevel 2>/dev/null || true
git status --short --branch 2>/dev/null || true
git diff --stat 2>/dev/null || true
rg --files -g 'AGENTS.md' -g '!external/**' -g '!data/raw/**' 2>/dev/null || true
rg --files -g '!external/**' -g '!data/raw/**' 2>/dev/null | sed -n '1,240p'
```

## 2026-07-31T22:04Z — System and GPU audit

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 0.22 s
- Outcome: Confirmed 16 physical/32 logical CPUs, 125 GiB RAM, 79 GiB disk free, idle 23,034 MiB NVIDIA L4, and driver 580.173.02.

```bash
set -o pipefail
uname -a
cat /etc/os-release
lscpu
free -h
df -h .
getconf _NPROCESSORS_ONLN
nvidia-smi
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.free,temperature.gpu,power.draw,power.limit --format=csv,noheader
```

## 2026-07-31T22:04Z — Toolchain audit

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0 (optional missing tools were allowed)
- Duration: 0.43 s
- Outcome: Found Git, CUDA nvcc, Nsight tools, jq, tmux, GCC, and Python; did not find G++, CMake, Ninja, MPI, Clang++, nvc++, pkg-config, or pip.

```bash
set -o pipefail
command -v git || true
command -v cmake || true
command -v ninja || true
command -v mpicxx || true
command -v clang++ || true
command -v nvc++ || true
command -v nsys || true
command -v ncu || true
command -v pkg-config || true
command -v jq || true
command -v tmux || true
command -v python3 || true
command -v nvcc || true
git --version
cmake --version 2>/dev/null || true
ninja --version 2>/dev/null || true
mpicxx --version 2>/dev/null | sed -n '1,4p' || true
clang++ --version 2>/dev/null | sed -n '1,4p' || true
nvc++ --version 2>/dev/null | sed -n '1,6p' || true
nsys --version 2>/dev/null || true
ncu --version 2>/dev/null || true
pkg-config --version 2>/dev/null || true
jq --version 2>/dev/null || true
tmux -V 2>/dev/null || true
nvcc --version 2>/dev/null || true
gcc --version | sed -n '1p'
g++ --version | sed -n '1p'
python3 --version
python3 -m pip --version 2>/dev/null || true
```

## 2026-07-31T22:05Z — Existing repository content audit

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: less than 0.01 s
- Outcome: Confirmed one initial commit, GitHub origin, and exact tracked README/license content.

```bash
set -o pipefail
git log -5 --oneline --decorate
git remote -v
git ls-files -s
rg --files --hidden -g '!.git/**'
sed -n '1,240p' README.md
sed -n '1,160p' LICENSE
```

## 2026-07-31T22:05Z — Installed-package and library audit

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0 (missing packages were expected)
- Duration: 0.07 s
- Outcome: Confirmed missing build/MPI/BLAS/pip packages, missing `ensurepip`, and incomplete/stale APT candidate metadata.

```bash
set -o pipefail
dpkg-query -W -f='${binary:Package}\t${Version}\n' build-essential cmake ninja-build pkg-config openmpi-bin libopenmpi-dev libopenblas-dev liblapack-dev python3-venv python3-pip jq tmux 2>&1 || true
apt-cache policy build-essential cmake ninja-build pkg-config openmpi-bin libopenmpi-dev libopenblas-dev liblapack-dev python3-venv python3-pip | sed -n '1,240p'
ldconfig -p 2>/dev/null | rg 'lib(openblas|lapack|blas)\.so' || true
python3 -c 'import ensurepip, venv; print("python_venv_modules=available")' 2>&1 || true
```

## 2026-07-31T22:05Z — Host detail audit

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: less than 0.01 s
- Outcome: Confirmed CPU/core mapping, filesystem capacity, hostname, and unchanged Git state.

```bash
set -o pipefail
hostname
nproc
nproc --all
lscpu -p=CPU,CORE,SOCKET,NODE | sed -n '1,40p'
stat -f -c 'filesystem=%T block_size=%S blocks_available=%a' .
git status --porcelain=v1 -uall
```

## 2026-07-31T22:06Z — Create Stage 0 report directory

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: less than 0.01 s
- Outcome: Created `reports/`; subsequent `apply_patch` file edits added the Stage 0 durable documents.

```bash
mkdir -p reports
```

## 2026-07-31T22:07Z — Validate Stage 0 files and scope

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: less than 0.01 s per parallel command group
- Outcome: Confirmed all six documents exist, the student-submission exclusion and safety rules are explicit, Git whitespace checks pass, and the only changes are new untracked project files.

```bash
set -o pipefail
rg --files AGENTS.md PROJECT_CONTEXT.md reports | sort
wc -l AGENTS.md PROJECT_CONTEXT.md reports/*.md
git status --short --branch
git diff --check
sed -n '1,220p' AGENTS.md
sed -n '1,260p' reports/ENVIRONMENT.md
```

```bash
set -o pipefail
rg -n -i 'abstract|poster|800-word|submission|student' AGENTS.md PROJECT_CONTEXT.md reports/*.md
rg -n 'NVIDIA HPC SDK|60 minutes|immutable|held-out|approval' AGENTS.md PROJECT_CONTEXT.md reports/*.md
```

```bash
set -o pipefail
rg -n --no-messages '^(deb|Types:|URIs:|Suites:|Components:)' /etc/apt/sources.list /etc/apt/sources.list.d/* || true
rg -n --no-messages 'ubuntu2404|us-east1|us-central1|cuda|cudnn' /etc/apt/sources.list /etc/apt/sources.list.d/* /var/lib/apt/lists/*Release 2>/dev/null | sed -n '1,180p' || true
apt-cache policy liblapacke-dev | sed -n '1,40p'
```

## 2026-07-31T22:08Z — Inspect cached APT origins

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: less than 0.01 s
- Outcome: Confirmed current Ubuntu sources use `us-east1`, cached archive lists use `us-central1`, and a local Ubuntu-24.04-named cuDNN repository is enabled on this Ubuntu 22.04 host.

```bash
set -o pipefail
find /var/lib/apt/lists -maxdepth 1 -type f -printf '%f\n' | sort | sed -n '1,200p'
apt-cache policy | sed -n '1,180p'
```

## 2026-07-31T22:09Z — Read remainder of handoff

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: less than 0.01 s
- Outcome: Confirmed the file has 929 lines and reviewed its remaining reading/organization checklist. No later instruction changes the Stage 0 execution requirements or the user's student-authorship override.

```bash
set -o pipefail
wc -l AutoSBD_SC26_Codex_Handoff.md
sed -n '801,1200p' AutoSBD_SC26_Codex_Handoff.md
```

## 2026-07-31T22:10Z — Final Stage 0 validation

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Outcome to verify: All required documents are nonempty, contain no merge markers or carriage returns, encode the scope/approval rules, include the exact dependency proposal, and leave existing tracked files unchanged.

```bash
set -o pipefail
test -s AGENTS.md
test -s PROJECT_CONTEXT.md
test -s reports/ENVIRONMENT.md
test -s reports/COMMAND_LOG.md
test -s reports/EXPERIMENT_LOG.md
test -s reports/DECISIONS.md
! rg -n '^(<<<<<<<|=======|>>>>>>>)' AGENTS.md PROJECT_CONTEXT.md reports/*.md
! rg -n $'\r' AGENTS.md PROJECT_CONTEXT.md reports/*.md
rg -n 'Never draft, write, rewrite, or generate' AGENTS.md
rg -n 'liblapacke-dev' reports/ENVIRONMENT.md
rg -n 'No SBD executable was cloned, compiled, or run' reports/EXPERIMENT_LOG.md
sha256sum README.md LICENSE AutoSBD_SC26_Codex_Handoff.md
git diff -- README.md LICENSE
git status --short --branch
git config --get user.name || true
git config --get user.email || true
```

## 2026-07-31T22:11Z — Create Stage 0 checkpoint

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Expected exit code: 0
- Expected outcome: Stage the user-supplied handoff and six new durable documents, validate whitespace, and create local commit `chore: capture L4 environment`. No push or network action.
- Identity handling: Reuse the author name/email recorded in the repository's initial commit for this one command; do not create or modify Git configuration.

```bash
rg -n ' +$' AGENTS.md PROJECT_CONTEXT.md reports/*.md || true
mapfile -t autosbd_author < <(git log -1 --format='%an%n%ae')
test "${#autosbd_author[@]}" -ge 2
git add AGENTS.md AutoSBD_SC26_Codex_Handoff.md PROJECT_CONTEXT.md reports/COMMAND_LOG.md reports/DECISIONS.md reports/ENVIRONMENT.md reports/EXPERIMENT_LOG.md
git diff --cached --check
git diff --cached --stat
git -c user.name="${autosbd_author[0]}" -c user.email="${autosbd_author[1]}" commit --no-gpg-sign -m 'chore: capture L4 environment'
git status --short --branch
```

## 2026-07-31T22:22Z — Add and pin upstream submodules

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0 for clone/checkout; the later assumed `LICENSE` hash path failed because both projects use `LICENSE.txt`
- Duration: 3.9 s
- Outcome: Added AMD at `729cfa3a...` and RIKEN at exact tag `v1.3.0`/`b71e1c3e...`; combined worktrees 44 MB. No source edits.
- Full log: `logs/stage1_submodules.log`

```bash
set -o pipefail
mkdir -p external
timeout 600s git submodule add https://github.com/AMD-HPC/amd-sbd.git external/amd-sbd > logs/stage1_submodules.log 2>&1
timeout 600s git -C external/amd-sbd fetch origin sc26-artifacts >> logs/stage1_submodules.log 2>&1
git -C external/amd-sbd checkout 729cfa3a5011fb805eb9e686a7711f6919836dcb >> logs/stage1_submodules.log 2>&1
timeout 600s git submodule add https://github.com/r-ccs-cms/sbd.git external/riken-sbd >> logs/stage1_submodules.log 2>&1
timeout 600s git -C external/riken-sbd fetch origin tag v1.3.0 >> logs/stage1_submodules.log 2>&1
git -C external/riken-sbd checkout b71e1c3ed857fcb4fb05731dc285831c1afe9ebd >> logs/stage1_submodules.log 2>&1
submodule_status=$?
tail -80 logs/stage1_submodules.log
if [ "$submodule_status" -ne 0 ]; then exit "$submodule_status"; fi
git submodule status
git -C external/amd-sbd rev-parse HEAD
git -C external/amd-sbd branch -r --contains HEAD
git -C external/riken-sbd rev-parse HEAD
git -C external/riken-sbd describe --tags --exact-match HEAD
sha256sum external/amd-sbd/LICENSE external/riken-sbd/LICENSE
du -sh external/amd-sbd external/riken-sbd .git/modules/external/amd-sbd .git/modules/external/riken-sbd
git status --short --branch
```

## 2026-07-31T22:23Z — Build AMD and RIKEN CPU applications

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0 for both parallel builds
- Duration: 14.3 s AMD; 14.6 s RIKEN
- Outcome: Produced working release CPU executables linked to OpenMPI, GNU OpenMP, and OpenBLAS.
- Full logs: `logs/stage1_amd_cpu_build.log`, `logs/stage1_riken_cpu_build.log`

```bash
timeout 600s make -C external/amd-sbd/applications/selected_basis_diagonalization/src GPU=0 CXX=mpicxx LDFLAGS='-fopenmp -lopenblas' VERBOSE=1 > logs/stage1_amd_cpu_build.log 2>&1
```

```bash
timeout 600s make -C external/riken-sbd/apps/chemistry_tpb_selected_basis_diagonalization clean > logs/stage1_riken_cpu_build.log 2>&1
timeout 600s make -C external/riken-sbd/apps/chemistry_tpb_selected_basis_diagonalization diag CCCOM=mpicxx CCFLAGS='-std=c++17 -fopenmp -O3 -march=native' SYSLIB='-fopenmp -lopenblas' >> logs/stage1_riken_cpu_build.log 2>&1
```

## 2026-07-31T22:24Z — Run authentic RIKEN CPU correctness smoke

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 40.90 s
- Outcome: N₂ `1em3` converged to residual `9.745846817253461e-09`, energy `-109.0416210980518 Ha`, peak RSS 37,472 KiB. GPU remained idle.
- Full logs: `logs/stage1_riken_cpu_n2_1em3.stdout.log`, `.stderr.log`, `.time.log`

```bash
timeout 300s env OMP_NUM_THREADS=1 OMP_PLACES=cores OMP_PROC_BIND=close OMP_DYNAMIC=false OPENBLAS_NUM_THREADS=1 /usr/bin/time -v -o logs/stage1_riken_cpu_n2_1em3.time.log mpirun -np 1 -x OMP_NUM_THREADS -x OMP_PLACES -x OMP_PROC_BIND -x OMP_DYNAMIC -x OPENBLAS_NUM_THREADS external/riken-sbd/apps/chemistry_tpb_selected_basis_diagonalization/diag --fcidump external/riken-sbd/data/n2/fcidump.txt --adetfile external/riken-sbd/data/n2/1em3-alpha.txt --method 0 --block 10 --iteration 4 --tolerance 1.0e-8 --max_time 240 --adet_comm_size 1 --bdet_comm_size 1 --task_comm_size 1 --shuffle 0 --carryover_type 0 --rdm 0 --bit_length 20 > logs/stage1_riken_cpu_n2_1em3.stdout.log 2> logs/stage1_riken_cpu_n2_1em3.stderr.log
```

## 2026-07-31T22:27Z — Rebuild all pinned upstream targets with tracked script

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: about 1 minute
- Outcome: Shell syntax passed; AMD CPU, RIKEN CPU, and RIKEN `sm_89` GPU builds completed. `cuobjdump` found two `sm_89` cubins. Full warnings retained.
- Full log: `logs/stage1_scripted_build.log`

```bash
chmod +x scripts/build_upstream.sh
bash -n scripts/build_upstream.sh
git add .gitmodules external/amd-sbd external/riken-sbd
timeout 600s scripts/build_upstream.sh all > logs/stage1_scripted_build.log 2>&1
```

## 2026-07-31T22:18Z — Refresh APT metadata and simulate build dependencies

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 15.9 s for update/simulation; 0.6 s for URI/size inspection
- Outcome: Downloaded 49.0 MB of metadata. Simulation proposed 83 new packages, 0 upgrades, 0 removals, 108 MB download, and 451 MB installed disk. No CUDA/cuDNN package change appeared.
- Full logs: `logs/stage1_apt_update.log`, `logs/stage1_apt_simulate.log`, `logs/stage1_apt_uris.log`

```bash
set -o pipefail
mkdir -p logs
timeout 600s sudo -n apt-get update > logs/stage1_apt_update.log 2>&1
apt_update_status=$?
tail -80 logs/stage1_apt_update.log
if [ "$apt_update_status" -ne 0 ]; then exit "$apt_update_status"; fi
sudo -n apt-get install --simulate --no-install-recommends -y build-essential cmake ninja-build pkg-config openmpi-bin libopenmpi-dev libopenblas-dev liblapack-dev liblapacke-dev python3-venv python3-pip > logs/stage1_apt_simulate.log 2>&1
apt_sim_status=$?
rg -n '^(The following packages|  [a-z0-9]|[0-9]+ upgraded|Inst |Remv |Conf |Need to get|After this operation)' logs/stage1_apt_simulate.log | tail -160
if [ "$apt_sim_status" -ne 0 ]; then exit "$apt_sim_status"; fi
```

```bash
set -o pipefail
sed -n '1,58p' logs/stage1_apt_simulate.log
rg -n '^(Remv |[0-9]+ upgraded)|cuda|cudnn|nvidia' logs/stage1_apt_simulate.log || true
sudo -n apt-get --print-uris --download-only --no-install-recommends -y install build-essential cmake ninja-build pkg-config openmpi-bin libopenmpi-dev libopenblas-dev liblapack-dev liblapacke-dev python3-venv python3-pip > logs/stage1_apt_uris.log 2>&1
awk '$1 ~ /^\047http/ || $1 ~ /^\047file/ {bytes += $3; count += 1} END {printf "archives=%d download_bytes=%.0f download_mib=%.2f\\n", count, bytes, bytes/1048576}' logs/stage1_apt_uris.log
rg -n '^(Need to get|After this operation|[0-9]+ upgraded)|cuda|cudnn|nvidia' logs/stage1_apt_uris.log || true
tail -8 logs/stage1_apt_uris.log
```

## 2026-07-31T22:19Z — Install and verify system build dependencies

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 20.2 s
- Outcome: Installed and verified G++, CMake, Ninja, MPI, pkg-config, OpenBLAS, LAPACK/LAPACKE, pip, and venv. nvcc remained 12.9.41; 78 GiB disk remained.
- Full log: `logs/stage1_apt_install.log`

```bash
set -o pipefail
timeout 600s sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y build-essential cmake ninja-build pkg-config openmpi-bin libopenmpi-dev libopenblas-dev liblapack-dev liblapacke-dev python3-venv python3-pip > logs/stage1_apt_install.log 2>&1
apt_install_status=$?
tail -100 logs/stage1_apt_install.log
if [ "$apt_install_status" -ne 0 ]; then exit "$apt_install_status"; fi
command -v g++
command -v cmake
command -v ninja
command -v mpicxx
command -v pkg-config
g++ --version | sed -n '1p'
cmake --version | sed -n '1p'
ninja --version
mpicxx --version | sed -n '1p'
pkg-config --modversion blas
pkg-config --modversion lapack
pkg-config --modversion lapacke
python3 -m pip --version
python3 -c 'import ensurepip, venv; print("python_venv_modules=available")'
nvcc --version | tail -4
df -h .
```

## 2026-07-31T22:21Z — Bootstrap project-local Python environment

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 7.5 s
- Outcome: Created a 21 MB `.venv` and installed only bootstrap packaging tools. No scientific Python packages were installed.
- Full log: `logs/stage1_python_bootstrap.log`

```bash
set -o pipefail
timeout 600s python3 -m venv .venv
timeout 600s .venv/bin/python -m pip install --upgrade pip setuptools wheel > logs/stage1_python_bootstrap.log 2>&1
python_bootstrap_status=$?
tail -60 logs/stage1_python_bootstrap.log
if [ "$python_bootstrap_status" -ne 0 ]; then exit "$python_bootstrap_status"; fi
.venv/bin/python --version
.venv/bin/python -m pip --version
.venv/bin/python -m pip freeze --all
dpkg-query -W -f='${binary:Package}\t${Version}\n' build-essential cmake ninja-build pkg-config openmpi-bin libopenmpi-dev libopenblas-dev liblapack-dev liblapacke-dev python3-venv python3-pip | sort
du -sh .venv logs
git status --short --branch
```

## 2026-07-31T22:35Z — Configure and size the official NVIDIA HPC SDK repository

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: Installed NVIDIA's public key and APT source, refreshed metadata, and simulated `nvhpc-26-5`. The simulation proposed one new package, no upgrades/removals, a 5,095 MB download, and about 14.8 GB installed size.
- Provenance note: the turn containing the temporary-file download/dearmor steps was interrupted before those unprivileged commands were copied here. Sudo audit records preserve the exact privileged commands below. The permanent source is `deb [signed-by=/usr/share/keyrings/nvidia-hpcsdk-archive-keyring.gpg] https://developer.download.nvidia.com/hpc-sdk/ubuntu/amd64 /`; key fingerprint is `0DCE 8250 6D09 CEB1 33D0 B3FD F338 EA0E 0105 AB24`.

```bash
sudo -n install -m 0644 /tmp/tmp.9oJ3shSbKx/nvidia-hpcsdk-keyring.gpg /usr/share/keyrings/nvidia-hpcsdk-archive-keyring.gpg
sudo -n install -m 0644 /tmp/tmp.9oJ3shSbKx/nvhpc.list /etc/apt/sources.list.d/nvhpc.list
sudo -n apt-get update
sudo -n apt-get install --simulate --no-install-recommends -y nvhpc-26-5
sudo -n apt-get --print-uris --download-only --no-install-recommends -y install nvhpc-26-5
```

## 2026-07-31T22:36Z — Install NVIDIA HPC SDK 26.5

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: download 68 s; complete APT transaction 5 min 11 s
- Outcome: Installed `nvhpc-26-5 26.5-0`; 5,095 MB downloaded, package installed size 14,463,145 KiB, no driver/CUDA/cuDNN package changed. Full log: `logs/stage1_nvhpc_install.log`.

```bash
sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y nvhpc-26-5 > logs/stage1_nvhpc_install.log 2>&1
```

## 2026-07-31T22:42Z — Verify NVHPC, L4 target support, and bundled MPI

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: Verified `nvc++ 26.5-0`, CUDA 13.2, accepted `cc89`, HPC-X/Open MPI wrapper backed by `nvc++`, and CUDA-aware MPI support. About 59 GiB disk remained.

```bash
nvhpc_root=/opt/nvidia/hpc_sdk/Linux_x86_64/26.5
find "$nvhpc_root" -maxdepth 6 -type f \( -name 'nvc++' -o -name 'mpic++' -o -name 'ompi_info' -o -name 'mpirun' \) -print | sort
"$nvhpc_root/compilers/bin/nvc++" -V
"$nvhpc_root/compilers/bin/nvc++" -help -gpu
PATH="$nvhpc_root/compilers/bin:$nvhpc_root/comm_libs/mpi/bin:$PATH" "$nvhpc_root/comm_libs/mpi/bin/mpic++" --showme:command
PATH="$nvhpc_root/compilers/bin:$nvhpc_root/comm_libs/mpi/bin:$PATH" "$nvhpc_root/comm_libs/mpi/bin/mpic++" --showme:compile
PATH="$nvhpc_root/compilers/bin:$nvhpc_root/comm_libs/mpi/bin:$PATH" "$nvhpc_root/comm_libs/mpi/bin/mpic++" --showme:link
"$nvhpc_root/comm_libs/13.2/hpcx/latest/ompi/bin/ompi_info" --parsable --all
df -h /home/nagan/autosbd-sc26-rg
```

## 2026-07-31T22:46Z — Build primary AMD CPU and L4 GPU executables

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 58.32 s
- Outcome: Built AMD CPU and OpenMP-offload `sm_89` GPU binaries from the same pinned unmodified commit. Peak compiler RSS was 535,132 KiB. The combined log has 46 upstream unused-variable warnings and no errors. Full log: `logs/stage1_amd_nvhpc_build.log`.

```bash
set -o pipefail
bash -n scripts/build_upstream.sh
timeout 900s /usr/bin/time -v scripts/build_upstream.sh amd-all > logs/stage1_amd_nvhpc_build.log 2>&1
build_status=$?
tail -n 100 logs/stage1_amd_nvhpc_build.log
exit "$build_status"
```

## 2026-07-31T22:47Z — Verify primary AMD binaries

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: Verified hashes, sizes, MPI/OpenMP/OpenBLAS linkage, offload runtime libraries, and one embedded `sm_89` cubin. No library was missing.

```bash
amd_build=build/upstream/amd-729cfa3a-nvhpc-26.5
sha256sum "$amd_build/diag_cpu" "$amd_build/diag_gpu"
stat -c '%n %s bytes' "$amd_build/diag_cpu" "$amd_build/diag_gpu"
ldd "$amd_build/diag_cpu" | rg 'mpi|openblas|nvomp|not found'
ldd "$amd_build/diag_gpu" | rg 'mpi|openblas|nvomp|cuda|cudadevice|not found'
cuobjdump --list-elf "$amd_build/diag_gpu"
readelf -S "$amd_build/diag_gpu" | rg -i 'cuda|nv|omp'
git -C external/amd-sbd status --short --branch
```

## 2026-07-31T22:48Z — Bound one-thread AMD CPU Fe₄S₄ attempt

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Final exit code: 143 after deliberate termination
- Duration: about 101 s
- Outcome: Reached four Davidson steps and residual `0.03715544425092371`; projected completion exceeded the pilot budget, so the exact timeout wrapper process was terminated and all partial logs retained.
- Logs: `logs/stage1_amd_cpu_fe4s4.*`

```bash
timeout --signal=TERM --kill-after=15s 300s env \
  OMP_NUM_THREADS=1 OMP_PLACES=cores OMP_PROC_BIND=close OMP_DYNAMIC=false \
  OMP_TARGET_OFFLOAD=DISABLED OPENBLAS_NUM_THREADS=1 \
  /usr/bin/time -v -o logs/stage1_amd_cpu_fe4s4.time.log \
  build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu \
  --fcidump external/amd-sbd/samples/selected_basis_diagonalization/fcidump_Fe4S4.txt \
  --adetfile external/amd-sbd/samples/selected_basis_diagonalization/AlphaDets.txt \
  --method 0 --block 10 --iteration 4 --tolerance 1.0e-8 --max_time 240 \
  --adet_comm_size 1 --bdet_comm_size 1 --task_comm_size 1 \
  --init 0 --shuffle 0 --carryover_ratio 0.5 --rdm 0 --bit_length 20 \
  > logs/stage1_amd_cpu_fe4s4.stdout.log 2> logs/stage1_amd_cpu_fe4s4.stderr.log
kill -TERM 25909
```

## 2026-07-31T22:50Z — Test four-restart AMD CPU convergence on 16 cores

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0, but numerical acceptance failed
- Duration: 62.77 s
- Outcome: The application exhausted four restarts at residual `1.7589424916975e-7`, above `1e-8`; energy `-326.698253673155 Ha`. Preserved as a non-passing attempt.

```bash
timeout --signal=TERM --kill-after=15s 300s env \
  OMP_NUM_THREADS=16 OMP_PLACES=cores OMP_PROC_BIND=close OMP_DYNAMIC=false \
  OMP_TARGET_OFFLOAD=DISABLED OPENBLAS_NUM_THREADS=1 \
  /usr/bin/time -v -o logs/stage1_amd_cpu_fe4s4_t16.time.log \
  build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu \
  --fcidump external/amd-sbd/samples/selected_basis_diagonalization/fcidump_Fe4S4.txt \
  --adetfile external/amd-sbd/samples/selected_basis_diagonalization/AlphaDets.txt \
  --method 0 --block 10 --iteration 4 --tolerance 1.0e-8 --max_time 240 \
  --adet_comm_size 1 --bdet_comm_size 1 --task_comm_size 1 \
  --init 0 --shuffle 0 --carryover_ratio 0.5 --rdm 0 --bit_length 20 \
  > logs/stage1_amd_cpu_fe4s4_t16.stdout.log 2> logs/stage1_amd_cpu_fe4s4_t16.stderr.log
```

## 2026-07-31T22:51Z — First converged AMD GPU Fe₄S₄ run

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 17.14 s
- Outcome: Converged to residual `8.931494922593578e-09` and energy `-326.6982536731581 Ha`. Raw telemetry showed actual L4 execution, 206 MiB peak sampled allocation, and up to 100% utilization. The original ISO timestamp introduced one extra CSV field; raw rows were retained and parsed from the end.

```bash
timeout --signal=TERM --kill-after=15s 300s env \
  PATH="/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/compilers/bin:/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/comm_libs/mpi/bin:$PATH" \
  CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=1 OMP_PLACES=cores OMP_PROC_BIND=close \
  OMP_DYNAMIC=false OMP_TARGET_OFFLOAD=MANDATORY OPENBLAS_NUM_THREADS=1 \
  /usr/bin/time -v -o logs/stage1_amd_gpu_fe4s4_i6.time.log \
  build/upstream/amd-729cfa3a-nvhpc-26.5/diag_gpu \
  --fcidump external/amd-sbd/samples/selected_basis_diagonalization/fcidump_Fe4S4.txt \
  --adetfile external/amd-sbd/samples/selected_basis_diagonalization/AlphaDets.txt \
  --method 0 --block 10 --iteration 6 --tolerance 1.0e-8 --max_time 240 \
  --adet_comm_size 1 --bdet_comm_size 1 --task_comm_size 1 \
  --init 0 --shuffle 0 --carryover_ratio 0.5 --rdm 0 --bit_length 20 \
  > logs/stage1_amd_gpu_fe4s4_i6.stdout.log 2> logs/stage1_amd_gpu_fe4s4_i6.stderr.log
```

## 2026-07-31T22:52Z — Converged matching AMD CPU Fe₄S₄ run

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 78.15 s
- Outcome: Converged to residual `8.931146441578446e-09` and energy `-326.6982536731583 Ha`; peak RSS 47,080 KiB.

```bash
timeout --signal=TERM --kill-after=15s 300s env \
  OMP_NUM_THREADS=16 OMP_PLACES=cores OMP_PROC_BIND=close OMP_DYNAMIC=false \
  OMP_TARGET_OFFLOAD=DISABLED OPENBLAS_NUM_THREADS=1 \
  /usr/bin/time -v -o logs/stage1_amd_cpu_fe4s4_t16_i6.time.log \
  build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu \
  --fcidump external/amd-sbd/samples/selected_basis_diagonalization/fcidump_Fe4S4.txt \
  --adetfile external/amd-sbd/samples/selected_basis_diagonalization/AlphaDets.txt \
  --method 0 --block 10 --iteration 6 --tolerance 1.0e-8 --max_time 240 \
  --adet_comm_size 1 --bdet_comm_size 1 --task_comm_size 1 \
  --init 0 --shuffle 0 --carryover_ratio 0.5 --rdm 0 --bit_length 20 \
  > logs/stage1_amd_cpu_fe4s4_t16_i6.stdout.log 2> logs/stage1_amd_cpu_fe4s4_t16_i6.stderr.log
```

## 2026-07-31T22:58Z — Canonical mandatory-offload AMD GPU rerun

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 17.22 s
- Outcome: `OMP_DISPLAY_ENV=VERBOSE` recorded `OMP_TARGET_OFFLOAD='MANDATORY'`; application recorded device 0. Residual, energy, and density exactly matched the first GPU run. Corrected telemetry timestamps contain no comma; across 75 samples, peak allocation was 206 MiB, utilization 100%, temperature 41 °C, and power 42.23 W.

```bash
timeout --signal=TERM --kill-after=15s 300s env \
  PATH="/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/compilers/bin:/opt/nvidia/hpc_sdk/Linux_x86_64/26.5/comm_libs/mpi/bin:$PATH" \
  CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=1 OMP_PLACES=cores OMP_PROC_BIND=close \
  OMP_DYNAMIC=false OMP_TARGET_OFFLOAD=MANDATORY OMP_DISPLAY_ENV=VERBOSE \
  OPENBLAS_NUM_THREADS=1 \
  /usr/bin/time -v -o logs/stage1_amd_gpu_fe4s4_i6_rerun1.time.log \
  build/upstream/amd-729cfa3a-nvhpc-26.5/diag_gpu \
  --fcidump external/amd-sbd/samples/selected_basis_diagonalization/fcidump_Fe4S4.txt \
  --adetfile external/amd-sbd/samples/selected_basis_diagonalization/AlphaDets.txt \
  --method 0 --block 10 --iteration 6 --tolerance 1.0e-8 --max_time 240 \
  --adet_comm_size 1 --bdet_comm_size 1 --task_comm_size 1 \
  --init 0 --shuffle 0 --carryover_ratio 0.5 --rdm 0 --bit_length 20 \
  > logs/stage1_amd_gpu_fe4s4_i6_rerun1.stdout.log \
  2> logs/stage1_amd_gpu_fe4s4_i6_rerun1.stderr.log
```

## 2026-07-31T22:58Z — Validate AMD CPU/GPU numerical agreement

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: All criteria passed: both residuals `<=1e-8`, energy relative error `6.959745663982201e-16 <= 1e-10`, and density maximum absolute error `2.7017277304253184e-13 <= 1e-10`. Wrote atomic `reports/stage1_amd_correctness.json`.

```bash
chmod +x scripts/compare_sbd_outputs.py
.venv/bin/python -m py_compile scripts/compare_sbd_outputs.py
.venv/bin/python scripts/compare_sbd_outputs.py \
  --cpu logs/stage1_amd_cpu_fe4s4_t16_i6.stdout.log \
  --gpu logs/stage1_amd_gpu_fe4s4_i6_rerun1.stdout.log \
  --residual-tolerance 1e-8 --energy-rtol 1e-10 --density-atol 1e-10 \
  --output reports/stage1_amd_correctness.json
jq -e '.passed == true and ([.checks[]] | all)' reports/stage1_amd_correctness.json
```

## 2026-07-31T23:00Z — Clean generated files from upstream worktrees

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: Removed exactly two generated executables and two object files from manual preliminary builds. Both submodules are clean; all four files are rebuildable and their relevant hashes/logs remain recorded.

```bash
rm \
  external/amd-sbd/applications/selected_basis_diagonalization/src/diag \
  external/amd-sbd/applications/selected_basis_diagonalization/src/main.o \
  external/riken-sbd/apps/chemistry_tpb_selected_basis_diagonalization/diag \
  external/riken-sbd/apps/chemistry_tpb_selected_basis_diagonalization/main.o
git -C external/amd-sbd status --short --branch
git -C external/riken-sbd status --short --branch
```

## 2026-07-31T23:18Z — Install the pinned Stage 2 Python dependency

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: Installed only `PyYAML==6.0.2` into the project-local virtual environment from `requirements-lock.txt`; the wheel download was 751.2 kB. Full output: `logs/stage2_pyyaml_install.log`.
- Provenance note: the durable pip log preserves the requested version and outcome, but not the exact short-versus-long spelling of the original pip option. The dependency request itself is exactly:

```text
PyYAML==6.0.2
```

## 2026-07-31T23:18Z–23:40Z — Implement and exercise the Stage 2 harness

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0 for the completed test and smoke-test runs
- Outcome: Added strict YAML configuration, streamed FCIDUMP/determinant features, memory feasibility, process monitoring, immutable JSON records, AMD output parsing, one-trial and sequential-sweep CLIs, and a five-outcome mock fixture. The first two complete mock smoke iterations passed 47 and 48 unit tests respectively. Each launched five trials with statuses `success=1`, `failed=2`, `timeout=1`, and `oom=1`; the immediate resume launched zero and reused all five records.
- Smoke roots: `/tmp/autosbd-stage2-smoke.4cDvC2`, `/tmp/autosbd-stage2-smoke.ePZCXD`.
- Focused runner log: `logs/test_runner.log`; 8/8 tests passed in 1.061 s.

```bash
bash scripts/smoke_test.sh
```

The smoke script executes the following commands and validates every resulting record:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python scripts/run_sweep.py configs/smoke.yaml --project-root "$repository_root" --results-dir "$results_dir" --logs-dir "$trial_logs_dir" --no-randomize
.venv/bin/python scripts/run_sweep.py configs/smoke.yaml --project-root "$repository_root" --results-dir "$results_dir" --logs-dir "$trial_logs_dir" --no-randomize
```

## 2026-07-31T23:40Z — Audit the pinned AMD command-line surface

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: Confirmed that pinned AMD commit `729cfa3a5011fb805eb9e686a7711f6919836dcb` accepts `--carryover_ratio`, accepts only `--adetfile` for this determinant input, and does not parse `--init`. Stage 2 therefore emits no `--init` and no `--bdetfile`; unknown flags must not be silently passed to the application.

```bash
rg -n -- '--init|--carryover_ratio|--adetfile|--bdetfile' external/amd-sbd/applications/selected_basis_diagonalization/src
```

## 2026-07-31T23:46Z — Run the first immutable Stage 2 AMD CPU correctness trial

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 78.53774263899686 s wall; 75.87626 s reported solver time
- Outcome: Schema-v1 record `3d550a2669c8c2d2b7cdc6f824d08f94c6d424c954160e3aa2fee18f9cd96bc1` converged in 50 iteration records to residual `8.931146441578446e-09` and energy `-326.6982536731583 Ha`; peak host RSS was 47.640625 MiB. Preflight saw an idle L4 with 22,564 MiB free and applied the 80%-free/20-GiB cap.
- Record: `results/raw/3d550a2669c8c2d2b7cdc6f824d08f94c6d424c954160e3aa2fee18f9cd96bc1.json`.
- Exact solver argv is preserved in that immutable record; the original outer `run_one.py` option ordering was not separately retained:

```bash
build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu \
  --fcidump external/amd-sbd/samples/selected_basis_diagonalization/fcidump_Fe4S4.txt \
  --adetfile external/amd-sbd/samples/selected_basis_diagonalization/AlphaDets.txt \
  --method 0 --iteration 6 --block 10 --tolerance 1e-08 --max_time 240 \
  --bit_length 20 --shuffle 0 --carryover_ratio 0.5 --rdm 0 \
  --adet_comm_size 1 --bdet_comm_size 1 --task_comm_size 1
```

## 2026-07-31T23:47Z — Run the first immutable Stage 2 AMD L4 correctness trial

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 17.13973771200108 s wall; 15.494857 s reported solver time
- Outcome: Schema-v1 record `0aa87a7deb05704f0dea7afc3d3ec382214d4d68c7ba4666fd6c7e89a8203ca5` converged in 50 iteration records to residual `8.931494922593578e-09` and energy `-326.6982536731581 Ha`. Mandatory target offload and device 0 were observed; 114 resource samples recorded 198 MiB peak GPU memory and 145.04296875 MiB peak host RSS.
- Record: `results/raw/0aa87a7deb05704f0dea7afc3d3ec382214d4d68c7ba4666fd6c7e89a8203ca5.json`.
- Exact solver argv differs from the CPU command only in its executable:

```bash
build/upstream/amd-729cfa3a-nvhpc-26.5/diag_gpu \
  --fcidump external/amd-sbd/samples/selected_basis_diagonalization/fcidump_Fe4S4.txt \
  --adetfile external/amd-sbd/samples/selected_basis_diagonalization/AlphaDets.txt \
  --method 0 --iteration 6 --block 10 --tolerance 1e-08 --max_time 240 \
  --bit_length 20 --shuffle 0 --carryover_ratio 0.5 --rdm 0 \
  --adet_comm_size 1 --bdet_comm_size 1 --task_comm_size 1
```

## 2026-07-31T23:48Z — Compare and resume the schema-v1 AMD pair

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: CPU/GPU residual, energy, and 36-value density checks passed. Energy relative error was `6.959745663982201e-16`; density maximum absolute error was `2.7017277304253184e-13`. Exact reruns reported `launched=false` and `reused=true` for both records.
- Integrity correction: schema v1 set `timing_eligible=true` even though the project tree was dirty and the protocol had zero warmups. The records remain byte-for-byte immutable, but that field is superseded and none of their timings are eligible for analysis.

## 2026-08-01T00:01Z–00:03Z — Exercise schema and telemetry hardening

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Intermediate outcome: A full 61-test integration run exited 1 with 10 errors after stricter manifest and identity gates invalidated stale test assumptions. This expected integration failure is preserved in `logs/telemetry_harden_full_tests.log`; the failing command was not repeated unchanged.
- Final focused outcomes: schema/claim tests 11/11 passed in 0.031 s; process/system telemetry tests 17/17 passed in 0.864 s.
- Logs: `logs/stage2_schema_harden_tests.log`, `logs/telemetry_harden_tests.log`.

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_records -v > logs/stage2_schema_harden_tests.log 2>&1
PYTHONPATH=src .venv/bin/python -m unittest tests.test_process tests.test_system -v > logs/telemetry_harden_tests.log 2>&1
```

## 2026-08-01T00:16Z–00:17Z — Validate the integrated schema-v2 runner

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: The hardened runner suite passed 13/13 tests in 2.373 s, including node-lock contention, input mutation, artifact hashing, logical-identity self-verification, official-source/binary rejection, and timing-gate coverage. The complete suite then passed 67/67 in 4.325 s.
- Logs: `logs/test_runner_v2.log`, `logs/test_full_v2.log`.

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_runner.py' -v > logs/test_runner_v2.log 2>&1
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v > logs/test_full_v2.log 2>&1
```

## 2026-08-01T00:17Z — Run the hardened mock smoke and resume test

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: 2.954 s for 62 tests plus bounded mock trials
- Outcome: `/tmp/autosbd-stage2-smoke.4XQRJS` launched five schema-v2 mock trials with statuses `success=1`, `failed=2`, `timeout=1`, and `oom=1`; its immediate resume launched zero and reused all five immutable records.

```bash
bash scripts/smoke_test.sh
```

## 2026-08-01T00:17Z–00:19Z — Run hardened schema-v2 AMD CPU/GPU correctness trials

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0 for both sequential runs
- CPU outcome: trial `9f9031146690fe8afd04b94fced38551c7863ea95d62ff35404f022895055d1d`; 78.72754408099718 s wall, 76.066536 s solver, 47.6484375 MiB peak RSS, residual `8.931146441578446e-09`, energy `-326.6982536731583 Ha`.
- GPU outcome: trial `1b7be4e302c4b8185d7960e04af7bf42abc4b41c49dfb0d3727a790383de6125`; 17.221985976000724 s wall, 15.509004 s solver, 198 MiB peak GPU memory, 145.0859375 MiB peak RSS, residual `8.931494922593578e-09`, energy `-326.6982536731581 Ha`.
- Safety/evidence: both preflights found no GPU compute process and 22,564 MiB free. Input hashes matched initially, immediately before launch, and after completion. The GPU monitor was complete and observed the trial process. Every stdout, stderr, and resource log is size/hash-linked in its record.
- Eligibility: both records say `purpose=correctness`, `warmups=0`, `correctness_validated=false`, and `project_git_dirty=true`; therefore both correctly record `timing_eligible=false`.
- Toolchain: both exact binaries are from official `AMD-HPC/amd-sbd` commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`, built with NVIDIA HPC SDK `nvc++ 26.5-0`; the GPU build targets `cc89` using bundled CUDA 13.2.
- The exact solver argv is the same backend-specific argv recorded in the two schema-v1 sections above. The schema-v2 records additionally bind it to compiler identity, build flags, executable hash, semantic input hash, protocol, environment, and attempt index.

```bash
sha256sum external/amd-sbd/samples/selected_basis_diagonalization/fcidump_Fe4S4.txt external/amd-sbd/samples/selected_basis_diagonalization/AlphaDets.txt
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage2_amd_smoke.yaml --no-randomize --require-all-success
```

## 2026-08-01T00:20Z–00:21Z — Revalidate AMD numerical agreement and seal evidence manifest

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: An inline record verifier recomputed all artifact hashes, schema identities, energy agreement, and the 36-value density comparison. `reports/stage2_amd_correctness.json` passed all four criteria for the schema-v2 pair: both residuals at most `1e-8`, energy relative error `6.959745663982201e-16`, and density maximum absolute error `2.7017277304253184e-13`. The two report files were then updated with `apply_patch`; no comparison command silently rewrote an immutable record. A second inline verifier checked all 19 manifest-linked files and exercised the runner's real manifest validator for both candidates. Manifest SHA-256: `aeb470c55e23ff9b71c946e38b25bc83193584ca2654e7a8cd2f8fca2aef6493`.

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
import json
from pathlib import Path
from autosbd.records import validate_record

paths = [
    Path("results/raw/9f9031146690fe8afd04b94fced38551c7863ea95d62ff35404f022895055d1d.json"),
    Path("results/raw/1b7be4e302c4b8185d7960e04af7bf42abc4b41c49dfb0d3727a790383de6125.json"),
]
records = [json.loads(path.read_text()) for path in paths]
for record in records:
    validate_record(record)
by_backend = {record["backend"]: record for record in records}
cpu = by_backend["cpu"]
gpu = by_backend["gpu"]
cpu_density = [float(value) for value in cpu["upstream_output"]["density"]]
gpu_density = [float(value) for value in gpu["upstream_output"]["density"]]
density_max_abs = max(abs(a - b) for a, b in zip(cpu_density, gpu_density))
energy_rel = abs(cpu["energy_or_eigenvalue"] - gpu["energy_or_eigenvalue"]) / abs(cpu["energy_or_eigenvalue"])
assert density_max_abs <= 1e-10
assert energy_rel <= 1e-10
print({"density_max_absolute_error": density_max_abs, "energy_relative_error": energy_rel})
PY
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage2_amd_smoke.yaml --no-randomize --require-all-success
jq empty reports/stage2_amd_correctness.json reports/stage2_amd_validation_manifest.json
sha256sum reports/stage2_amd_correctness.json reports/stage2_amd_validation_manifest.json
```

The exact rerun summary was `launched=0`, `reused=2`, `statuses={"success": 2}`.

## 2026-08-01 — Reconcile and validate the Stage 2 durable logs

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: Appended the Stage 2 command, experiment, and decision evidence without modifying earlier entries. Whitespace, merge-marker, carriage-return, required-term, heading, and three-file scope checks passed. The report-only diff contains 233 inserted lines before this audit entry.

```bash
git diff --check -- reports/COMMAND_LOG.md reports/EXPERIMENT_LOG.md reports/DECISIONS.md
! rg -n '^(<<<<<<<|=======|>>>>>>>)' reports/COMMAND_LOG.md reports/EXPERIMENT_LOG.md reports/DECISIONS.md
! rg -n $'\r' reports/COMMAND_LOG.md reports/EXPERIMENT_LOG.md reports/DECISIONS.md
rg -n 'Stage 2|schema-v2|schema v2|timing_eligible=false|AMD-HPC/amd-sbd|NVIDIA HPC SDK 26\.5|9f903114|1b7be4e3|3d550a26|0aa87a7d|67/67' reports/COMMAND_LOG.md reports/EXPERIMENT_LOG.md reports/DECISIONS.md
rg -n '^## D-[0-9]{3}' reports/DECISIONS.md
git diff --stat -- reports/COMMAND_LOG.md reports/EXPERIMENT_LOG.md reports/DECISIONS.md
git status --short -- reports/COMMAND_LOG.md reports/EXPERIMENT_LOG.md reports/DECISIONS.md
```

## 2026-08-01 — Record non-mutating diagnostic invocation failures

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Outcome: The two inspection batches below exited 1 without changing project files. The first stopped immediately because `pytest` is intentionally absent from the minimal environment. The second omitted `PYTHONPATH=src`, so discovery found seven test modules and all seven imports failed with `ModuleNotFoundError: No module named 'autosbd'`; its saved exit status was returned after the subsequent read-only help/file inspections completed. Both were corrected by using standard-library `unittest` with `PYTHONPATH=src`; neither failed command was repeated unchanged.

```bash
.venv/bin/python -m pytest -q && .venv/bin/python scripts/run_one.py --help && .venv/bin/python scripts/run_sweep.py --help && sed -n '1,240p' pyproject.toml && sed -n '1,260p' configs/stage2_amd_smoke.yaml && sed -n '1,220p' configs/smoke.yaml && jq '{schema_version,passed,checks,metrics,cpu,gpu}' reports/stage2_amd_correctness.json && jq '{trial_id,status,correct,timing_eligible,wall_time_s,solver_time_s,peak_gpu_memory_mb,iterations,result,resource_monitoring,input_integrity,run_artifacts,upstream,build,compiler}' results/raw/1b7be4e302c4b8185d7960e04af7bf42abc4b41c49dfb0d3727a790383de6125.json
```

```bash
.venv/bin/python -m unittest discover -s tests -v; test_status=$?; .venv/bin/python scripts/run_one.py --help; .venv/bin/python scripts/run_sweep.py --help; sed -n '1,240p' pyproject.toml; sed -n '1,260p' configs/stage2_amd_smoke.yaml; sed -n '1,220p' configs/smoke.yaml; jq '{schema_version,passed,checks,metrics,cpu,gpu}' reports/stage2_amd_correctness.json; jq '{trial_id,status,correct,timing_eligible,wall_time_s,solver_time_s,peak_gpu_memory_mb,iterations,result,resource_monitoring,input_integrity,run_artifacts,upstream,build,compiler}' results/raw/1b7be4e302c4b8185d7960e04af7bf42abc4b41c49dfb0d3727a790383de6125.json; exit "$test_status"
```

- Additional short inline probes initially used the unavailable `python` alias (exit 127), then omitted `PYTHONPATH=src`, and then guessed obsolete API names `load_config` and `ExperimentRunner`. Each was a read-only introspection failure. The corrected APIs are `load_sweep_config`, `TrialRunner`, and `_detect_nvhpc_compiler_identity`, invoked with `.venv/bin/python` and `PYTHONPATH=src`.

## 2026-08-01 — Remove legacy RIKEN targets from the active build entry point

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0 for validation; the deliberately invalid `riken-cpu` request returned the required exit code 2.
- Outcome: `scripts/build_upstream.sh` now exposes only `amd-all`, `amd-cpu`, and `amd-gpu`; it also rejects a non-official origin, a commit other than `729cfa3a5011fb805eb9e686a7711f6919836dcb`, or a dirty official checkout before compilation. No binary was rebuilt. The historical RIKEN submodule/header/logs remain preserved but have no active build target.

```bash
bash -n scripts/build_upstream.sh
set +e
scripts/build_upstream.sh riken-cpu >/tmp/autosbd-invalid-target.stdout 2>/tmp/autosbd-invalid-target.stderr
status=$?
set -e
test "$status" -eq 2
test ! -s /tmp/autosbd-invalid-target.stdout
rg -n '^Usage: .*amd-all\|amd-cpu\|amd-gpu' /tmp/autosbd-invalid-target.stderr
if rg -ni 'riken' scripts/build_upstream.sh
then
  exit 1
fi
test "$(git -C external/amd-sbd rev-parse HEAD)" = "729cfa3a5011fb805eb9e686a7711f6919836dcb"
test "$(git -C external/amd-sbd remote get-url origin)" = "https://github.com/AMD-HPC/amd-sbd.git"
test -z "$(git -C external/amd-sbd status --porcelain)"
```

## 2026-08-01T00:35Z — Generate and verify official AMD Fe₄S₄ size variants

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: Generated five exact nested determinant prefixes and `manifest.json` under `data/derived/amd_fe4s4_prefixes/`. The immediate `--check` changed zero files. Manifest SHA-256 is `47b62521b5b369f2a7c3af52ae805073451b23b457a8e044ff9fa27a2f6d47e8`; the official AMD checkout remained clean.

```bash
.venv/bin/python scripts/prepare_workloads.py
.venv/bin/python scripts/prepare_workloads.py --check
find data/derived/amd_fe4s4_prefixes -maxdepth 1 -type f -printf '%f %s bytes\n' | sort
sha256sum data/derived/amd_fe4s4_prefixes/AlphaDets_n*.txt data/derived/amd_fe4s4_prefixes/manifest.json
jq '.' data/derived/amd_fe4s4_prefixes/manifest.json
test -z "$(git -C external/amd-sbd status --porcelain)"
```

## 2026-08-01T00:36Z — Validate workload generator and calibration geometry

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0 for the final checks
- Outcome: Seven focused tests passed in 0.662 s, including exact prefix hashes, idempotence, tamper rejection, upstream write refusal, and fail-closed origin/commit/dirty-checkout cases. `configs/stage3_calibration.yaml` strict-loaded to eight CPU16/GPU correctness trials. The four non-full prefix configuration counts are 1,024, 3,025, 10,000, and 30,276; conservative guards are at most 640 MiB.
- Diagnostic correction: the first read-only geometry probe omitted the required `max_block` and `iterations` arguments to `estimate_source_memory` and raised `TypeError` after loading the eight trials. It changed no files and was retried once with the actual signature.

```bash
.venv/bin/python -m py_compile scripts/prepare_workloads.py tests/test_prepare_workloads.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_prepare_workloads.py' -v
.venv/bin/python scripts/prepare_workloads.py --help >/dev/null
.venv/bin/python scripts/prepare_workloads.py --check
```

## 2026-08-01T00:39Z–00:40Z — Run four-size derived correctness calibration

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Duration: about 60 s for eight sequential trials
- Outcome: All eight official AMD CPU16/GPU records completed with status `success`; `launched=8`, `reused=0`. The safety query showed a clean project/upstream, an idle L4 with 22,564 MiB free at 34 °C, about 122 GiB available host memory, and load average 0.04. Subsequent schema/artifact/input and cross-backend verification passed every pair.

```bash
git status --porcelain
git -C external/amd-sbd status --porcelain
git -C external/amd-sbd rev-parse HEAD
git -C external/amd-sbd remote get-url origin
sha256sum build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu build/upstream/amd-729cfa3a-nvhpc-26.5/diag_gpu
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,temperature.gpu,power.draw,utilization.gpu --format=csv,noheader,nounits
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits
free -b
uptime
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage3_calibration.yaml --no-randomize --require-all-success
```

## 2026-08-01T00:40Z–00:42Z — Discover and preserve clean-resume anomaly

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0
- Outcome: An inline verifier accepted the first four clean CPU/GPU pairs, then the exact sweep command below unexpectedly launched eight new trials. Root cause: the new untracked `results/raw/*.json` files made the second `TrialRunner` report `project_git_dirty=true`, changing logical identities. The duplicate sweep remained safe/sequential and completed successfully. All eight duplicate records are preserved but excluded; none is timing eligible.

```bash
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage3_calibration.yaml --no-randomize --require-all-success
pgrep -af 'scripts/run_sweep.py configs/stage3_calibration.yaml' || true
ps -eo pid,ppid,stat,etime,cmd | rg 'run_sweep.py|diag_(cpu|gpu)' || true
```

## 2026-08-01T00:42Z–00:47Z — Harden resume and multi-input calibration evidence

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0 for corrected commands
- Outcome: Added a narrowly opt-in Git-state filter, schema-v2 multi-input manifest validation, and a deterministic correctness-only calibration-manifest builder. The integrated suite passed 89/89 tests in 6.765 s. A real four-input temporary manifest was written and an identical second invocation returned `unchanged`; it contains no timing or speedup fields. The calibration config now enumerates ten trials across all five prefix sizes.
- Diagnostic corrections: delegated verification initially used the absent `python` alias, unavailable `pytest`, or omitted `PYTHONPATH=src`; those invocations ran no applicable tests and changed no files. Each was corrected once with the commands below and no package installation.

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_system.py' -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_runner.py' -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_calibration_manifest.py' -v
PYTHONPATH=src .venv/bin/python scripts/build_calibration_manifest.py \
  results/raw/a09754871cf59de3125e3420bb067412c69bf279ef7d8c016b71d4b600ecc57d.json \
  results/raw/2681cbbbe0c0e713991c47f797cf73f5b123c7e36070cc4aa53069e42db4d143.json \
  results/raw/51132580237331aff79401fd6578d5f144b4090064eb92162bc6cfe3b81cb338.json \
  results/raw/ee44ef1c9053626aef785e9a311ba10272ec1c0dd5bf67c9ae9af1a71636c933.json \
  results/raw/7e9ff4feb43bc2092d6c0d224c419fdfd935d7e41f058b5a9a04b83498c25186.json \
  results/raw/a24a1104865795e9ad6d25c498c17a91fdbfbf7532f6d638aa9c64d60aa3fca7.json \
  results/raw/d2dc37a2d170636e27915c71f129a01a9055496823468e6e6c67c6c1f26f3439.json \
  results/raw/cea5de6fa53517dcfcdb0065293bf06c01251f181ecda91af175f441072b6b69.json \
  --output /tmp/autosbd-stage3-initial-calibration.json
```

## 2026-08-01 — Run definitive five-size calibration and validate pilot geometry

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Pre-run safety/provenance: the project tree was clean at commit `7bdb03d96508ccb38f2aa5f6ed8dc5c439db9322`; the official `AMD-HPC/amd-sbd` checkout was clean at pinned commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`.
- First calibration sweep: exit code 0; `launched=10`, `reused=0`, `statuses={"success": 10}`. The ten sequential CPU16/GPU correctness trials produced the immutable IDs listed below.
- Immediate identical resume: exit code 0; `launched=0`, `reused=10`, `statuses={"success": 10}`. This is the definitive clean-resume validation after the narrow untracked-raw-record Git-state fix.
- Calibration-manifest builder: the first invocation exited 0 with `status=written, validated_inputs=5`; the immediate identical second invocation exited 0 with `status=unchanged, validated_inputs=5`. The resulting `reports/stage3_calibration_manifest.json` SHA-256 is `6fcc273d84f65d20185c0abcba9b750a29c2d64a87c982e500a4be5cdd93bdec`.
- Scientific scope: this five-size calibration establishes CPU/GPU correctness references and resume behavior only. Its observed runtimes are diagnostic; this entry makes no timing, performance, or speedup claim.
- Pilot validation: an initial read-only parser probe imported nonexistent `load_experiment_config` and exited 1 without changing files. The corrected `load_sweep_config` validator exited 0 and found 20 expanded pilot trials and 10 unique workload/candidate pairs, all valid with `errors=[]`.
- State interpretation: project dirtiness during the post-run, pre-checkpoint validation was expected from pending project changes; it is distinct from the clean pre-run state recorded above and did not alter the immutable calibration records.

The ten record paths, in manifest-builder order, are:

1. `results/raw/a3031aa22d1302ca125d623f528bf83e6e114c70daf5661971a4a2b3c38802a9.json`
2. `results/raw/36e8b30cd7a47395b4d77a35cb03076e5eeb71c5c1d50e86cda5616db7401c1a.json`
3. `results/raw/1a0b61f03bb70ef8b2f6fafe193332e9467a7a76ef4a9650c8905f0aff7bce6d.json`
4. `results/raw/e494bffc56fdeb6530acfd4073d71d3adc47d738369d742aecac17287c631c18.json`
5. `results/raw/6ec823260f147f7e419270c013c72ac2136072eb5d993bdffd12c55979303bb3.json`
6. `results/raw/986ff28be901f37618522018fc1fb4221bf60577649eb9bbf99a1eb46355a2fb.json`
7. `results/raw/1513df46ffcb2e05b099a477dc64382471ece1ddc1f8315748da7f2c166dc012.json`
8. `results/raw/59767a40295039a8f168f73b4d671a7fb7ae419d9bf61317e0f733c9899664b5.json`
9. `results/raw/b126ad26ffb7456299d0dcddb0846fb43f98942c251a1fcd585c7fa7ca57dae9.json`
10. `results/raw/e80924745e5090c1ba11868ac6f6bdf71a06f66f0a913527a4091a2ab6dbfa28.json`

```bash
git status --porcelain
git rev-parse HEAD
git -C external/amd-sbd status --porcelain
git -C external/amd-sbd rev-parse HEAD

PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage3_calibration.yaml --no-randomize --require-all-success
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage3_calibration.yaml --no-randomize --require-all-success

PYTHONPATH=src .venv/bin/python scripts/build_calibration_manifest.py \
  <ten explicit results/raw/...json paths enumerated above, in that order> \
  --output reports/stage3_calibration_manifest.json
# The immediately repeated builder invocation used the identical command and order.
sha256sum reports/stage3_calibration_manifest.json
```

The failed read-only loader probe was:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
from autosbd.config import load_experiment_config
PY
```

The corrected pilot-only validator was:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
from autosbd.config import enumerate_trials, load_sweep_config

pilot = load_sweep_config("configs/stage3_pilot.yaml")
trials = enumerate_trials(pilot, randomize=False)
pairs = {(trial.workload.name, trial.candidate.name) for trial in trials}
errors = []
if len(trials) != 20:
    errors.append(f"trial count={len(trials)}")
if len(pairs) != 10:
    errors.append(f"unique workload/candidate pairs={len(pairs)}")
print({"trials": len(trials), "unique_pairs": len(pairs), "errors": errors})
if errors:
    raise SystemExit(1)
PY
```

A documentation-side read-only validator initially combined the 10 calibration templates with the 20 pilot warmup/measured templates and exited 1 after reporting 30 total; it changed no files. The pilot-only command above corrected that counting scope once and exited 0.

## 2026-08-01 — Verify the clean pre-pilot checkpoint

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0 for both parallel checks.
- Outcome: The complete suite passed 89/89 tests in 6.738 s. The deterministic workload generator reported `changed_files=[]` and its existing manifest SHA-256. The Stage 3 calibration manifest parsed as JSON and retained SHA-256 `6fcc273d84f65d20185c0abcba9b750a29c2d64a87c982e500a4be5cdd93bdec`. The official AMD checkout remained clean at the required commit and origin. Neither active Stage 3 configuration nor the AMD-only build entry point contains a RIKEN path.

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
git diff --check
.venv/bin/python scripts/prepare_workloads.py --check
.venv/bin/python -m json.tool reports/stage3_calibration_manifest.json >/dev/null
test "$(git -C external/amd-sbd rev-parse HEAD)" = "729cfa3a5011fb805eb9e686a7711f6919836dcb"
test "$(git -C external/amd-sbd remote get-url origin)" = "https://github.com/AMD-HPC/amd-sbd.git"
test -z "$(git -C external/amd-sbd status --porcelain)"
! rg -ni 'riken|r-ccs-cms' configs/stage3_calibration.yaml configs/stage3_pilot.yaml scripts/build_upstream.sh
sha256sum reports/stage3_calibration_manifest.json
git status --short
```

## 2026-08-01 — Run, resume, audit, and aggregate the Stage 3 pilot

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Preflight exit status: 0. The project tree was clean at commit `2ddbb40953e36194531fcd48966ecacaefb09959`. The official `AMD-HPC/amd-sbd` checkout was clean at pinned commit `729cfa3a5011fb805eb9e686a7711f6919836dcb` and origin `https://github.com/AMD-HPC/amd-sbd.git`.
- Exact artifacts: CPU SHA-256 `190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07`; GPU SHA-256 `8f1481b6bcb4ddf3326453fd3a7c03dc36e29034629f46c5e982a4c17e43bc07`; correctness-manifest SHA-256 `6fcc273d84f65d20185c0abcba9b750a29c2d64a87c982e500a4be5cdd93bdec`.
- Initial safety state: the NVIDIA L4 was idle with no compute processes, 22,564 MiB free of 23,034 MiB, 0% utilization, 34 °C, and 16.52 W power draw. Available host memory was 130,886,766,592 bytes, one-minute load was 0.333984375, and the GPU allocation cap was 18,928,055,091 bytes under `min(20 GiB, 80% of preflight free VRAM)`.
- First pilot invocation: exit code 0; `total=20`, `launched=20`, `reused=0`, `statuses={"success": 20}`.
- Immediate exact rerun: exit code 0; `total=20`, `launched=0`, `reused=20`, `statuses={"success": 20}`. No solver was relaunched and no immutable record changed.
- Eligibility and integrity: all 10 warmups have `timing_eligible=false`; all 10 measured records have `timing_eligible=true`. Schema/identity, official-source, exact-build, clean-tree, valid-manifest, correctness, input-stability, resource-monitoring, GPU-idle/device/process/allocation, and artifact size/SHA gates all passed.
- Pilot-only observation: the CPU16/GPU measured ordering changes between 1,024 and 3,025 product configurations. This is a provisional crossover bracket from one measured repetition per candidate, not a final crossover, uncertainty, speedup, or headline performance claim.

The 20 immutable record paths, in observed execution order, are:

1. `results/raw/4d80b460ad16db719a8dd0d72efd5251aa6eb28c5ec28c0b6ae1fa8da578a8c1.json` — warmup, size 32, CPU16
2. `results/raw/a5f77f629f419a4eb8b9e55bd49c71873ec790b9994713ccf108a88d7b699950.json` — warmup, size 32, GPU
3. `results/raw/37e9df4031045fd854078dd88befde2de45109b744cd6fe3c26a21728adb37fb.json` — warmup, size 55, GPU
4. `results/raw/1b2f7462ccd4ae032c9070557b579b1a14efb1394cca7893b77f6b726329900a.json` — warmup, size 55, CPU16
5. `results/raw/95f18489b726822544d9b83103332471063cbbdf68551c6414fa16289771cf4c.json` — warmup, size 100, CPU16
6. `results/raw/f35d82c34a6f8d94df53a6b955aa9501a279193ed7ba1e0091efb3cbe7f13c63.json` — warmup, size 100, GPU
7. `results/raw/84c49de363351dce7ccea810c996051e72e494e7bb10792c7d2208565c4ac759.json` — warmup, size 174, CPU16
8. `results/raw/88b8c3db069fa8bf7385bb15268ec339b85c701bfcc42ac8feedee3f6c9e7a16.json` — warmup, size 174, GPU
9. `results/raw/8dcb1bd51f281ed82c5e8080a55c7d29d9e6624708aa48ac115b6709476a6519.json` — warmup, size 244, GPU
10. `results/raw/77a5579d6a932531a8ba9cc7c01d3235ed7e5e98d7c5daa107df6f979b74f669.json` — warmup, size 244, CPU16
11. `results/raw/c1f46570e5eb16916af4a3902ef799697b7e10a8226f9913797f64b237f239a1.json` — measured, size 32, GPU
12. `results/raw/e059dbfc8ab402e395b41d467b03fe39cf1d601e4ed4db4162e92e96f31474b8.json` — measured, size 32, CPU16
13. `results/raw/96582c3f7dcb942b9b091d34a47074f620f61e9d6c4a19c4bf1514077bea7197.json` — measured, size 55, GPU
14. `results/raw/64af98614e64fe74146bdc2ba45760491f91d4eafb301c539b1a98d09e45a9e5.json` — measured, size 55, CPU16
15. `results/raw/aadf64a56d1236b7026e197c600de37ea25117ef07e9cefb565d2add5b181087.json` — measured, size 100, CPU16
16. `results/raw/13b9155ea6bc2817871d9822b0f710358e3bef163dcb740551321a520501f96a.json` — measured, size 100, GPU
17. `results/raw/bbf148905993355e8fd89deb3a63a50c396cebe7c4d1056913b74c2b21e8fc07.json` — measured, size 174, CPU16
18. `results/raw/718bbe4be95bce3c1c9d093c4d1141fa32ffd952927a138989216edfad0d74b9.json` — measured, size 174, GPU
19. `results/raw/c674e42e6c0a774f3e659bc79dd6e2ea2c3463a2b75f53c7bcb8402157ecbc23.json` — measured, size 244, CPU16
20. `results/raw/4ed99164c34929bf4fad80ffbd8a75e51ab9b56963d545a5aaea61a68097499f.json` — measured, size 244, GPU

```bash
git status --porcelain
git rev-parse HEAD
git -C external/amd-sbd status --porcelain
git -C external/amd-sbd rev-parse HEAD
git -C external/amd-sbd remote get-url origin
sha256sum \
  build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu \
  build/upstream/amd-729cfa3a-nvhpc-26.5/diag_gpu \
  reports/stage3_calibration_manifest.json
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,temperature.gpu,power.draw,utilization.gpu --format=csv,noheader,nounits
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits
free -b
uptime

PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage3_pilot.yaml --require-all-success
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage3_pilot.yaml --require-all-success
```

The read-only integrity audit loaded all 20 explicit records through `autosbd.records.load_record`, independently recomputed record/build/input/stdout/stderr/resource/manifest hashes and sizes, checked the exact 5-workload × 2-backend × 2-phase geometry, and reconstructed all current logical identities through `_load_expected_record`. The reconstruction returned `total=20`, `launched=0`, `reused=20`, `success=20`; it did not call `TrialRunner.run`, `run_sweep`, or `run_monitored`, and before/after raw-record sizes and mtimes were identical.

The deterministic aggregator was invoked twice with the identical explicit order above:

```bash
PYTHONPATH=src .venv/bin/python scripts/analyze_results.py \
  <20 explicit results/raw/...json paths enumerated above, in that order> \
  --output-json results/processed/stage3_pilot.json \
  --output-csv results/processed/stage3_pilot.csv
# The immediate second invocation used the identical command and record order.
sha256sum results/processed/stage3_pilot.json results/processed/stage3_pilot.csv
```

- First aggregation: exit code 0; `input_records=20`, `included_records=10`, `excluded_records=10`, `json_changed=true`, `csv_changed=true`.
- Immediate identical aggregation: exit code 0; the same 20/10/10 counts, `json_changed=false`, and `csv_changed=false`.
- Deterministic outputs: JSON SHA-256 `0e5a6ce892377125f988a9cdc4a793e4071053d1cc8fefb151a8e324bbd001f6`; CSV SHA-256 `816a4c1afac501006ed4d0a656da12d7c83db0abc8bbc9620a17ff4a56f9d35c`. The CSV contains 20 data rows plus one header; warmups are retained as excluded rows rather than deleted.

The CPU-thread pilot configuration was then validated read-only; no thread benchmark was launched:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
from autosbd.config import load_sweep_config

config = load_sweep_config("configs/stage3_thread_pilot.yaml")
trials = config.trial_templates(randomize=True)
pairs = {(trial.workload.name, trial.candidate.name) for trial in trials}
assert len(trials) == 18
assert len(pairs) == 9
print({"templates": len(trials), "unique_pairs": len(pairs), "errors": []})
PY
```

Outcome: exit code 0; 18 templates, 9 unique workload/candidate pairs, and no validation errors.

All integrity/resume audits were read-only and produced no record mutation. Two diagnostic assumptions were corrected once: the first deep audit looked for nonexistent `validation_evidence.passed` and `.upstream_commit` keys (exit 1), then used the actual `valid=true` and `errors=[]` contract; the first static identity probe guessed the project-origin owner incorrectly (exit 1 before record matching), then limited the check to the required commit/clean state and passed 20/20. A later aggregate projection requested nonexistent `summary`/`records` keys and printed null/0 without failing; the corrected `record_counts`/`rows` projection returned input/included/excluded counts 20/10/10. None of these probes invoked a benchmark or changed a file.

## 2026-08-01 — Verify Stage 3 aggregation and thread-pilot checkpoint

- Working directory: `/home/nagan/autosbd-sc26-rg`
- Exit code: 0.
- Outcome: Focused aggregation tests passed 7/7 in 0.135 s and the full standard-library suite passed 96/96 in 6.848 s. Byte compilation and diff checks passed. The analysis layer now rejects explicitly supplied schema-v1 records with a clear fail-closed `AnalysisError`; the immutable record loader itself remains backward compatible. Processed pilot counts remain exactly 20 input, 10 included measurements, and 10 excluded warmups.
- File SHA-256: thread pilot config `0ae526e8e009ba41a332f76cdffa29bcbe561f9b680c164cb09d73363cb71b3e`; analysis module `aa07b594223ab7a838d1fabf824ca9992d823ac9fa84ff81a7a745a353fd7c7d`; analysis CLI `842c91cef21b2a1e796ed6410adaa40f5a770f3c00616234142d36974b8d5b9d`; analysis tests `ffaedfe430b25e51855eff21fce6b190c0e33a3fd4f7ad69000f826e750224f7`.

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_analysis.py' -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
git diff --check
.venv/bin/python -m py_compile src/autosbd/analysis.py scripts/analyze_results.py tests/test_analysis.py
.venv/bin/python -m json.tool results/processed/stage3_pilot.json >/dev/null
test "$(($(wc -l < results/processed/stage3_pilot.csv)-1))" -eq 20
sha256sum \
  configs/stage3_thread_pilot.yaml \
  src/autosbd/analysis.py \
  scripts/analyze_results.py \
  tests/test_analysis.py \
  results/processed/stage3_pilot.json \
  results/processed/stage3_pilot.csv
```

## 2026-08-01 — Run the CPU-thread pilot and freeze Stage 4

Purpose: execute the predeclared single-repetition CPU-thread pilot, prove immutable resume behavior, combine it with the Stage 3 CPU16/GPU pilot, apply decision D-024, and freeze the bounded Stage 4 protocol before any final measurements. No final benchmark was run in this block.

### Preflight and provenance

Commands:

```bash
git status --porcelain
git rev-parse HEAD
git -C external/amd-sbd status --porcelain
git -C external/amd-sbd rev-parse HEAD
git -C external/amd-sbd remote get-url origin
sha256sum build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu \
  reports/stage3_calibration_manifest.json \
  configs/stage3_thread_pilot.yaml
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader,nounits
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits
free -b
uptime
```

Exit status: `0` for the preflight batch. Evidence:

- Project checkout: clean at `63c7fba3dcfc50a09dd849b1ada539ce31073cc9` before launch.
- Official upstream: clean at AMD-HPC/amd-sbd commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`, origin `https://github.com/AMD-HPC/amd-sbd.git`.
- CPU executable: `build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu`, 797304 bytes, SHA-256 `190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07`.
- Validation manifest: 20337 bytes, SHA-256 `6fcc273d84f65d20185c0abcba9b750a29c2d64a87c982e500a4be5cdd93bdec`.
- Thread-pilot config: SHA-256 `0ae526e8e009ba41a332f76cdffa29bcbe561f9b680c164cb09d73363cb71b3e`.
- GPU: NVIDIA L4, 23034 MiB total, 0 MiB used, 22564 MiB free, 0% utilization, 34 C, 16.53 W, and no compute processes; the runner recorded `gpu_idle=true`, a successful query, and a 18928055091-byte GPU allocation cap.
- Host: 130794508288 bytes available, 104635606630-byte allocation cap, and load average 0.37548828125 at the first trial preflight.

### Thread-pilot launch and immediate immutable resume

Commands, issued twice without alteration:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage3_thread_pilot.yaml --require-all-success
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage3_thread_pilot.yaml --require-all-success
```

Exit status and outcomes:

- First invocation: exit `0`; total 18, launched 18, reused 0, successful 18; wall time approximately 4.1 minutes.
- Immediate identical invocation: exit `0`; total 18, launched 0, reused 18, successful 18.

The seeded execution order and immutable raw paths were:

```text
results/raw/29a0703af2205a8b2f70142de4335cfb1a701ed7e862a37ac29ae7ddbc934668.json
results/raw/8c258492f94fd50789df2b02b183226f6d99f64bdfd1b6580f98ede2e4c5d28a.json
results/raw/c2b69d0d191668bce244a4370fe3b33c005c4c9b2b4db985f3b0e952068730b3.json
results/raw/6bf4c3c57b6ae4380df445f1aa44915a1b27d52922a18358bccf28c30a0c2934.json
results/raw/dfebd88d09cd5c0479d1a4c83d32c8f614690556776e009039d4c627acd5438e.json
results/raw/13c8406ef2ff8c8ffcc882ba39786b4a17b1d0b455525f24afa5340e7aa41f4c.json
results/raw/a3813a2a15d364dd01854c705fb44820ebf1cf6b0ff3e0f3d652c97c15b24f75.json
results/raw/562537935652247f81ce5a4e90b0af1c00490a0807242e758349557314c44626.json
results/raw/6f9a0f85142d640f00fa9696372f6799da430568ab6601e16317e4084258732d.json
results/raw/088ed9672fdad73d3fb37731783332ada8e5cfb958efca1cefd6434e131128a2.json
results/raw/55745400d3e298ad4d35dfcc7230b57a66db2ef6eee00e8479e9bc43d1514b51.json
results/raw/5946ae3cd24970c92f5af44e06971b65e48d39d48251837f790a00d5e97b738b.json
results/raw/e35dcf729319e3b3b988d3aee2f2c8126253eee6800748896f5afc50d5c13de5.json
results/raw/3e2289629882c1912081e4814befe970d0112d42c35c4564e64ed19bc9face5d.json
results/raw/4125b7a769ea05c1022a5af1f71e20a8b89319ffc695f2aa8cc9e7ebbe458f24.json
results/raw/5c573ef9d6d47255466c095aae2a14613015b896b8051cf9a1f0157643b149df.json
results/raw/a285e83eef4e35374b28b391fa19bae0deba12204d92c411cd66c5b595fe7004.json
results/raw/21aad203bbd88774c7f17335048a5b65197e84b14f26715d1311799248c91d1d.json
```

The first nine paths are warm-ups with `timing_eligible=false`; the final nine are measured trials with `timing_eligible=true`. All 18 records passed schema, identity, filename, attempt-0, provenance, correctness, success, stable-input, monitoring, and linked-artifact hash/size checks. Static logical-identity reconstruction found all 18 records and predicted launched 0/reused 18 without invoking the runner. Before/after `(size, mtime_ns, SHA-256)` tuples were identical for every raw record.

Measured wall times, combined with the previously recorded Stage 3 CPU16/GPU baselines:

| Configurations | Prefix | CPU1 (s) | CPU4 (s) | CPU8 (s) | CPU16 (s) | GPU (s) | Winner |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| 1024 | 32 | 4.825855235998461 | 2.2148800249997294 | 1.6123988079998526 | 1.411638931997004 | 1.6263662540004589 | CPU16 |
| 3025 | 55 | 18.586236787996313 | 5.5287907120000455 | 3.319506758998614 | 2.4178249460019288 | 1.9363074720022269 | GPU |
| 10000 | 100 | 67.1935004170009 | 17.88604694699461 | 9.549780615998316 | 5.635352830999182 | 2.835080121003557 | GPU |

Applying the predeclared D-024 rule—retain an alternate CPU thread count only if it is at least 10% faster than CPU16 or changes the full candidate-set winner—pruned CPU1, CPU4, and CPU8. Their CPU16-normalized wall-time ratios at prefixes 32/55/100 were respectively CPU1 `3.418619/7.687172/11.923566`, CPU4 `1.569013/2.286679/3.173900`, and CPU8 `1.142218/1.372931/1.694620`; all were dominated. CPU16 and GPU were retained. This is one-repetition pilot evidence for candidate pruning, not a final performance claim; D-025 records the accepted outcome.

One read-only audit refinement was necessary: a broad commit-difference probe flagged newly added `src/autosbd/analysis.py`, which is not in the execution path. A narrowed comparison of the actual runner, config, feature, process, monitoring, and identity modules confirmed those execution paths were unchanged between the baseline and thread-pilot commits. No raw record or source file was modified by the audit.

### Combine and verify the Stage 3 evidence

Commands:

```bash
PYTHONPATH=src .venv/bin/python scripts/analyze_results.py <38 explicit paths: 20 Stage3 paths above followed by 18 paths above> --output-json results/processed/stage3_candidate_pilot.json --output-csv results/processed/stage3_candidate_pilot.csv
PYTHONPATH=src .venv/bin/python scripts/analyze_results.py <38 explicit paths: 20 Stage3 paths above followed by 18 paths above> --output-json results/processed/stage3_candidate_pilot.json --output-csv results/processed/stage3_candidate_pilot.csv
sha256sum results/processed/stage3_candidate_pilot.json results/processed/stage3_candidate_pilot.csv
```

Exit status: `0`. The first aggregation reported input 38, included 19, excluded 19, `json_changed=true`, and `csv_changed=true`. Its immediate identical rerun reported the same counts with `json_changed=false` and `csv_changed=false`. The JSON contains 38 rows; the CSV contains 39 lines including its header. All 19 exclusions are warm-up/timing-ineligible records.

- JSON SHA-256: `3e066afa35217cddba203df33b294966ce24227fa59d3e2267b64fc4ac36d17c`.
- CSV SHA-256: `b381cff4d7df939a9a5d593f4304ff4a6b4e253faeb728284ee91400eb479dee`.

### Freeze and validate the Stage 4 protocol

Frozen artifacts:

- `configs/stage4_final_crossover.yaml`: SHA-256 `e87e5ba6957b1f054a4973199a5ecad92ebca630093fb5d6bee6c5f3d00d8b70`; prefixes 32/55; one warm-up and five measured repetitions per CPU16/GPU candidate; 24 trials (4 warm-up, 20 measured); estimated 1.09 minutes.
- `configs/stage4_final_mid.yaml`: SHA-256 `f2dca217bd21c215ef708445c98e1d7994f6f9d0854022454ced19273f51a6bd`; prefixes 100/174; one warm-up and three measured repetitions per candidate; 16 trials (4 warm-up, 12 measured); estimated 4.11 minutes.
- `configs/stage4_final_large.yaml`: SHA-256 `784e8b3cecbdd010e526ade2b301a91a1b7b8ceefd151e9c20d59d8f39a62cac`; prefix 244; one warm-up and three measured repetitions per candidate; 8 trials (2 warm-up, 6 measured); estimated 8.15 minutes.
- `reports/stage4_protocol.json`: SHA-256 `29431c68e84cee75a280c5b5faf3d2a15f1eb2ec2c16f4f5ce37796ef5f307f6`; status `frozen_before_measurement`.

All shards use experiment name `stage4-amd-fe4s4-final-v1`, purpose `final`, seed 1729, timeout 300 seconds, and the validated correctness manifest. The protocol explicitly preserves separate reporting views to prevent double-counting the two configurations that also appeared in the pilot.

Validation command:

```bash
PYTHONPATH=src .venv/bin/python - <<'PY'
import hashlib
import json
from pathlib import Path
from autosbd.config import load_sweep_config
protocol = json.load(open('reports/stage4_protocol.json'))
assert protocol['status'] == 'frozen_before_measurement'
total = warmup = measured = 0
semantic_keys = set()
for shard in protocol['shards']:
    path = Path(shard['path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == shard['sha256']
    config = load_sweep_config(path)
    assert config.name == protocol['name']
    templates = config.trial_templates(randomize=True)
    assert len(templates) == shard['expected_total_records']
    assert sum(t.phase == 'warmup' for t in templates) == shard['expected_warmup_records']
    assert sum(t.phase == 'measured' for t in templates) == shard['expected_measured_records']
    keys = {t.semantic_key for t in templates}
    assert not semantic_keys.intersection(keys)
    semantic_keys.update(keys)
    total += len(templates)
    warmup += sum(t.phase == 'warmup' for t in templates)
    measured += sum(t.phase == 'measured' for t in templates)
for evidence_key in ('correctness_gate', 'candidate_pruning_evidence'):
    evidence = protocol[evidence_key]
    path = Path(evidence['path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == evidence['sha256']
assert {'warmup': warmup, 'measured': measured, 'total': total} == protocol['expected_campaign_records']
print({'shards': len(protocol['shards']), 'unique_semantic_keys': len(semantic_keys), 'warmup': warmup, 'measured': measured, 'total': total, 'status': 'PASS'})
PY
.venv/bin/python -m json.tool reports/stage4_protocol.json >/dev/null
sha256sum reports/stage4_protocol.json \
  configs/stage4_final_crossover.yaml \
  configs/stage4_final_mid.yaml \
  configs/stage4_final_large.yaml \
  results/processed/stage3_candidate_pilot.json \
  results/processed/stage3_candidate_pilot.csv
git diff --check
```

Exit status: `0`.

```text
{'shards': 3, 'unique_semantic_keys': 48, 'warmup': 10, 'measured': 38, 'total': 48, 'status': 'PASS'}
```

Documentation-check correction: the first post-edit validation batch exited `127` only because it invoked unavailable system `python`; its preceding heading, diff, and status checks passed. The command was not repeated unchanged; subsequent validation used the repository-local `.venv/bin/python`.

Final verification commands:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_stage4_protocol.py' -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
```

Exit status: `0`. The protocol-freeze test passed, and the complete standard-library suite passed 97/97.

An independent runner-identity audit also confirmed 48 unique logical identities and all 10 workload/backend correctness-manifest pairs.

Interpretation: the Stage 4 plan is frozen as three bounded, non-overlapping shards with 48 unique semantic/logical trials—10 warm-ups and 38 measured trials—and valid correctness provenance. No Stage 4 measurement was started in this block.

## 2026-08-01 — Execute and aggregate the frozen Stage 4 final timing protocol

- UTC execution/analysis window: approximately `2026-08-01 01:59–02:23`.
- Working directory: `/home/nagan/autosbd-sc26-rg`.
- Scope: execute the three already frozen final-timing shards sequentially, prove immutable reuse, audit the exact resulting record set, and aggregate only those explicit records. This block did not train or complete a selector and did not create figures.

### Per-shard preflight and provenance

The following read-only checks were performed before each of the crossover, mid, and large shards, using the corresponding frozen config in the final `sha256sum` argument:

```bash
git status --porcelain
git -C external/amd-sbd status --porcelain
git -C external/amd-sbd rev-parse HEAD
git -C external/amd-sbd remote get-url origin
sha256sum \
  build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu \
  build/upstream/amd-729cfa3a-nvhpc-26.5/diag_gpu \
  reports/stage3_calibration_manifest.json \
  configs/stage4_final_crossover.yaml
# The mid and large preflights substituted, respectively:
# configs/stage4_final_mid.yaml
# configs/stage4_final_large.yaml
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader,nounits
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits
free -b
uptime
```

All three preflights passed:

- `external/amd-sbd` was clean at official `AMD-HPC/amd-sbd` commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`, origin `https://github.com/AMD-HPC/amd-sbd.git`.
- NVHPC 26.5 CPU executable SHA-256: `190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07`.
- NVHPC 26.5 GPU executable SHA-256: `8f1481b6bcb4ddf3326453fd3a7c03dc36e29034629f46c5e982a4c17e43bc07`.
- Correctness-manifest SHA-256: `6fcc273d84f65d20185c0abcba9b750a29c2d64a87c982e500a4be5cdd93bdec`.
- Crossover-config SHA-256: `e87e5ba6957b1f054a4973199a5ecad92ebca630093fb5d6bee6c5f3d00d8b70`.
- Mid-config SHA-256: `f2dca217bd21c215ef708445c98e1d7994f6f9d0854022454ced19273f51a6bd`.
- Large-config SHA-256: `784e8b3cecbdd010e526ade2b301a91a1b7b8ceefd151e9c20d59d8f39a62cac`.
- The NVIDIA L4 was idle before every shard: 0 MiB used, 0% utilization, and no compute processes. Final timing ran sequentially; no final configurations overlapped.

### Sequential final runs and immutable reuse

Each command below was followed immediately by one identical invocation to verify resume behavior:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage4_final_crossover.yaml --require-all-success
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage4_final_crossover.yaml --require-all-success

PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage4_final_mid.yaml --require-all-success
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage4_final_mid.yaml --require-all-success

PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage4_final_large.yaml --require-all-success
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py configs/stage4_final_large.yaml --require-all-success
```

All six invocations exited `0`:

- Crossover first run: total 24, launched 24, reused 0, successful 24. Immediate identical rerun: launched 0, reused 24, successful 24.
- Mid first run: total 16, launched 16, reused 0, successful 16. Immediate identical rerun: launched 0, reused 16, successful 16.
- Large first run: total 8, launched 8, reused 0, successful 8. Immediate identical rerun: launched 0, reused 8, successful 8.
- Across the campaign there were no failures, timeouts, OOMs, or skips. The final immutable set contains 48 records: 10 warm-ups and 38 measured trials.

The exact 48 raw paths, in the deterministic aggregate input order, were:

```bash
stage4_records=(
  results/raw/107fbe8a96874d48fbf6cf07d9f91c5add6ca9602bfddb399a2fe261c997a3d8.json
  results/raw/17e441c1533540b70cc0cbe73299b02f7941e2db8d1107b82f1b796123fa5b36.json
  results/raw/1828d00372451f8eed4e72f9b7618f1ea567f653f0649955db96b3c730392530.json
  results/raw/18eec5181ee67326db2ebe31045cb90612c516eb73cfa75094b803c43e54a868.json
  results/raw/196b3131f5336aad7cd9c4ee5e7f3d8f515890d6f6134e6d7111bbc3a63edf7f.json
  results/raw/23c4bddd74dad174b71b7f603de6217283774f0e6ec3a76238bfcbd37322649a.json
  results/raw/2682ab52f394aa3332c4ce384f0eeb099e5222b30aa6512a2750213e61c8f025.json
  results/raw/26e34d766211ea7fffb19b527451db1d4e0e2fec45fc802a620584d36f0c94c5.json
  results/raw/2a3761bfb0e7d1da032304ab608bcd13e898bade945269c386049b8db2764dd4.json
  results/raw/2b1a872d08adf4dae18780d39c3bb3b6a633aff19b57e0eb4a78a70cea406546.json
  results/raw/2d7af29017a3bd241e7b73c2504be82e8419e9e1124daafb0b0d3aa37ddfa1fa.json
  results/raw/3242dcd76554d7c4a5771d59336b4ae5566bc9918edcada17184593dca344522.json
  results/raw/364c2dd8099b484e6fdeab99d39197da5051c4918f40a31faf02b059eb3e9699.json
  results/raw/36681c01f7984b94d63ba440ab7f22e2bd94707f838c4369380f9801b45b684a.json
  results/raw/3e678c24f0557fc0944c95780b793b32d2ad68a8ee3d842fb1db37ad16ea494a.json
  results/raw/469f3e9e0bfed5ce886a3fc8912e382ca839c3b15b28d04e8ef0188ccf02d85a.json
  results/raw/47c38818e4f6fe169e436aae1d5d7c8dd0b7fbae6a43d7041ef5d7da7292e964.json
  results/raw/49bdc6528a387317d71ad181d2781bc5da2c6c32ae7424737064f4bda960c4e0.json
  results/raw/4ef3e18770524d630983b87dc94e44eaf78bb19c51dde3badccdd25fb20ea1d3.json
  results/raw/59b9121a07f1615d994aedf7c68b836687b0eb1ad1e262a5d1a9a79a1e4d52c8.json
  results/raw/59d3cbb3055441d0d7168152439e2498c621d47c40ce248ed863243e538039ad.json
  results/raw/5ff4896b2b15bec48961a74f8f9cda4c142e834dbea71dfec53c874f6a06e29c.json
  results/raw/6311fb33ec3ecab681770bfc3f96fa6eef26c0ccab9ef12375dd11afbdca9dad.json
  results/raw/6bd677d64c28fdab2b1199ebdc0d85cb655d6e1a91ffbc0a77298bf5e9e4fee8.json
  results/raw/72d9ccb479bf5b08848e2ed58e403ab1f019fa2f4184bdb45f81e21df2de558f.json
  results/raw/8087a3105880ca163d7ebda8fa4893be8dcb3f4c77b1cd7dd9639553bd50f829.json
  results/raw/82ebcc264c25541f0a13ba78c4e1ba3fd63fc78df7334b1c1fce1fe53d5cefaa.json
  results/raw/a618280b1095aa1a879e8464877c7bb17f9ee0026f3fe2a5dba71822171ec9ce.json
  results/raw/a91ca983f96b931e6b837c868a483aa1696fc238577613fbe51f281e3b3b7ab9.json
  results/raw/ab0ae4126a47916620b0128fe8b3a0459b49dae9dfac87301427564b7c24744c.json
  results/raw/b1fb7cbf40909cb1b119bcb1a118af06caa1af2d6fb6535a8fd5065b151b2de5.json
  results/raw/b8463cd42b6ac55dacdc5abac5e9affc0e65c84a59dd084467ef3ce085673ca7.json
  results/raw/b8d1a6bd46a949791192ab58d59fcf8898313ce93ee5495004a6014ecfa428f3.json
  results/raw/bb355684dbac68a98351d6f79de503a41f210d047d6cf0446a5696e13a6542bf.json
  results/raw/bd327b11319cb72a7d8c74312308cfb091c9e37318ea64ff16af05aa93575ed4.json
  results/raw/c0fe60a66c19a581b8d1b3223116c9a54071125fbce6a427bd926fc9ab747496.json
  results/raw/c81319dfb3791ad00d4d559c0d9b09dd424a602ce7c629f8e52dfc91e0ec6e68.json
  results/raw/c847995688ac6961210aae0e1e5ee7eebc93301404e744ca672adbfebfdfd029.json
  results/raw/cd0fdd6068cb653f83090725dc598e16ed902e1d0425fac8e3638dfdccb126f6.json
  results/raw/d844fde93f05fe4bc4904139680868b4975fdf90f53e8e2e94ab73d0191b2af9.json
  results/raw/d9c7fa3c1087bd7d2da569a80803ed1313da2b42ddd302b61876387828a2dfcf.json
  results/raw/db2fd96b503d553e02bbd35e981f2e0c1019ed2f4ac603b664b7a5e8a551ac23.json
  results/raw/e284853e26527ba397dc55b81bf3e41aaa6e49bb07a1c9219172743b8918a976.json
  results/raw/e42646e72c03542753e41340f3aec8e5eb26c6326da06afbd3aa7faa69026a11.json
  results/raw/f16ec20bbfcfcc9cc28a1f90b9a114d9686f69f98ac1567e7b47b97ae7a21a7e.json
  results/raw/f304cde049ba0b9a8dd4a4598e3b2597b47dad11c306546a1a8753b8ad54b195.json
  results/raw/f3efd5c43424129519dfefe1f302cf742615d7225ab2a20a3451709a53000514.json
  results/raw/f8061e07c0be9a2a0dc834b4f1e8bd4eff5b91ce2585374c02bb56c0f6945196.json
)
```

### Strict record audit and deterministic aggregation

The first strict-audit probe stopped safely at `results/raw/107fbe8a96874d48fbf6cf07d9f91c5add6ca9602bfddb399a2fe261c997a3d8.json` with an artifact-map mismatch. This was a validator comparison issue: the correctness manifest's candidate-artifact entry contains the manifest-only `backend` key, while a run record's `build_artifact` contains the common `path`, `sha256`, and `size_bytes` fields. No record failed and no file was changed. A diagnostic invocation then exited with `ModuleNotFoundError: No module named 'autosbd'` because `PYTHONPATH=src` had been omitted. Neither failing diagnostic was repeated unchanged.

The corrected field-normalized audit used `PYTHONPATH=src`, loaded records with `autosbd.records.load_record`, compared common artifact fields, checked the frozen semantic-key set and all provenance/integrity/monitoring fields, and passed:

```text
{"audit":"PASS","records":48,"warmup":10,"measured":38,"timing_eligible":38,"all_success_correct":true}
```

The aggregator then received only the exact array above and was run twice without alteration:

```bash
PYTHONPATH=src .venv/bin/python scripts/analyze_results.py \
  "${stage4_records[@]}" \
  --output-json results/processed/stage4_final.json \
  --output-csv results/processed/stage4_final.csv
# The immediate second invocation used the identical array, order, and command.
sha256sum results/processed/stage4_final.json results/processed/stage4_final.csv
```

- First aggregation: exit `0`; input 48, included 38, excluded 10, `json_changed=true`, `csv_changed=true`.
- Immediate identical aggregation: exit `0`; input 48, included 38, excluded 10, `json_changed=false`, `csv_changed=false`.
- Final aggregate geometry: 48 rows, 10 candidate groups, and 5 workload comparisons. All 10 exclusions are warm-up/timing-ineligible records.
- JSON SHA-256: `58c6b6bc2454de9237a102a3d3d6b3628d0bb98b0f0758cf0353d9edc64885aa`.
- CSV SHA-256: `b60ffa4dcfff0c7c46cd0d4b89a9af876845a4f3bee965bca8946758981b0801`.

### Install the isolated analysis dependencies

The requested packages were installed only in the repository virtual environment:

```bash
.venv/bin/python -m pip install scikit-learn==1.7.1 matplotlib==3.10.5
.venv/bin/python -m pip check
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
df -h /home/nagan/autosbd-sc26-rg
git diff --check
```

The install exited `0`. Resolved relevant versions were:

```text
scikit-learn==1.7.1
matplotlib==3.10.5
numpy==2.2.6
scipy==1.15.3
joblib==1.5.3
threadpoolctl==3.6.0
contourpy==1.3.2
cycler==0.12.1
fonttools==4.63.0
kiwisolver==1.5.0
packaging==26.2
pillow==12.3.0
pyparsing==3.3.2
python-dateutil==2.9.0.post0
six==1.17.0
```

`pip check` passed with `No broken requirements found.` The full standard-library suite remained green at 97/97. The filesystem retained 59 GiB free. No system package, compiler, upstream source, raw record, or GPU state was changed by this virtual-environment installation. Model development and figure generation had not yet been performed or completed in this block.

## 2026-08-01 — Ingest completion handoff and gate preliminary Stage 5

Read and hash-identified `AGENTS.md` and `AutoSBD_SC26_Completion_Handoff_v2.md`, then checked Git state, the official AMD origin/commit/cleanliness, Stage 4 artifact hashes, host capacity, and L4 state with `wc`, `sha256sum`, `sed`, `git`, `nvidia-smi`, `uptime`, and `free`. Outcome: exit `0`; official source was clean at `729cfa3a5011fb805eb9e686a7711f6919836dcb`, recorded Stage 4 hashes matched, and the L4 was idle with 22,564 MiB free, 34 C, and no compute process. No solver was launched.

## 2026-08-01 — Run, repair, and verify the preliminary Stage 5 evaluator

The initial command failed before writing artifacts because the wrapper requested an absent `split_id` key:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_tuner.py \
  --config configs/stage5_size_heldout.yaml \
  --output-dir results/processed/stage5
```

Outcome: nonzero with `KeyError: 'split_id'`; no partial Stage 5 file remained. The unchanged failing command was not repeated. After replacing the two wrapper references with `split.name`, the focused artifact tests passed 3/3, Python compilation passed, and `git diff --check` passed. The repaired evaluation then ran with:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_tuner.py \
  --config configs/stage5_size_heldout.yaml \
  --output-dir results/processed/stage5 2>&1 | tee logs/stage5_evaluator_retry.log
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q \
  2>&1 | tee logs/stage5_full_tests_after_retry.log
```

Outcome: exit `0`; eight preliminary artifacts reported 30 balanced measurements, 10 candidate rows, one primary held-out instance, and five sensitivity folds. The complete suite passed 118/118 in 10.734 seconds.

## 2026-08-01 — Audit preliminary Stage 5 and implement Phase A3/A4

Read-only output/source inspection used `sha256sum`, `wc`, `jq`, `sed`, and `rg`; detailed outputs are saved in `logs/stage5_preliminary_structure_inspection.log`, `logs/stage5_preliminary_decision_inspection.log`, `logs/stage5_overhead_implementation_mapping.log`, `logs/phase_a_threshold_alias_diff_review.log`, and `logs/phase_a_traceability_format_and_validation_review.log`. Outcome: all JSON parsed, source hashes matched, split source-ID intersections were empty, and model copies agreed. One exploratory `jq` query assumed the wrong secondary nesting and emitted a diagnostic; corrected queries succeeded and changed nothing.

`apply_patch` changed threshold candidates to explicit always-GPU/geometric-midpoint/always-CPU kinds, retained JSON-null sentinels, centralized threshold dispatch, made registered order the deterministic tie break, reduced emitted policies to six, and retained the upstream-default mapping only as provenance. Validation used:

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_evaluation tests.test_evaluation_artifacts -v
PYTHONPATH=src .venv/bin/python -m py_compile \
  src/autosbd/evaluation.py tests/test_evaluation.py \
  tests/test_evaluation_artifacts.py
git diff --check
```

Outcome: exit `0`; 12/12 focused tests passed. A subsequent review found that YAML carried but did not fail-close on the new threshold declaration, so explicit config validation and a mutation test were added. One combined append patch failed on a report anchor and changed no file; it was split into verified narrow patches rather than repeated unchanged.

## 2026-08-01 — Complete Phase A validation and regenerate corrected Stage 5

The threshold/config/alias integration and new inference-overhead implementation were validated without running the timer:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
PYTHONPATH=src .venv/bin/python -m unittest tests.test_inference_overhead -v
PYTHONPATH=src .venv/bin/python -m py_compile \
  src/autosbd/inference_overhead.py scripts/measure_inference_overhead.py \
  tests/test_inference_overhead.py
git diff --check
```

Outcome: exit `0`; the complete suite passed 123/123 and the overhead-focused suite passed 5/5. The strict loader accepted the real model/dataset artifacts and resolved five candidate groups plus the shortest `1.4109253030037507 s` denominator.

The evaluator was run twice after A3/A4 changes:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_tuner.py \
  --config configs/stage5_size_heldout.yaml \
  --output-dir results/processed/stage5
# Immediate identical second invocation.
sha256sum results/processed/stage5/*
wc -l results/processed/stage5/*.csv
```

Outcome: exit `0`; the first invocation updated behavior-bound files, while the second reported `changed=false` for all eight artifacts. Counts became 36 predictions and 12 summaries plus headers. Corrected sensitivity changed the threshold result from the superseded preliminary 5/5 to 3/5, while both trees remained 4/5.

Inspection then found three null summary columns caused by wrapper/core key-name mismatches. `apply_patch` mapped `instances_total`, `failure_count`, and `geometric_mean_oracle_over_selected_valid_only` into the established artifact columns and added typed non-null assertions. An attempted temporary-output check was rejected before execution because its cleanup trap contained recursive removal; no file changed and the command was not repeated. Focused tests passed 3/3, and canonical regeneration produced 12 rows with no null fields. Final non-overhead Stage 5 hashes are recorded in `reports/STAGE5_PRELIMINARY_AUDIT.md`.

## 2026-08-01T14:06Z — Measure hot and load-plus-selection overhead

Preflight and the bounded CPU-only measurement used:

```bash
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw,power.limit --format=csv,noheader,nounits
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits
uptime
free -h
sha256sum results/processed/stage5/models.json \
  results/processed/stage5/balanced_dataset.json
/usr/bin/time -v env PYTHONPATH=src .venv/bin/python \
  scripts/measure_inference_overhead.py
```

Outcome: exit `0`; pre/post L4 state was 0 MiB used, 0% utilization, 22,564 MiB free, 34 C, and no compute process. One-minute CPU load was 0.00 and 122 GiB host memory was available. The run took 1.53 seconds with 114,560 KiB peak RSS and created exactly one immutable raw record. Hot 10,000-iteration median/p90/p95 were `38.65/42.6673/48.7131 us`; cold 100-iteration load-plus-selection median/p90/p95 were `929.11/936.1551/939.67855 us`. The hot median was `0.002739337080263366%` of the shortest measured SBD median. Raw and processed SHA claims were independently rehashed and matched.

## 2026-08-01 — Refresh internal documentation and verify Phase A

Updated only `README.md`, `PROJECT_CONTEXT.md`, `reports/RESULTS.md`, and `reports/LIMITATIONS.md` to replace stale Stage 4/5 status with hash-verified facts. Created the internal `reports/STAGE5_PRELIMINARY_AUDIT.md`; no abstract, summary, poster, poster source/copy, or other student submission content was created. Read-only `jq` probes with two guessed Stage 4 layouts returned null projections; direct schema inspection corrected the queries and no artifact changed.

Final verification used:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m pip check
git diff --check
jq empty results/processed/stage5/*.json \
  results/raw/inference_overhead/*.json
git -C external/amd-sbd remote get-url origin
git -C external/amd-sbd rev-parse HEAD
git -C external/amd-sbd status --short
sha256sum reports/stage4_protocol.json reports/stage4_completion.json \
  results/processed/stage4_final.json configs/stage5_size_heldout.yaml \
  results/processed/stage5/* results/raw/inference_overhead/*.json
PYTHONPATH=src .venv/bin/python scripts/evaluate_tuner.py \
  --config configs/stage5_size_heldout.yaml \
  --output-dir results/processed/stage5
```

Outcome: exit `0`; 123/123 tests passed, dependencies were consistent, all JSON parsed, Markdown/diff hygiene passed, every audit size/hash matched, all train/test record overlaps were zero, the official AMD checkout remained clean at `729cfa3a5011fb805eb9e686a7711f6919836dcb`, and the final evaluator reported `changed=false` for all eight deterministic artifacts. The reviewed local checkpoint scope contains the unchanged completion handoff, Phase A code/tests/config, internal reports/logs, ten processed Stage 5 files, and one immutable overhead raw record. Nothing has been pushed.

## 2026-08-01 — Prepare the Phase B1 N₂/H₂O provenance and correctness gate

The uploaded completion handoff was read without modification and retained at SHA-256 `8a0cbc219aff2de04698767b7d085186f850d351ffdaf1791e789553d8f5a203`. Read-only repository, source, format, and artifact inspection used:

```bash
git status --short
git -C external/riken-sbd remote get-url origin
git -C external/riken-sbd rev-parse HEAD
git -C external/riken-sbd describe --tags --exact-match HEAD
git -C external/riken-sbd status --porcelain=v1 --untracked-files=all
git -C external/amd-sbd remote get-url origin
git -C external/amd-sbd rev-parse HEAD
git -C external/amd-sbd status --porcelain=v1 --untracked-files=all
rg --files external/riken-sbd/data/n2 external/riken-sbd/data/h2o | sort
sha256sum external/riken-sbd/LICENSE.txt \
  $(rg --files external/riken-sbd/data/n2 external/riken-sbd/data/h2o | sort)
wc -cl $(rg --files external/riken-sbd/data/n2 external/riken-sbd/data/h2o | sort)
sha256sum external/amd-sbd/LICENSE.txt \
  build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu \
  build/upstream/amd-729cfa3a-nvhpc-26.5/diag_gpu
rg -n -i "phase b|density|N2|H2O|NORB|correctness manifest|compatib" \
  AutoSBD_SC26_Completion_Handoff_v2.md
rg -n "density|residual|iteration|energy|git_dirty|timing_eligible|monitor|offload|device" \
  scripts/build_calibration_manifest.py tests -g '*.py'
```

Outcome: exit `0`. The retained RIKEN checkout is clean at exact tag `v1.3.0`, commit `b71e1c3ed857fcb4fb05731dc285831c1afe9ebd`, origin `https://github.com/r-ccs-cms/sbd.git`, with Apache-2.0 license SHA-256 `b2bd772f0613e47353e1e4391f953d3de1958a12d0759f5cda48395f6f5ea759`. It is authorized as an input-data source only. Both retained FCIDUMPs and all 15 determinant files passed static structural inspection. The active solver artifacts remain the same official AMD CPU/GPU binaries, with SHA-256 values `190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07` and `8f1481b6bcb4ddf3326453fd3a7c03dc36e29034629f46c5e982a4c17e43bc07`. One delegated read-only probe initially addressed `external/riken-sbd/LICENSE` instead of `LICENSE.txt`; the corrected path succeeded, no file changed, and the unchanged failing probe was not repeated.

Created `reports/phase_b_input_inventory.json`, `scripts/validate_phase_b_inputs.py`, `tests/test_phase_b_inputs.py`, `reports/PHASE_B_COMPATIBILITY.md`, and the two smallest-input correctness configs. Hardened `scripts/build_calibration_manifest.py` so every record must have a positive integer orbital count and a density vector of exactly that length. Preparation validation used:

```bash
.venv/bin/python -m json.tool reports/phase_b_input_inventory.json
.venv/bin/python -m py_compile \
  scripts/validate_phase_b_inputs.py tests/test_phase_b_inputs.py \
  scripts/build_calibration_manifest.py tests/test_calibration_manifest.py
PYTHONPATH=src .venv/bin/python scripts/validate_phase_b_inputs.py
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_phase_b_inputs tests.test_calibration_manifest tests.test_config
git diff --check -- . ':(exclude)AutoSBD_SC26_Completion_Handoff_v2.md'
sha256sum reports/phase_b_input_inventory.json \
  scripts/validate_phase_b_inputs.py tests/test_phase_b_inputs.py \
  reports/PHASE_B_COMPATIBILITY.md \
  configs/phaseb_n2_correctness.yaml configs/phaseb_h2o_correctness.yaml
```

The first validator run failed closed before any solver execution because README `wc -l` values had been recorded as logical line counts. Both upstream README files lack a terminal newline: `awk` and strict byte decoding showed 17 N₂ logical lines and 15 H₂O logical lines. Only those two manifest integers were corrected; source sizes and hashes were unchanged. The corrected invocation exited `0`, reported 20 verified artifacts and 15 determinant files, and 19/19 focused tests passed, including full-validation hash tampering, structure tampering with recomputed metadata, duplicate-key/float/unknown-key rejection, and density-length tampering. Final preparation hashes are:

- input inventory: `0105bc73dea01e31f8a4230ec7c69f0bb903d8f53763eb5270b4f4bbaf0b9fc1`;
- validator: `2edc75749f9fb8740ba6880ff8d21ce315fe9a6201d030dd469ae54e69f97687`;
- validator tests: `98af6cd40f52faa6824ab4f55d4ac210c3641536456ddbf0208acd3491fab537`;
- compatibility report: `f168430bf31848e7fb225b707711d0271109e4debdd3cebdacfbc5d642662e23`;
- N₂ config: `63ad99fc22094b59c6617ff1aa35c16a410d263fcb15bd3b60530aa1f37ed891`;
- H₂O config: `73e0806e07e177eedbd97432b724ead36a784a342cbdca164667f6724da197b9`.

No solver, GPU kernel, RIKEN executable, build, download, package installation, or performance timing ran during this preparation block.

Full repository validation used:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m pip check
PYTHONPATH=src .venv/bin/python scripts/validate_phase_b_inputs.py
# Load both YAML files and call trial_templates(randomize=False).
git diff --check -- . ':(exclude)AutoSBD_SC26_Completion_Handoff_v2.md'
git -C external/amd-sbd status --porcelain=v1 --untracked-files=all
git -C external/riken-sbd status --porcelain=v1 --untracked-files=all
```

Outcome: 128/128 tests passed in 11.232 seconds; dependencies were consistent; the inventory validator passed; each Phase B config expanded to exactly two ordered templates, CPU then GPU; diff hygiene passed; and both upstream checkouts were clean. The first extra loader assertion mistakenly called nonexistent `SweepConfig.trials()` and exited `1` after all tests and inventory validation had already passed. Source inspection identified the public `trial_templates(randomize=False)` API; the corrected assertion exited `0`, and no project file changed because of the audit-command error.

## 2026-08-01 — Run the Phase B1 smallest N₂/H₂O correctness pairs

Preparation was checkpointed at clean project commit `b0324dd011b87c13a0902ada46f5a44f62a543a6`. Before every solver launch, `scripts/validate_phase_b_inputs.py` passed; project and both upstream source trees were clean apart from the runner's narrow allowance for newly generated raw JSON; `nvidia-smi` reported no compute process, 0 MiB used, 22,564 MiB free, 0% utilization, 34 C, and approximately 16.5 W; host memory availability was 122 GiB; and one-minute load was recorded. Project-native `extract_input_features` and `estimate_source_memory` reported:

```text
N2:  combined input 6976b0d5793326781b16b53b6ff8d7c76068bdd016bdd29aa4cbee3e6aab0deb
     57,121 configurations; 16,970,806 host-known bytes;
     2,159,488 GPU-known bytes; 603,979,776-byte host/GPU guard
H2O: combined input ee17c38802ca7e869797f014dbc4957e7b589cc2cb8e2f2068c37fc2af1a150d
     75,625 configurations; 25,070,256 host-known bytes;
     3,699,192 GPU-known bytes; 603,979,776-byte host/GPU guard
```

The guarded GPU totals of 606,139,264 and 607,678,968 bytes were below the contemporaneous `18,928,055,091`-byte admission limit. CPU ran first and each family stopped at its inspection gate before GPU launch:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py \
  configs/phaseb_n2_correctness.yaml \
  --no-randomize --max-trials 1 --require-all-success
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py \
  configs/phaseb_n2_correctness.yaml \
  --no-randomize --max-trials 2 --require-all-success
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py \
  configs/phaseb_h2o_correctness.yaml \
  --no-randomize --max-trials 1 --require-all-success
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py \
  configs/phaseb_h2o_correctness.yaml \
  --no-randomize --max-trials 2 --require-all-success
```

All four invocations exited `0`. Each first invocation launched one CPU record; each second invocation reused that CPU record and launched exactly one GPU record. Record IDs and SHA-256 values are:

- N₂ CPU `16cda11507164d29f1528889b61d9a1560105fe96791edf75e2187922c36f0a8`, record SHA `8c48f052a8453a75003de33df7427161fb8b7772b1e3d92374fac56f4a6e6eff`;
- N₂ GPU `3c190b275f4c7521631b333a22dad44249d57b7f13ca1715a4e4644e2670af23`, record SHA `7de8a685ac198d4811cb4e2eb98e53fab56ed8b025b78900d40838d6de72d593`;
- H₂O CPU `52b394f95cad7a1fca0d929ef1e099780ffb730c3156b48afa8d2270fef748d0`, record SHA `1809e64ae9634ec0db6d396f36ad5783cd2822e1558e34f2a6467f577a490d81`;
- H₂O GPU `15c1e429c88423849e587e132bbf588caa1545cc9e27270a63f4a23d2d0de716`, record SHA `fabb943bba3fe20fbf49c71a96ff49d8fbd9da9052803ae5753f16e3fdd41fcb`.

Record inspection and independent `sha256sum` checks confirmed exact official AMD build hashes, CPU `OMP_TARGET_OFFLOAD=DISABLED`, GPU `OMP_TARGET_OFFLOAD=MANDATORY`, explicit device 0, complete monitoring, positive GPU allocations, stable three-stage input descriptions, and matching stdout/stderr/resource hashes. One compact `jq` inspection initially queried nonexistent aliases `peak_host_memory_mb` and `input_stable`, which returned null. A corrected read of schema fields `peak_host_rss_mb` and `input_integrity` succeeded; no record changed.

Pairwise and combined manifests were built with:

```bash
PYTHONPATH=src .venv/bin/python scripts/build_calibration_manifest.py \
  results/raw/16cda11507164d29f1528889b61d9a1560105fe96791edf75e2187922c36f0a8.json \
  results/raw/3c190b275f4c7521631b333a22dad44249d57b7f13ca1715a4e4644e2670af23.json \
  results/raw/52b394f95cad7a1fca0d929ef1e099780ffb730c3156b48afa8d2270fef748d0.json \
  results/raw/15c1e429c88423849e587e132bbf588caa1545cc9e27270a63f4a23d2d0de716.json \
  --output reports/phaseb_n2_h2o_correctness_manifest.json
# Immediate identical second invocation.
```

Outcome: the combined builder exited `0`, validated two inputs, reported `written` then `unchanged`, and produced SHA-256 `fc73db40f756384e86852e8a7a12ec00fe8838db25683681aa12eceb9bdf38c5`. N₂ energy relative error was zero and density max difference was `3.1974e-14`; H₂O energy relative error was `5.5922e-16` and density max difference was `1.9984e-14`. Residuals were below `1e-8`, iteration counts matched exactly, and density lengths equaled `NORB`. All four records remain `timing_eligible=false`. No RIKEN solver ran.

Final B1 integration verification used the complete 128-test suite, `pip check`, the Phase B input validator, strict JSON parsing and explicit success/clean/timing-ineligible/input-stable assertions for all four raw records, combined-manifest regeneration, `git diff --check`, exact SHA-256 recomputation, post-run GPU telemetry, and both upstream cleanliness checks. Outcome: exit `0`; 128/128 tests passed in 11.250 seconds; dependencies were consistent; the 20-artifact inventory passed; all record assertions passed; manifest regeneration reported `unchanged`; hashes matched; the L4 returned to 0 MiB used, 0% utilization, 22,564 MiB free, 34 C, and no compute process; and both upstream trees were clean.

## 2026-08-01 — Prepare the Phase B2 deterministic N₂/H₂O size grid

Read-only handoff and artifact discovery used `rg --files`, `rg -n`, `jq`, `sha256sum`, `wc`, `sed`, `git status --short`, and `git diff --no-index` against the completion handoff, Phase B inventory/correctness manifest, Stage 4 completion/aggregate evidence, the new generator, and its tests. The first compact JSON query guessed nonexistent `.workloads`/`.pairs` keys and a nonexistent processed path; the corrected key/path discovery succeeded, no file changed, and the unchanged failing query was not repeated. `git diff --no-index /dev/null <new-file>` returned its expected status `1` because both reviewed files were new. The full 890-line implementation and test suite were subsequently read in bounded chunks. Comparison with `scripts/prepare_workloads.py` confirmed the same changed-only generation plus read-only immutable `--check` convention.

The generator implementation and validation commands were:

```bash
# Deterministically derive and pin the eight non-full prefix hashes from the
# exact official-parent input bytes; no repository output was created.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile \
  scripts/prepare_phase_b_workloads.py tests/test_prepare_phase_b_workloads.py

# This attempted test runner was unavailable and was not repeated.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q \
  tests/test_phase_b_inputs.py tests/test_prepare_phase_b_workloads.py
# Outcome: `.venv/bin/python: No module named pytest`.
# `.venv/bin/ruff` was also absent, so linting was skipped without installation.

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest -v \
  tests.test_phase_b_inputs tests.test_prepare_phase_b_workloads
```

Outcome: syntax validation passed and the available `unittest` runner passed 11/11 tests in 4.020 seconds. Coverage includes exact byte equality and nesting, full-parent identity, closed manifest fields, changed-only idempotency, read-only checking, source/inventory/output/manifest tamper failures, exact checkout origin/tag/commit/cleanliness, and safe output boundaries. No package was installed.

Repository data generation and immediate verification used:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/prepare_phase_b_workloads.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/prepare_phase_b_workloads.py --check
find data/derived/phase_b_prefixes -type f -printf '%P\t%s bytes\n' | sort
sha256sum data/derived/phase_b_prefixes/manifest.json
jq -c '.workloads[] | {workload_id,family_id,molecule,basis,half_determinant_count:.prefix.half_determinant_count,output_sha256:.output.sha256,fcidump_sha256:.companion_fcidump.sha256,norb:.electronic_structure.norb,nelec:.electronic_structure.nelec,expected_product_configurations}' \
  data/derived/phase_b_prefixes/manifest.json
git status --short
```

Outcome: exit `0`. Generation wrote exactly ten family-separated determinant files plus `manifest.json`; immediate `--check` reported `changed_files=[]`. Manifest SHA-256 is `852c6c99b279610b413e29472e4839fc178fc63e094b01275f4bf3aaae57d373`. N₂ half-list counts are 32, 55, 100, 174, and 239, producing 1,024, 3,025, 10,000, 30,276, and 57,121 configurations. H₂O counts are 32, 55, 100, 174, and 275, producing 1,024, 3,025, 10,000, 30,276, and 75,625 configurations. The full N₂/H₂O variants have exact parent SHA-256 values `73a28f6e6a26b06fbf4accf704f4112dca36ea53fe52ec40ed6379644b218dd2` and `ea94906047a1d081d493066478e9f009c07cb4286541f1781060081205fd5a67`. Total generated file payload is under 47 KiB. No solver, GPU kernel, network access, package installation, or timing experiment ran.

Independent source-byte verification used `cmp` for both full variants, `head -n N | cmp` for all eight shorter prefixes, and a manifest-versus-directory file count. Outcome: exit `0`; all ten data files match the exact expected parent bytes, the directory has exactly 11 files including its manifest, and the manifest hash remains `852c6c99b279610b413e29472e4839fc178fc63e094b01275f4bf3aaae57d373`.

## 2026-08-01 — Implement versioned family identity and immutable Fe₄S₄ augmentation

Implemented config schema 2 and raw-record schema 3 in `src/autosbd/config.py`, `src/autosbd/records.py`, `src/autosbd/runner.py`, and `scripts/build_calibration_manifest.py`, with focused tests in the four matching test modules. Config schema 1 remains the omitted default and continues emitting raw schema 2. Config schema 2 requires exact trimmed `family_id`, `molecule`, and `basis` fields and emits raw schema 3 with those values bound at the top level and in `logical_identity`. `problem_family` remains the sweep name. Calibration manifests remain byte-compatible for all-v2 inputs, emit schema 3 for all-v3 inputs, pair by `(family_id, problem_instance, input_sha256)`, and reject mixed raw schemas. A regression verifies that identical instance labels in distinct families do not collide.

Delegated verification passed 49/49 focused tests and then 143/143 repository tests. Independent review used complete `git diff`/`sed` reads, import-impact `rg`, and:

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest -q \
  tests.test_config tests.test_records tests.test_runner \
  tests.test_calibration_manifest tests.test_phase_b_inputs \
  tests.test_prepare_phase_b_workloads
.venv/bin/python -m pip check
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python scripts/prepare_phase_b_workloads.py --check
# Rebuild the four-record B1 manifest into an isolated /tmp directory, then cmp.
git diff --check
```

Outcome: exit `0`; 61/61 independently selected tests passed in 8.839 seconds; dependencies were consistent; prefix check changed nothing; and the rebuilt B1 manifest was byte-identical with SHA-256 `fc73db40f756384e86852e8a7a12ec00fe8838db25683681aa12eceb9bdf38c5`. The verification copy remains at `/tmp/autosbd-b2-verify.df4eM7/manifest.json`. The first attempted verification wrapper was rejected by the command safety layer before execution because it contained guarded recursive temporary cleanup; it changed nothing and was replaced by the non-deleting form.

Added `src/autosbd/family_registry.py`, `scripts/build_family_registry.py`, and `tests/test_family_registry.py`. The builder hard-binds the frozen completion/aggregate path, SHA, and size; verifies all 48 immutable schema-v2 raw records, IDs, exact input components, and complete feature agreement; derives five Fe₄S₄ workload entries; records every raw path/SHA/size and trial/logical ID; represents basis as null with `basis_status=upstream_not_reported`; and rejects unknown, ambiguous, inconsistent, or extra nested fields. Focused validation passed 7/7 tests in 0.411 seconds.

Registry generation used:

```bash
before_raw_chain=$(jq -r '.records[].raw_record.path' reports/stage4_completion.json \
  | sort | xargs sha256sum | sha256sum | cut -d ' ' -f 1)
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python scripts/build_family_registry.py
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python scripts/build_family_registry.py --check
after_raw_chain=$(jq -r '.records[].raw_record.path' reports/stage4_completion.json \
  | sort | xargs sha256sum | sha256sum | cut -d ' ' -f 1)
test "$before_raw_chain" = "$after_raw_chain"
sha256sum reports/stage4_fe4s4_family_registry.json
```

Outcome: exit `0`; generation reported changed and immediate check reported unchanged/verified. Registry ID is `86bb6e3954b0b6dc86ae831c6b754eb25d77f63a3e548e7c4bd88fb10858e631`; file SHA-256 is `cfeb5f60e29d01068c68b9d348739fba4b4e204e5165edce899aff5dfa94395d`; it maps 48 records to five workloads. The pre/post raw-chain digest is unchanged at `3bc6e00863305e08720aeb0949f1b0ceb80d2715af213cae5f7375629b66a91c`. No raw record, Stage 4 aggregate, completion attestation, or Stage 5-v1 artifact changed.

The read-only B3 campaign audit extracted exact B1 end-to-end walls and measured-only Stage 3 size scaling. The initial compact query used nonexistent raw aliases and included warmups; exact path discovery corrected it without file changes. Final inputs were N₂ CPU/GPU `5.836839927/1.299271674 s`, H₂O CPU/GPU `10.757544634/1.746693241 s`, and measured-only Fe₄S₄ sum/full ratios `1.50216726` CPU and `1.88101214` GPU. The resulting conservative plan budgets 1.55 minutes for 20 v3 correctness records, 3.09 minutes for 40 pilot records, and 4.64 minutes total before the approval stop. Current official GCP `g2-standard-32` [accelerator-optimized list pricing](https://cloud.google.com/products/compute/pricing/accelerator-optimized) was checked separately as `USD 1.734376528/hour`; projected pre-approval marginal cost is about `USD 0.134`, excluding disk, region/discount variation, and pathological repeated timeouts.

## 2026-08-01 — Freeze and validate the ten-workload raw-v3 correctness protocol

Added `configs/phaseb_n2_h2o_grid_correctness.yaml`, SHA-256 `d9ff3d497a0ba561016b5c22b12a29ad3db808b0fe3c2f68beef37ebb14fe99a`, and `tests/test_phase_b_grid_config.py`, SHA-256 `86293fb936fc6318b13b2102d371bd841e352214d9aaf00d441083e6e917854b`. The config uses schema 2; orders five N₂ then five H₂O workloads; binds exact family/molecule/basis and derived paths; retains the exact B1 CPU16/L4 candidates, build flags, solver, timeout, and seed; and specifies zero warmups, one correctness repetition, no reference values, and no prior timing authorization. In nonrandomized expansion it produces exactly 20 templates, CPU then GPU within every workload.

Focused validation passed 12/12 tests and independently pinned all determinant, FCIDUMP, combined-input, executable, solver-boundary, and manifest hashes. Full pre-checkpoint validation then used:

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m pip check
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python scripts/validate_phase_b_inputs.py
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python scripts/prepare_phase_b_workloads.py --check
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python scripts/build_family_registry.py --check
git -C external/amd-sbd status --porcelain=v1 --untracked-files=all
git -C external/riken-sbd status --porcelain=v1 --untracked-files=all
git diff --check
```

Outcome: exit `0`; 155/155 tests passed in 16.173 seconds; dependencies were consistent; the 20-artifact source inventory passed; both derived-input and Fe₄S₄ registry checks were unchanged; both upstream trees were clean; and diff hygiene passed. Factual status was updated in `README.md`, `PROJECT_CONTEXT.md`, `reports/RESULTS.md`, `reports/LIMITATIONS.md`, and `reports/PHASE_B_COMPATIBILITY.md` without claiming unrun correctness/timing or creating student-submission prose. No solver or GPU kernel ran in this preparation/validation block.

After the documentation review and one README clarification, the same full gate was repeated. Outcome: exit `0`; 155/155 tests passed in 16.143 seconds; `pip check` reported no broken requirements; the inventory, derived-prefix, registry, upstream-cleanliness, and diff checks all remained unchanged/passing.

## 2026-08-01T15:49Z–16:01Z — Execute and attest the ten-input Phase B2 schema-v3 correctness gate

Started from clean local project commit `477a132911bed1756d42e298ea3af69d7a10a9bb`. The active implementation remained the clean official `AMD-HPC/amd-sbd` commit `729cfa3a5011fb805eb9e686a7711f6919836dcb`; the RIKEN checkout supplied input bytes only. The frozen config SHA-256 was `d9ff3d497a0ba561016b5c22b12a29ad3db808b0fe3c2f68beef37ebb14fe99a`.

Static admission used `load_sweep_config`, `extract_input_features`, and `estimate_source_memory` plus the following live checks before every individual trial:

```bash
git status --short
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory --format=csv,noheader
cat /proc/loadavg
awk '/MemAvailable:/ {print $2 " KiB available"}' /proc/meminfo
```

All ten inputs produced 603,979,776-byte CPU-host, GPU-host, and GPU guards. The L4 had 22,564 MiB free, giving an 18,928,055,091-byte admission cap; every candidate was admitted. Host availability remained about 122 GiB. Preflights showed no compute process, 0 MiB used, 0% utilization, 33–34 C, and 16.48–16.53 W.

Four read-only verification mistakes failed without launching a solver or changing a project file and were not repeated unchanged:

1. The first static preflight imported `estimate_source_memory` from nonexistent `autosbd.resources`; it exited `1` with `ImportError`. Source inspection corrected both estimator imports to `autosbd.features`.
2. The next display block used nonexistent `WorkloadConfig.problem_instance`; it exited `1` with `AttributeError` after computing the first estimate. It was corrected to `workload.name` and the dataclass fields.
3. The first post-CPU checker queried obsolete top-level aliases (`purpose`, `solver_source_commit`, `upstream_git_dirty`, `convergence`, `validation`, `features`, and `resource_summary`) and exited `1`. The schema-v3 record itself loaded successfully and remained unchanged.
4. A second checker incorrectly required `correct=true` before pair-manifest construction and queried nonexistent nested cleanliness, `density_diagonal`, and `monitoring_complete` fields. It exited `1`; the corrected contract expects raw `correct=null`, uses `upstream_output.density`, `input_features.fcidump.n_orbitals`, and `host_complete`/`gpu_complete`, and verifies upstream cleanliness live.

The corrected first CPU checker passed before its GPU pair was exposed. The campaign then advanced one immutable template at a time with this exact cumulative command, issued individually with `N` equal to each integer from `1` through `20`:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_sweep.py \
  configs/phaseb_n2_h2o_grid_correctness.yaml \
  --no-randomize --max-trials N --require-all-success
```

After every CPU record, an inline `load_record` verifier checked schema 3, metadata, exact input/AMD/project identities, clean project state, correctness-purpose/timing-ineligible status, process/scientific success, convergence/residual, density length, unchanged inputs, CPU offload disablement, and host monitoring. Only after that passed was the paired GPU command issued. GPU verification additionally required mandatory offload, device assignment, GPU process observation, complete host/GPU monitoring, positive allocation, and CPU/GPU energy/density agreement. Every invocation exited `0`; cumulative resume reused all prior records and launched exactly one new record.

Outcome: 20/20 terminal successes, ten CPU and ten GPU, with no timeout, OOM, launch, parse, process, convergence, input-integrity, monitoring, or offload failure. All are zero-warmup, one-repetition correctness records with raw `correct=null` and `timing_eligible=false`. Maximum energy relative error was `9.134172443598369e-16`; maximum density absolute difference `5.252048795867381e-14`; maximum final residual `9.746200382889772e-9`; paired iterations were exact; GPU allocation ranged from 18 to 196 MiB. Diagnostic wrapper wall fields summed to 39.519474 seconds but are not performance evidence.

The manifest builder received the 20 explicit paths now embedded in `validated_inputs[].records`. Its exact command was:

```bash
PYTHONPATH=src .venv/bin/python scripts/build_calibration_manifest.py \
  "${records[@]}" --output reports/phaseb_n2_h2o_grid_correctness_manifest.json
```

The first invocation wrote ten pairs; an immediate identical invocation reported `status=unchanged`. Both SHA-256 values were `ba6bf82b63c9a8bdf2a5a513df914a9f1446605a0d4939cb53f7921527222829`. An independent auditor reconstructed all combined hashes/identities, verified every record/stdout/stderr/resource hash and size, checked resource CSV row counts, and rebuilt byte-identical output. One delegated help probe omitted `PYTHONPATH` and emitted `ModuleNotFoundError` through a pipeline whose outer status was masked; it wrote nothing and was corrected with `PYTHONPATH=src`.

## 2026-08-01 — Freeze and test the manifest-linked Phase B pilot

Added `configs/phaseb_n2_h2o_grid_pilot.yaml` and `tests/test_phase_b_pilot_config.py`. Every workload retains the correctness grid's exact input/metadata, receives its exact schema-v3 manifest reference value, and points to that manifest. Candidates and solver settings are identical at the dataclass boundary. Protocol is one warmup, one measured repetition, purpose `pilot`, seed 1729, 300-second timeout, prior correctness required, and default deterministic candidate randomization within workload/phase blocks.

```bash
PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_phase_b_pilot_config \
  tests.test_phase_b_grid_config \
  tests.test_calibration_manifest -v
.venv/bin/python -m py_compile tests/test_phase_b_pilot_config.py
sha256sum configs/phaseb_n2_h2o_grid_pilot.yaml \
  tests/test_phase_b_pilot_config.py
git diff --check
```

Outcome: exit `0`; 19/19 focused tests passed in 0.467 seconds. Expansion is exactly 40 trials: 20 warmups and 20 measured, with deterministic randomized candidate order differing from nonrandomized order. Config SHA-256 is `3519b8fd4e45d9a412dd85a1fae9c586ddf865c078ae4cbfeaa43ee1a5091d70`; test SHA-256 is `4e3037f6ede6d6ef5a262a21ed3a18ba25a6fe29332dbc229e2a39ccd39c7dc7`.

Final checkpoint validation used:

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m pip check
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python scripts/validate_phase_b_inputs.py
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python scripts/prepare_phase_b_workloads.py --check
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python scripts/build_family_registry.py --check
mapfile -t records < <(jq -r \
  '.validated_inputs[] | .records.cpu.path, .records.gpu.path' \
  reports/phaseb_n2_h2o_grid_correctness_manifest.json)
PYTHONPATH=src .venv/bin/python scripts/build_calibration_manifest.py \
  "${records[@]}" --output reports/phaseb_n2_h2o_grid_correctness_manifest.json
jq empty reports/phaseb_n2_h2o_grid_correctness_manifest.json "${records[@]}"
git -C external/amd-sbd status --porcelain=v1 --untracked-files=all
git -C external/riken-sbd status --porcelain=v1 --untracked-files=all
git diff --check
```

Outcome: exit `0`; 158/158 tests passed in 16.110 seconds; dependencies were consistent; input inventory passed; prefix and Fe₄S₄ registry checks were unchanged; the schema-v3 manifest rebuilt unchanged at the expected SHA; all 20 JSON records parsed and retained `timing_eligible=false`; the pilot expanded to 40 templates; both upstream trees were clean; stale-status and diff-hygiene checks passed.
