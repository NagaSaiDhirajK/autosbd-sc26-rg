# Current limitations and claim boundaries

Status date: 2026-08-01

This internal report records what the completed engineering, repeated-timing, and current single-family selector evidence does not establish. It is not student-authored submission material.

## Workload coverage

- The timed and evaluated corpus currently contains one authentic chemistry family: Fe₄S₄. Phase B compatibility/correctness work for additional N₂/H₂O data is approval-gated and has not run.
- Determinant-prefix sizes derived from Fe₄S₄ can locate a size crossover, but they change the selected subspace and energy and are not independent chemical families. Evaluation must label them as size-held-out, not family-held-out.
- With only one family, leave-one-family-out generalization is impossible. The current evaluation groups all repetitions and candidates for a derived instance together, but its largest-size holdout and leave-one-instance-out folds remain size-based evidence rather than independent-family generalization.

## Performance evidence

- The schema-v2 CPU/GPU pair is correctness-only. It used zero warmups and one repetition per backend while the harness worktree was uncommitted, so both records are explicitly timing-ineligible.
- The one-repetition manifest-linked pilot remains pruning evidence only. Stage 4 adds repeated medians and IQRs, using five measurements per candidate at the two smallest sizes and three at the other sizes, but it does not provide confidence intervals or independent-machine replication.
- CPU1/4/8 pruning also uses one measured repetition at only the three smallest sizes. It justifies retaining the consistently faster CPU16 candidate for the frozen deadline-bounded protocol, but it is not a general CPU scaling study.
- Only one GCP heterogeneous node has been exercised: 16 physical Intel Xeon cores/32 logical CPUs and one NVIDIA L4. Results cannot imply multi-node, other-accelerator, leadership-system, or exascale behavior.
- Stage 4 kept CPU and GPU timing candidates sequential under the node lock and used warmups, seeded randomized candidate order, repeated trials, and contemporaneous preflight telemetry. Ambient VM variation and single-node execution remain limitations.

## Correctness evidence

- Correctness is strong cross-backend agreement on identical bytes, convergence, energy, iteration count, and density. It is not comparison against an independently certified exact Fe₄S₄ energy: upstream supplies only an approximate, non-asserted value.
- The pinned upstream prints one density vector with a missing closing bracket. The parser performs one narrowly defined repair and records `density_bracket_repaired=true`; any other malformed output remains a parsing failure.
- The Stage 2 and five-input Stage 3 validation manifests prove the exact checked artifacts and criteria. They do not retroactively make their zero-warmup source trials eligible for performance analysis.

## Harness and selector maturity

- The deterministic GPU guard was applied throughout the measured size range, and all candidates were admitted and completed. Because no candidate approached the cap and there were no OOMs or guard skips, near-cap estimate accuracy and infeasibility discrimination remain unvalidated.
- The selector, grouped splits, training-only threshold, shallow trees, regret analysis, and held-out evaluation are implemented. Evidence is still limited to five correlated size variants of one family; the primary test contains one instance, and the full tree does not outperform the size-only tree in sensitivity analysis.
- Hot selector overhead is measured, but the `929.11 us` object-cold diagnostic includes model-file read/parse with uncontrolled OS page-cache state and must not be described as storage-cache-cold latency.
- Only the documented AMD command-line parameters are exposed. Unsupported or silently ignored flags, including the previously considered `--init`, are deliberately excluded.
- Historical RIKEN `v1.3.0` executable/build/smoke evidence is preserved for provenance only and is not an active implementation or comparison baseline. If Phase B is approved, pinned RIKEN-repository N₂/H₂O files may be considered only as data inputs after license, hash, format-compatibility, and same-official-AMD-binary correctness gates; this does not promote the RIKEN solver.

## Authorship boundary

Code, raw evidence, internal analysis, reproducibility reports, and organizational checklists may be prepared in this repository. The abstract, 800-word submission summary, poster, poster source/copy, portal prose, and final student interpretation must be written by the student.
