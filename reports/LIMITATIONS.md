# Current limitations and claim boundaries

Status date: 2026-08-01

This internal report records what the completed Stage 2 evidence does not establish. It is not student-authored submission material.

## Workload coverage

- The pinned official AMD artifact tree currently supplies one authentic chemistry dataset for the primary path: Fe₄S₄. It does not provide the N₂, H₂O, or other independent families referenced by some upstream scripts.
- Determinant-prefix sizes derived from Fe₄S₄ can locate a size crossover, but they change the selected subspace and energy and are not independent chemical families. Evaluation must label them as size-held-out, not family-held-out.
- With only one family, leave-one-family-out generalization is impossible. Any later model result must disclose this and group all repetitions of a derived instance/configuration together to prevent leakage.

## Performance evidence

- The schema-v2 CPU/GPU pair is correctness-only. It used zero warmups and one repetition per backend while the harness worktree was uncommitted, so both records are explicitly timing-ineligible.
- The one-repetition manifest-linked pilot brackets an observed CPU16/GPU winner flip, but it has no repetition distribution, median/IQR, confidence interval, or exact threshold. Its ratios are pilot diagnostics, not final speedup claims; near-crossover replication and the final protocol have not run yet.
- Only one GCP heterogeneous node has been exercised: 16 physical Intel Xeon cores/32 logical CPUs and one NVIDIA L4. Results cannot imply multi-node, other-accelerator, leadership-system, or exascale behavior.
- Final CPU and GPU timing candidates must remain sequential. The node lock prevents overlap, but ambient VM variation still requires warmups, randomized order, repeated trials, and contemporaneous preflight telemetry.

## Correctness evidence

- Correctness is strong cross-backend agreement on identical bytes, convergence, energy, iteration count, and density. It is not comparison against an independently certified exact Fe₄S₄ energy: upstream supplies only an approximate, non-asserted value.
- The pinned upstream prints one density vector with a missing closing bracket. The parser performs one narrowly defined repair and records `density_bracket_repaired=true`; any other malformed output remains a parsing failure.
- The Stage 2 and five-input Stage 3 validation manifests prove the exact checked artifacts and criteria. They do not retroactively make their zero-warmup source trials eligible for performance analysis.

## Harness and selector maturity

- The deterministic GPU guard is implemented, but its workload memory estimates have not yet been calibrated across the planned size range. Conservative skips are preferable to OOM until pilot evidence exists.
- Stage 2 records features and candidate settings, but no runtime selector, training split, learned threshold, decision tree, regret analysis, or held-out evaluation has been completed.
- Only the documented AMD command-line parameters are exposed. Unsupported or silently ignored flags, including the previously considered `--init`, are deliberately excluded.
- Historical RIKEN `v1.3.0` build and smoke evidence is preserved for provenance only. It is not an active alternative implementation, training source, or comparison baseline unless the user explicitly changes scope.

## Authorship boundary

Code, raw evidence, internal analysis, reproducibility reports, and organizational checklists may be prepared in this repository. The abstract, 800-word submission summary, poster, poster source/copy, portal prose, and final student interpretation must be written by the student.
