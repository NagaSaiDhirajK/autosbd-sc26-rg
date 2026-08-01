# Phase B N₂/H₂O Compatibility Gate

**Status:** static unchanged-input compatibility **PASS**; CPU/GPU correctness is
still pending.  This is an internal engineering record, not submission prose.
No solver was built or executed to produce this report, and no timing evidence is
created or admitted by this gate.

## Scope and implementation boundary

Phase B may reuse the authentic N₂ and H₂O input data retained from
`r-ccs-cms/sbd`, but every correctness and timing run must continue to use the
official `AMD-HPC/amd-sbd` CPU and NVIDIA OpenMP-offload GPU executables.  The
RIKEN solver is provenance for the data only: it must not be built, executed,
timed, trained on, selected, or promoted in the active pipeline.

The static review found no need to rename, convert, pad, truncate, reorder, or
otherwise modify the source inputs.  Any future need for an input conversion or
AMD source modification invalidates this PASS and triggers the stop conditions
below.

## Pinned provenance and licenses

| Role | Repository | Retained revision | Checkout state | License evidence |
|---|---|---|---|---|
| Sole active CPU/GPU implementation | `https://github.com/AMD-HPC/amd-sbd.git` | commit `729cfa3a5011fb805eb9e686a7711f6919836dcb` | clean | Apache-2.0, `external/amd-sbd/LICENSE.txt`, SHA-256 `ceab7171e789f741c6c2dba1525c7b70c07ff97c845c0921efaf26d70beeb7ab` |
| Input-data source only | `https://github.com/r-ccs-cms/sbd.git` | exact tag `v1.3.0`, commit `b71e1c3ed857fcb4fb05731dc285831c1afe9ebd` | clean | Apache-2.0, `external/riken-sbd/LICENSE.txt`, SHA-256 `b2bd772f0613e47353e1e4391f953d3de1958a12d0759f5cda48395f6f5ea759` |

The active AMD artifacts remain the same audited NVIDIA HPC SDK 26.5 builds from
the single unmodified AMD commit:

| Candidate | Artifact | Size (bytes) | SHA-256 |
|---|---|---:|---|
| CPU16 | `build/upstream/amd-729cfa3a-nvhpc-26.5/diag_cpu` | 797,304 | `190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07` |
| NVIDIA L4 GPU | `build/upstream/amd-729cfa3a-nvhpc-26.5/diag_gpu` | 2,021,216 | `8f1481b6bcb4ddf3326453fd3a7c03dc36e29034629f46c5e982a4c17e43bc07` |

The RIKEN data provenance pages are
`https://github.com/r-ccs-cms/sbd/tree/v1.3.0/data/n2` and
`https://github.com/r-ccs-cms/sbd/tree/v1.3.0/data/h2o`.

## Smallest complete upstream inputs

These are the exact full upstream `1e-3` determinant lists required for the
first correctness-only CPU/GPU pair in each family.

| Family | Role and path | Size (bytes) | SHA-256 | Verified structure |
|---|---|---:|---|---|
| N₂ / 6-31G | FCIDUMP: `external/riken-sbd/data/n2/fcidump.txt` | 437,951 | `dee67eb5e8aee2f099953a52d7910db59bc7b284ad03a8fa7ffd2a4ba8efcf33` | 10,329 lines: four-line `&FCI` header plus 10,325 integral records; `NORB=18`, `NELEC=14`, `MS2=0`; indices span 0–18 |
| N₂ / 6-31G | alpha determinants: `external/riken-sbd/data/n2/1em3-alpha.txt` | 4,541 | `73a28f6e6a26b06fbf4accf704f4112dca36ea53fe52ec40ed6379644b218dd2` | 239 unique, nonblank rows; each row has exactly 18 binary characters and seven occupied orbitals |
| H₂O / cc-pVDZ | FCIDUMP: `external/riken-sbd/data/h2o/fcidump.txt` | 1,124,056 | `a3c2302834a33dce7260e8050a3f5180e05dbba1bb748f3e2f6410a7eacbd94d` | 26,651 lines: four-line `&FCI` header plus 26,647 integral records; `NORB=24`, `NELEC=10`, `MS2=0`; indices span 0–24 |
| H₂O / cc-pVDZ | alpha determinants: `external/riken-sbd/data/h2o/h2o-1em3-alpha.txt` | 6,875 | `ea94906047a1d081d493066478e9f009c07cb4286541f1781060081205fd5a67` | 275 unique, nonblank rows; each row has exactly 24 binary characters and five occupied orbitals |

The AMD application sets `bdet = adet` after loading the alpha list.  That is the
intended closed-shell tensor-product-basis interpretation for these `MS2=0`
inputs: every validated alpha string contains `NELEC/2` electrons and the same
list supplies the beta strings.  The resulting product spaces are therefore
`239 × 239 = 57,121` configurations for N₂ and
`275 × 275 = 75,625` configurations for H₂O.

## Exhaustive static format checks

The review traced the official AMD application and readers rather than inferring
compatibility from filenames:

1. `applications/selected_basis_diagonalization/src/main.cc` sends `--fcidump`
   to `sbd::LoadFCIDump` and `--adetfile` to `sbd::LoadAlphaDets`, then copies
   the loaded alpha list into the beta list.
