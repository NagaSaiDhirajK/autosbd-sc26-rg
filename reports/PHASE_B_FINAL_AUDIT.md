# Phase B Final N₂/H₂O Timing Audit

Date: 2026-08-01
Status: complete; independently audited
Evidence role: internal engineering/scientific report, not student submission prose

## Scope and authorization

This audit covers the frozen repeated CPU16-versus-L4 campaign for the authentic
N₂/6-31G and H₂O/cc-pVDZ inputs. The user explicitly approved the campaign after
reviewing the measured pilot projection. The 300-second value was used only as
a per-trial hang/pathology cap; no trial approached it or was killed by it.

Every run used the official `AMD-HPC/amd-sbd` source at commit
`729cfa3a5011fb805eb9e686a7711f6919836dcb`. CPU16 and NVIDIA L4 OpenMP-offload
executables came from the same exact commit and NVIDIA HPC SDK 26.5 toolchain.
The retained RIKEN checkout supplied pinned input bytes only; no RIKEN solver
was built, run, timed, trained on, or selected in this campaign.

## Bound artifacts

| Artifact | SHA-256 |
| --- | --- |
| Frozen final protocol, `reports/phaseb_final_protocol.json` | `bf5b27d5213e02b08c5836e7a91da4702431d7c6ee9b01c58d76d660add73e98` |
| Crossover config | `f9aedb1eb33d419f7a7ff0103e284259926aa522e139845a11b3d4a68abcd990` |
| Broad config | `755ccfa48ae7830d494d6b0c0a3617df82eb5a86c79fae6a0deb00c0c6425398` |
| Headline config | `1807f183eab5d4732ae28ef8a7c3bf9becb17013870246e4d03eda9969519c2e` |
| Correctness manifest | `ba6bf82b63c9a8bdf2a5a513df914a9f1446605a0d4939cb53f7921527222829` |
| CPU16 executable | `190525bd05ff0b453e02e1762f7f221bac3e5da713e5d1d2999def3b0290ef07` |
| L4 executable | `8f1481b6bcb4ddf3326453fd3a7c03dc36e29034629f46c5e982a4c17e43bc07` |
| Final aggregate JSON | `f7deacc86e923614fded5f8e6bdfa7206fe8339e3a4d035d6db7ee967212768d` |
| Final aggregate CSV | `755cf8c6a35a260eec39ffc61d8a24028e99c3916057d8ec9b1151ffb6a58244` |
| Final completion attestation | `9a75df34696ee05e683e50ce4583eaefcfbbed4f8f8265b3836a892ce0c7326d` |

All records bind clean project commit
`834af59c4663998e855e7442caf718850bfc60b1` and harness SHA-256
`df93472367bf42b2453748df56330ee4013760d6a8db34405cb1bc2e6c45505e`.

## Exact geometry and eligibility

| Shard | Workloads | Warmups | Measurements | Total |
| --- | ---: | ---: | ---: | ---: |
| Crossover: N₂/H₂O 55 and 100 | 4 | 8 | 40 | 48 |
| Broad: N₂/H₂O 32 and 174 | 4 | 8 | 24 | 32 |
| Headline: N₂ 239 and H₂O 275 | 2 | 4 | 20 | 24 |
| **Total** | **10** | **20** | **84** | **104** |

The audit found 104 unique canonical trial IDs and 104 unique logical IDs, all
attempt index zero. Exactly 52 records use CPU16 and 52 use L4. Every warmup is
timing-ineligible; every measured record is timing-eligible. The three shard
files share one sweep name, so the raw record does not directly name its YAML
file, but their workload sets are disjoint and resolve ownership uniquely.

## Independent integrity result

The independent read-only audit loaded every record through the strict project
validator and reconstructed expected config templates, canonical identities,
input/component hashes, build bindings, validation evidence, and resource-log
claims. It also regenerated the correctness manifest object- and byte-identically.

All 104 records passed:

- process, parser, convergence, residual, reference-energy, and density checks;
- exact official source, compiler/build, binary, config, input, and manifest
  provenance;
- initial/before-launch/after-run input byte equality;
- empty successful GPU-process queries and idle L4 preflights;
- CPU target-offload disabled; GPU target-offload mandatory on CUDA device 0;
- complete host monitoring and complete process-observed GPU monitoring;
- static host/GPU guards below recorded caps;
- resource CSV row/sample and peak-value consistency;
- paired CPU/GPU energy, density, and iteration agreement; and
- sequential timestamps with zero overlapping trial intervals.

