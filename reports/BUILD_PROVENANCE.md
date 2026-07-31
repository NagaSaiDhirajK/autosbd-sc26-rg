# Upstream build provenance

## Source pins

| Implementation | URL | Ref | Commit | Source state |
|---|---|---|---|---|
| AMD SBD | https://github.com/AMD-HPC/amd-sbd | branch `sc26-artifacts` | `729cfa3a5011fb805eb9e686a7711f6919836dcb` | no upstream source edits |
| RIKEN SBD | https://github.com/r-ccs-cms/sbd | tag `v1.3.0` | `b71e1c3ed857fcb4fb05731dc285831c1afe9ebd` | no upstream source edits |

Both carry Apache-2.0 `LICENSE.txt` files. See `external/README.md` for attribution and pin rationale.

## Primary AMD-HPC NVHPC build

Date: 2026-07-31

`scripts/build_upstream.sh amd-all` compiles the two primary executables directly from the same unmodified AMD commit. It uses NVIDIA HPC SDK 26.5's `nvc++` through the bundled CUDA-aware HPC-X MPI wrapper.

CPU flags:

```text
-std=c++17 -O3 -tp=native -mp
-DSBD_TRADMODE -DUSE_DET_CACHE_OMP
```

GPU additions/replacements:

```text
-mp=gpu -gpu=cc89 -Minfo=mp
-DUSE_GPU -DUSE_HIJ_OMP_OFFLOAD
```

Both link the system OpenBLAS. The combined build completed in 58.32 s with peak compiler RSS 535,132 KiB. Each phase emitted 23 upstream unused-variable warnings (46 total), with no errors or fatal diagnostics. GPU compilation reported four kernels plus target data mappings and NVIDIA device routines; `cuobjdump` verified an embedded `sm_89` cubin.

| Binary | SHA-256 | Size (bytes) |
|---|---|---:|
| AMD CPU | `190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07` | 797,304 |
| AMD GPU (`sm_89`) | `8f1481b6bcb4ddf3326453fd3a7c03dc36e29034629f46c5e982a4c17e43bc07` | 2,021,216 |

Build log: `logs/stage1_amd_nvhpc_build.log`.

## Primary AMD identical-input correctness

The official artifact Fe₄S₄ sample has 36 orbitals, 54 electrons, 244 alpha and 244 beta half-determinants, and 59,536 product states.

| Input | SHA-256 |
|---|---|
| `fcidump_Fe4S4.txt` | `9a74e2035f76218f1d02aa641a5be256c0b685f0382b1612fc261117dd1b6e93` |
| `AlphaDets.txt` | `b1aa7e60cfde6adc39f9271bb2c6d8d15774a694e746e66bab44db9842748f68` |

Both backends used one MPI process, matrix-free method 0, block size 10, at most six Davidson restarts, residual tolerance `1e-8`, no shuffle, `bit_length=20`, and identical remaining options. CPU used 16 bound OpenMP threads; GPU used one host thread, `CUDA_VISIBLE_DEVICES=0`, and mandatory OpenMP target offload.

| Metric | AMD CPU | AMD GPU canonical rerun |
|---|---:|---:|
| Final residual norm | `8.931146441578446e-09` | `8.931494922593578e-09` |
| Final energy (Ha) | `-326.6982536731583` | `-326.6982536731581` |
| End-to-end wall (s) | 78.15 | 17.22 |
| Peak host RSS (KiB) | 47,080 | 147,536 |
| Peak sampled GPU allocation (MiB) | 0 | 206 |

The canonical GPU log explicitly records `OMP_TARGET_OFFLOAD='MANDATORY'` and `rank 0 has device 0`; telemetry reached 100% utilization, 41 °C, and 42.23 W. A preceding GPU run produced exactly the same final residual, energy, and density tuple.

Project-defined acceptance at the paper-motivated strictness passes:

- both residuals are at most `1e-8`;
- energy absolute error is `2.2737367544323206e-13 Ha` and relative error is `6.959745663982201e-16`, below `1e-10`;
- maximum absolute density difference is `2.7017277304253184e-13`, below `1e-10`.

The only upstream Fe₄S₄ reference is the approximate, non-asserted `-326.70 Ha`; these results round to it. Exact agreement criteria above are explicitly AutoSBD validation criteria, not an upstream-provided golden-energy tolerance. Machine-readable evidence is in `reports/stage1_amd_correctness.json`; raw logs are named `logs/stage1_amd_cpu_fe4s4_t16_i6.*` and `logs/stage1_amd_gpu_fe4s4_i6_rerun1.*`. These single correctness runs are not final performance measurements.

