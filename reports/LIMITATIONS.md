# Current limitations and claim boundaries

Status date: 2026-08-01

This internal report records what the completed engineering, repeated-timing, and three-family selector evidence does not establish. It is not student-authored submission material.

## Workload coverage

- The selector-evaluated corpus contains three authentic chemistry families—Fe₄S₄, N₂, and H₂O—but only five correlated determinant-prefix instances per family. The 15 prefixes are not 15 independent chemistry systems.
- The primary evaluation is genuinely leave-one-family-out: every candidate and repetition from the held-out family is excluded from training. With only three folds/families, however, it cannot establish broad chemistry generalization or support narrow confidence intervals.
- Prefix size changes the selected subspace and energy. Within-family rows remain correlated, and Fe₄S₄'s basis is correctly recorded as unknown rather than inferred.

## Performance evidence

- The schema-v2 CPU/GPU pair is correctness-only. It used zero warmups and one repetition per backend while the harness worktree was uncommitted, so both records are explicitly timing-ineligible.
- The four Phase B1 N₂/H₂O records also use zero warmups, one repetition, and protocol purpose `correctness`. Their diagnostic wall fields cannot establish cross-family speedup, crossover, or selector benefit and remain `timing_eligible=false` even though the combined correctness manifest passes.
- The 20 homogeneous Phase B2 grid records likewise use zero warmups and one correctness repetition. All are `timing_eligible=false`; their diagnostic duration fields are excluded and provide no N₂/H₂O speedup, crossover, variance, or selector evidence.
- The one-repetition manifest-linked N₂/H₂O pilot remains planning and crossover-bracketing evidence only and is excluded from final medians/model rows. The later repeated Phase B campaign supplies eligible N₂/H₂O medians, but neither Stage 4 nor Phase B provides confidence intervals or independent-machine replication.
- CPU1/4/8 pruning also uses one measured repetition at only the three smallest sizes. It justifies retaining the consistently faster CPU16 candidate for the frozen deadline-bounded protocol, but it is not a general CPU scaling study.
- Only one GCP heterogeneous node has been exercised: 16 physical Intel Xeon cores/32 logical CPUs and one NVIDIA L4. Results cannot imply multi-node, other-accelerator, leadership-system, or exascale behavior.
- Stage 4 kept CPU and GPU timing candidates sequential under the node lock and used warmups, seeded randomized candidate order, repeated trials, and contemporaneous preflight telemetry. Ambient VM variation and single-node execution remain limitations.

## Correctness evidence

- Correctness is strong cross-backend agreement on identical bytes, convergence, energy, iteration count, and density. It is not comparison against an independently certified exact Fe₄S₄ energy: upstream supplies only an approximate, non-asserted value.
- The pinned upstream prints one density vector with a missing closing bracket. The parser performs one narrowly defined repair and records `density_bracket_repaired=true`; any other malformed output remains a parsing failure.
- The Stage 2 and five-input Stage 3 validation manifests prove the exact checked artifacts and criteria. They do not retroactively make their zero-warmup source trials eligible for performance analysis.
- The Phase B1 manifest still proves only its two exact full inputs. The separate schema-v3 Phase B2 manifest proves the ten exact grid hashes and permits a linked pilot, but nothing outside those hashes. The eight non-full prefixes are validated through CPU/GPU agreement, not independently certified chemistry energies.

## Harness and selector maturity

- The deterministic GPU guard was applied throughout the measured size range, and all candidates were admitted and completed. Because no candidate approached the cap and there were no OOMs or guard skips, near-cap estimate accuracy and infeasibility discrimination remain unvalidated.
- The selector, family-grouped splits, training-only threshold, shallow trees, regret analysis, and held-out-family evaluation are implemented and independently hardened. The full tree improves pooled selected/oracle runtime over the frozen size-only tree and threshold on this corpus, but 13/15 correct decisions across only three families is not universal generalization.
- This is not a comprehensive autotuner. It compares the already-pruned CPU16 and L4 GPU candidates only; `shuffle`, `bit_length`, cache/decomposition, MPI, other CPU thread counts, and other accelerators are outside the sealed evaluation.
- No confidence intervals, independent machine, repeated cloud environment, or multi-node validation is available. A single GCP CPU/L4 node and 15 correlated prefixes cannot establish production robustness or exascale behavior.
- Hot selector overhead is measured, but the `929.11 us` object-cold diagnostic includes model-file read/parse with uncontrolled OS page-cache state and must not be described as storage-cache-cold latency.
- Only the documented AMD command-line parameters are exposed. Unsupported or silently ignored flags, including the previously considered `--init`, are deliberately excluded.
- Historical RIKEN `v1.3.0` executable/build/smoke evidence is preserved for provenance only and is not an active implementation or comparison baseline. Phase B1 used exact pinned RIKEN-repository N₂/H₂O bytes only as licensed data after license, hash, format-compatibility, and same-official-AMD-binary correctness gates; no RIKEN executable ran, and this does not promote the RIKEN solver.

## Authorship boundary

Code, raw evidence, internal analysis, reproducibility reports, and organizational checklists may be prepared in this repository. The abstract, 800-word submission summary, poster, poster source/copy, portal prose, and final student interpretation must be written by the student.
