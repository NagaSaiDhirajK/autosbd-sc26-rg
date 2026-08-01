#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
target="${1:-amd-all}"

amd_sha="729cfa3a5011fb805eb9e686a7711f6919836dcb"
amd_url="https://github.com/AMD-HPC/amd-sbd"
amd_dir="$project_root/external/amd-sbd"
build_root="$project_root/build/upstream"
nvhpc_root="${NVHPC_ROOT:-/opt/nvidia/hpc_sdk/Linux_x86_64/26.5}"
nvhpc_compiler_dir="$nvhpc_root/compilers/bin"
nvhpc_mpi_dir="$nvhpc_root/comm_libs/mpi/bin"
nvhpc_cxx="$nvhpc_compiler_dir/nvc++"
nvhpc_mpicxx="$nvhpc_mpi_dir/mpic++"

usage() {
    echo "Usage: $0 [amd-all|amd-cpu|amd-gpu]" >&2
}

if [[ "$target" != "amd-all" && "$target" != "amd-cpu" && \
      "$target" != "amd-gpu" ]]; then
    usage
    exit 2
fi

for required in git sha256sum; do
    if ! command -v "$required" >/dev/null 2>&1; then
        echo "Required tool not found: $required" >&2
        exit 1
    fi
done

origin_url="$(git -C "$amd_dir" remote get-url origin)"
if [[ "${origin_url%.git}" != "$amd_url" ]]; then
    echo "AMD checkout origin is not the official $amd_url" >&2
    exit 1
fi
if [[ "$(git -C "$amd_dir" rev-parse HEAD)" != "$amd_sha" ]]; then
    echo "Official AMD checkout is not pinned at $amd_sha" >&2
    exit 1
fi
if [[ -n "$(git -C "$amd_dir" status --porcelain)" ]]; then
    echo "Official AMD checkout has local modifications" >&2
    exit 1
fi
mkdir -p "$build_root"
temporary_build="$(mktemp -d "$build_root/.tmp.XXXXXX")"

run() {
    printf '+'
    printf ' %q' "$@"
    printf '\n'
    "$@"
}

build_amd_cpu() {
    local output_dir="$build_root/amd-${amd_sha:0:8}-nvhpc-26.5"
    local temporary_binary="$temporary_build/amd_diag_cpu"
    require_amd_toolchain
    mkdir -p "$output_dir"
    run env PATH="$nvhpc_compiler_dir:$nvhpc_mpi_dir:$PATH" \
        "$nvhpc_mpicxx" \
        -std=c++17 -O3 -tp=native -mp \
        -DSBD_TRADMODE -DUSE_DET_CACHE_OMP \
        -I"$amd_dir/include" \
        "$amd_dir/applications/selected_basis_diagonalization/src/main.cc" \
        -o "$temporary_binary" -lopenblas
    mv "$temporary_binary" "$output_dir/diag_cpu"
    sha256sum "$output_dir/diag_cpu"
}

build_amd_gpu() {
    local output_dir="$build_root/amd-${amd_sha:0:8}-nvhpc-26.5"
    local temporary_binary="$temporary_build/amd_diag_gpu"
    require_amd_toolchain
    mkdir -p "$output_dir"
    run env PATH="$nvhpc_compiler_dir:$nvhpc_mpi_dir:$PATH" \
        "$nvhpc_mpicxx" \
        -std=c++17 -O3 -tp=native -mp=gpu -gpu=cc89 -Minfo=mp \
        -DSBD_TRADMODE -DUSE_GPU -DUSE_DET_CACHE_OMP \
        -DUSE_HIJ_OMP_OFFLOAD \
        -I"$amd_dir/include" \
        "$amd_dir/applications/selected_basis_diagonalization/src/main.cc" \
        -o "$temporary_binary" -lopenblas
    mv "$temporary_binary" "$output_dir/diag_gpu"
    if command -v cuobjdump >/dev/null 2>&1; then
        cuobjdump --list-elf "$output_dir/diag_gpu"
    fi
    sha256sum "$output_dir/diag_gpu"
}

require_amd_toolchain() {
    if [[ ! -x "$nvhpc_cxx" || ! -x "$nvhpc_mpicxx" ]]; then
        echo "NVIDIA HPC SDK compiler/MPI not found under $nvhpc_root" >&2
        exit 1
    fi
}

case "$target" in
    amd-all)
        build_amd_cpu
        build_amd_gpu
        ;;
    amd-cpu)
        build_amd_cpu
        ;;
    amd-gpu)
        build_amd_gpu
        ;;
esac

rmdir "$temporary_build"
echo "Build completed for target: $target"