No timeout, OOM, skip, launch, parse, scientific, correctness, monitoring,
input, provenance, or resource anomaly occurred.

## Final measured medians

`CPU/L4` is median CPU16 end-to-end wall time divided by median L4 wall time.
Values above one favor L4. IQRs use the preregistered deterministic percentile
method; no interpolation is used between measured workload sizes.

| Family | Configurations | CPU16 median (s) | CPU IQR | L4 median (s) | L4 IQR | CPU/L4 | Winner |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| N₂ | 1,024 | 0.607656 | 0.000346 | 0.791775 | 0.000665 | 0.767460 | CPU16 |
| N₂ | 3,025 | 0.707902 | 0.000388 | 0.786233 | 0.005360 | 0.900372 | CPU16 |
| N₂ | 10,000 | 1.110516 | 0.001125 | 0.995270 | 0.004767 | 1.115794 | L4 |
| N₂ | 30,276 | 3.020428 | 0.000209 | 1.126547 | 0.028935 | 2.681138 | L4 |
| N₂ | 57,121 | 5.936789 | 0.000694 | 1.308605 | 0.001763 | 4.536732 | L4 |
| H₂O | 1,024 | 0.607208 | 0.000465 | 0.842173 | 0.031098 | 0.721002 | CPU16 |
| H₂O | 3,025 | 0.708406 | 0.000305 | 0.980570 | 0.052381 | 0.722443 | CPU16 |
| H₂O | 10,000 | 1.311406 | 0.000394 | 0.993132 | 0.002685 | 1.320475 | L4 |
| H₂O | 30,276 | 3.624439 | 0.001227 | 1.311358 | 0.048623 | 2.763883 | L4 |
| H₂O | 75,625 | 10.965016 | 0.101867 | 1.754983 | 0.064964 | 6.247934 | L4 |

N₂ and H₂O both flip between measured sizes 3,025 and 10,000. Fe₄S₄ final
evidence instead favors L4 at 3,025, creating a same-size family-dependent
winner. This makes leave-one-family-out comparison against a training-only
universal size threshold scientifically meaningful. It does not guarantee that
the full-feature model will improve; the result must be reported either way.

The largest within-cell timing spread is N₂-55 on L4: minimum 0.782102658 s,
median 0.786232874 s, and maximum 0.869959851 s. Repetition 4 is 10.65% above
the median. It passed every gate and remains in the raw evidence and aggregate.

## Time, resources, and cost

- First start: `2026-08-01T17:09:52.635682Z`
- Last finish: `2026-08-01T17:14:32.621553Z`
- Sequential span: 279.985871 seconds
- Sum of per-record process wall: 212.774595652 seconds
- Peak host RSS: 138.078125 MiB
- Peak GPU allocation: 196 MiB
- Minimum preflight free L4 memory: 22,564 MiB
- Maximum preflight L4 temperature: 39 °C
- Maximum static guard: 603,979,776 bytes
- Approximate span cost: USD 0.13489 at the repository-recorded
  USD 1.734376528/hour rate; the rate was not independently refreshed here

The campaign completed below its 7.55063-minute/approximately USD 0.21826 pilot
projection. The 300-second cap was never the observed duration of a run.

## Analysis and claim boundary

The deterministic final aggregate contains all 104 rows, includes the 84
eligible measurements, excludes exactly the 20 warmups, and reproduced
byte-identically on an immediate second run.

`reports/phaseb_final_completion.json` is a 101,178-byte deterministic
machine-readable attestation. It binds the protocol and aggregate to all 104 raw
path/size/SHA claims, rebuilds the aggregate exactly, records the 60-ID balanced
view, and attests zero overlap. Its raw-inventory chain is
`ead9e2e0558bdf28079e3902f712aa33842efe979066ada7dd65a87cfd67b3e2`,
using the definition stored in that completion artifact.

For balanced three-family selector evaluation, use only measured repetitions
0, 1, and 2 from every instance/candidate. This yields 60 N₂/H₂O measurements;
with the existing 30 Fe₄S₄ measurements, the balanced dataset has 90 source
measurements, 30 candidate medians, and 15 independent problem instances.
Pilot, correctness, warmup, and repetitions 3–4 remain outside that evaluation.

This evidence supports repeated two-backend timing across N₂ and H₂O on the
documented single heterogeneous node. It does not yet establish low held-out
selector regret, improvement beyond size, broad hardware generalization,
multi-node scaling, comprehensive parameter autotuning, or OOM-boundary
avoidance. Those claims require their separate gates.
