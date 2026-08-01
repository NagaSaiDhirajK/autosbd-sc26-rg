# Upstream source provenance

The directories below are Git submodules. Their algorithms, implementations, data, and notices remain upstream work and are not covered by this repository's MIT license. Preserve each upstream `LICENSE.txt` and attribution.

| Local path | Upstream | Exact ref | License | AutoSBD use |
|---|---|---|---|---|
| `external/amd-sbd` | https://github.com/AMD-HPC/amd-sbd | `sc26-artifacts` commit `729cfa3a5011fb805eb9e686a7711f6919836dcb` | Apache-2.0; RIKEN, AMD, and IBM notices | Primary paper-aligned CPU/GPU benchmark and selector implementation |
| `external/riken-sbd` | https://github.com/r-ccs-cms/sbd | tag `v1.3.0`, commit `b71e1c3ed857fcb4fb05731dc285831c1afe9ebd` | Apache-2.0; RIKEN notice | Historical-only source preserving prior CUDA/Thrust build, input, and smoke-test evidence; not an active AutoSBD backend |

The two January 2026 SBD papers name repository URLs but do not state a branch, tag, or commit. The pins above come from the project handoff plus direct repository inspection and must not be presented as paper-specified SHAs.

## AMD primary path and historical RIKEN context

The AMD artifact checkout documents an AMD ROCm/OpenMP-offload default targeting `gfx90a`, while its source comments also describe NVIDIA OpenMP target flags. The initial 2026-07-31 AMD GPU feasibility attempt was blocked by the then-installed compiler stack and ROCm-oriented defaults. That records an environment limitation at the time; it does not reject AMD as the primary implementation.

NVIDIA HPC SDK 26.5 was subsequently authorized for an external L4 build adaptation. AutoSBD compiles AMD CPU and GPU executables from the same pinned source without editing upstream files. L4-specific flags, compiler/MPI paths, executable hashes, and correctness results are recorded outside the submodule.

## Historical RIKEN build adaptation

The checked-in CPU configuration is a Homebrew/macOS example, and the checked-in GPU comments use NVIDIA HPC SDK. AutoSBD changed no upstream file during the historical Stage 1 probe. That probe's exact Linux/GCC and CUDA 12.9 nvcc commands are preserved in Git history, `reports/BUILD_PROVENANCE.md`, and local logs. The active `scripts/build_upstream.sh` deliberately exposes only official AMD CPU/GPU targets.

RIKEN `v1.3.0` uses CUDA's device-only `__popcll` intrinsic inside a `__host__ __device__` function. The forced-include header `include/autosbd/nvcc_compat.h` narrowly maps the four calls to the equivalent host/device compiler builtin. This is a build-compatibility shim, not an SBD algorithm change. CPU/GPU numerical validation is mandatory because nvcc reports cross-execution-space warnings elsewhere in the upstream headers.

This RIKEN build and its smoke evidence remain reproducible historical provenance. They are not an AutoSBD benchmark candidate, training source, or fallback selected by the active runner.

## Initialize and verify

```bash
git submodule update --init external/amd-sbd
git submodule status external/amd-sbd
scripts/build_upstream.sh amd-all
```

Build products are written under `build/upstream/` and are intentionally not tracked. Full build commands and compiler output belong under `logs/`; durable hashes and decisions belong under `reports/`.