2. `include/sbd/framework/fcidump.h` accepts the supplied `&FCI ... &END`
   headers, extracts `NORB` and `NELEC`, and reads each integral as one floating
   value followed by four integer indices.
3. `include/sbd/chemistry/basic/makedeterminants.h` dispatches every `.txt`
   determinant file through the text reader.  `from_string` consumes exactly
   `NORB` characters and supports both the 18-orbital and 24-orbital inputs with
   the audited `bit_length=20` representation.
4. AMD and RIKEN `include/sbd/chemistry/basic/makeintegrals.h` are byte-identical,
   with SHA-256
   `d2851bc7aef68241464f925877ad54fa68b47c654fdfb2c88553e85cb15ef854`.
   The determinant-reader implementations are semantically identical for the
   text path used here.

An exhaustive read-only check covered both FCIDUMPs and all 15 retained N₂/H₂O
determinant files, not only the two smallest lists.  It verified:

- exactly one `&END` marker and the expected `NORB`/`NELEC` values;
- exactly five syntactically valid fields in every integral record;
- integer indices within `[0, NORB]`, including one nuclear-repulsion
  `0 0 0 0` record and at least one index equal to `NORB`;
- ASCII determinant rows containing only `0` and `1`;
- uniform row width equal to `NORB` and occupation equal to `NELEC/2`; and
- no blank or duplicate determinant rows.

The official AMD parser can therefore consume the exact retained bytes.  Dynamic
convergence and numerical agreement are deliberately not inferred from this
static result.

## MPI serialization precision caveat

The pinned AMD and RIKEN FCIDUMP loaders parse these source files equivalently,
but their MPI serialization differs.  RIKEN `v1.3.0` serializes floating-point
integrals in scientific notation with `max_digits10`; the pinned AMD
`serializeFCIDump` uses the default stream precision.  AMD then deserializes the
broadcast representation on every rank, including rank zero, so the active AMD
path may internally round source integrals.

This is not an input-format incompatibility and must not be "fixed" by altering
the inputs or switching solvers.  Both official AMD candidates execute the same
behavior, so identical-input CPU/GPU parity remains the primary correctness test.
The caveat does mean that an energy printed by a different upstream revision or
solver configuration is not an exact-value acceptance target.

## Upstream-energy evidence boundary

The retained README files report the following values for the smallest complete
lists:

| Family | Upstream README value | Permitted use |
|---|---:|---|
| N₂ `1em3-alpha.txt` | `-109.041511 Ha` | contextual provenance only |
| H₂O `h2o-1em3-alpha.txt` | `-76.2359376 Ha` | contextual provenance only |

These values do not independently certify the AMD run unless every solver and
serialization setting is proven identical.  A discrepancy from a README value
does not by itself fail Phase B when both official AMD candidates converge and
meet the exact cross-backend criteria below; any discrepancy must still be
reported, not hidden or hand-corrected.

## Correctness-only acceptance gate

Each N₂ and H₂O pair passes only when all of the following are true:

1. CPU and GPU records use the exact AMD commit and audited artifact hashes above,
   identical solver settings, and byte-identical FCIDUMP/determinant descriptions.
2. Each record is terminal `success`, its output parses completely, and it is
   converged with a finite final residual no greater than `1e-8`.
3. CPU and GPU iteration counts are exactly equal.
4. With
   `scale = max(abs(E_cpu), abs(E_gpu))`, the energy relative difference is zero
   when `scale == 0`, otherwise
   `abs(E_cpu - E_gpu) / scale`; it must be no greater than `1e-10`.
5. Both density vectors are finite, have the same length equal to `NORB`, and
   their maximum elementwise absolute difference is no greater than `1e-10`.
6. Input hashes are unchanged at initial inspection, immediately before launch,
   and after execution.  Record, stdout, stderr, and resource-log hashes verify.
7. The source worktree is clean; host monitoring is complete; the GPU record has
   mandatory target offload, an exact device-assignment line, and complete GPU
   monitoring; the standard idle-GPU and memory-feasibility gates pass before
   launch.
8. A deterministic validation manifest names both records, both exact binaries,
   and both exact input hashes and reports the pair as passed.

Correctness runs remain timing-ineligible regardless of any wall or solver time
printed in their records.  No N₂/H₂O timing may be admitted until the
validation manifest covers the exact input hashes to be timed.

## Stop conditions

Stop the affected family before timing and preserve all evidence if any of these
conditions occurs:

- the AMD or input-data origin, commit/tag, checkout cleanliness, executable
  hash, input size, or input SHA-256 differs from this gate;
- the exact AMD binaries cannot accept the files unchanged, or compatibility
  would require source modification, data conversion, or the RIKEN executable;
- GPU idleness cannot be established, estimated GPU memory exceeds 80% of current
  free VRAM or the project cap, telemetry is incomplete, or the five-minute
  correctness timeout is reached;
- either backend exits unsuccessfully, produces malformed/non-finite output,
  fails to converge, or lacks required offload/device evidence; or
- iteration, energy, residual, density, solver-identity, or input-integrity
  comparison fails any acceptance condition above.

Do not retry an unchanged failure more than once.  Do not delete, rewrite, or
reinterpret a failed raw record.  Report incompatibility or numerical failure,
diagnose it within the official AMD path, and do not silently combine cross-solver
measurements.