## Historical preliminary CPU builds

Date: 2026-07-31

AMD artifact CPU command:

```bash
make -C external/amd-sbd/applications/selected_basis_diagonalization/src \
  GPU=0 CXX=mpicxx LDFLAGS='-fopenmp -lopenblas' VERBOSE=1
```

- Compiler path: `/usr/bin/mpicxx`, GCC 11.4.0 backend
- Effective compile flags printed by upstream: `-std=c++17 -fopenmp -O3 -march=native -funroll-loops -DSBD_TRADMODE -DUSE_DET_CACHE_OMP`
- Binary SHA-256: `89879a112ffec29175f6ceb748718de339a8160b0110d0ae4d48456893a77dc3`
- Binary size: 636,472 bytes
- Log: `logs/stage1_amd_cpu_build.log`

RIKEN CPU command:

```bash
make -C external/riken-sbd/apps/chemistry_tpb_selected_basis_diagonalization diag \
  CCCOM=mpicxx \
  CCFLAGS='-std=c++17 -fopenmp -O3 -march=native' \
  SYSLIB='-fopenmp -lopenblas'
```

- Compiler path: `/usr/bin/mpicxx`, GCC 11.4.0 backend
- Binary SHA-256: `2e0217d52f5d52e173b63869ea80eefde9d4e6a14934b82c72c7cd43ba7d43d9`
- Binary size: 602,008 bytes
- Log: `logs/stage1_riken_cpu_build.log`

Both binaries dynamically link OpenMPI, GNU OpenMP, and the system OpenBLAS alternative.

## Historical RIKEN direct nvcc feasibility probe

Pinned RIKEN source compiled successfully with CUDA 12.9.41 nvcc using `-x cu -std=c++17 -O3 -arch=sm_89 --expt-relaxed-constexpr -DSBD_THRUST`, OpenMPI include/link flags, host OpenMP, BLAS/LAPACK, and the tracked forced-include compatibility header.

The final temporary probe binary was 1,761,024 bytes with SHA-256 `9737907c95463762c971bb422ae7f7cd0a61df64310235d149d19c807e9d1784`. `cuobjdump` found two `sm_89` cubins plus `sm_89` PTX and named SBD/Thrust kernels. The build completed in 28 seconds with zero errors and 43 upstream-header warnings; no SBD workload was run from the temporary probe.

An earlier form of `scripts/build_upstream.sh` reproduced these contingency binaries before D-012 restored AMD as the primary path:

| Binary | SHA-256 | Size (bytes) |
|---|---|---:|
| AMD artifact CPU | `619bd93e7b6d5caeaa21a4ec49c7b4bfdcdb94d302a6c34abd0373af7967682a` | 636,472 |
| RIKEN CPU | `f56fa5878d45be8f2b13dbfe98e0b09aca024c72cea9775093f3e28efc57bef2` | 602,008 |
| RIKEN GPU (`sm_89`) | `4c21c06b6d617d757b6f53d24d8e1649d622a8e285a33aad211d7914980c8b20` | 1,761,024 |

`cuobjdump --list-elf` verified two embedded `sm_89` cubins in the tracked-script GPU build. Binary hashes are build identifiers for these invocations; compiler-generated metadata may make a later correct rebuild byte-different, so source pins, full commands, compiler versions, and per-build hashes are all retained.

## Historical RIKEN CPU correctness smoke

- Family/instance: N₂/6-31g, upstream `1em3`
- Alpha and beta half-determinants: 239 each
- Product-space configurations: 57,121
- FCIDUMP SHA-256: `dee67eb5e8aee2f099953a52d7910db59bc7b284ad03a8fa7ffd2a4ba8efcf33`
- Half-determinant SHA-256: `73a28f6e6a26b06fbf4accf704f4112dca36ea53fe52ec40ed6379644b218dd2`
- Backend: RIKEN CPU, one MPI rank, one OpenMP thread, one OpenBLAS thread, no shuffle, `bit_length=20`
- Solver: matrix-free Davidson, block 10, four restart allowance, requested residual tolerance `1e-8`
- Exit status: 0
- Final residual: `9.745846817253461e-09`
- Energy: `-109.0416210980518 Ha`
- End-to-end wall time: 40.90 s
- Peak RSS: 37,472 KiB
- GPU use: none

RIKEN `v1.3.0`'s rounded N₂ README table lists `-109.041511 Ha`, about `1.10e-4 Ha` away. The later AMD-synchronized N₂ documentation lists `-109.04162110 Ha`, agreeing with the computed value to the displayed precision. This result is retained as historical fallback evidence only; it is not the primary AutoSBD validation.
