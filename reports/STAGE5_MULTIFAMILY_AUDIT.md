# Stage 5 multifamily evaluation audit

Status date: 2026-08-01

This is an internal engineering and scientific evidence audit. It is not an
abstract, submission summary, poster, poster source, or student-authored
interpretation.

## Audit outcome

The sealed package at `results/processed/stage5_multifamily/` passes its
independent provenance, geometry, leakage, determinism, and semantic checks.
It evaluates the two retained official-AMD candidates—CPU16 and NVIDIA L4
OpenMP offload—on one heterogeneous node. No solver run, new timing trial, raw
record mutation, hyperparameter search, or held-out tuning occurred during
evaluation.

The balanced dataset contains exactly 90 timing-eligible measurements:
repetitions 0–2 for two candidates at five correlated determinant-prefix sizes
in each of three chemistry families. Those records become 30 candidate medians
and 15 family-qualified instances. Three leave-one-chemistry-family-out (LOFO)
folds each train on ten complete instances from two families and test five
complete instances from the third. Candidate records and repetitions never
cross a fold boundary, and the split manifest reports `leakage_check=PASS`.

The full tree, size-only tree, and training-only threshold were frozen before
real-data fitting. Both trees use `DecisionTreeRegressor(max_depth=3,
min_samples_leaf=2, random_state=1729)`. Family, molecule, basis, instance and
input identities, timings, resource peaks, and other post-execution values are
excluded from predictors. The full model uses only pre-execution size,
work-proxy, determinant-cache, GPU-guard, determinant-graph-density, backend,
and CPU-thread features. The size-only ablation uses configuration count and
backend only.

After the LOFO evaluation was sealed, the artifact writer was extended to fit
one full-feature deployment tree on all 15 balanced instances solely for
deployment selection and inference-overhead timing. It is stored separately
from the three fold models, is explicitly marked
`used_for_heldout_metrics=false`, and does not enter `evaluation.json`, policy
predictions, regret, accuracy, speedup, or any other held-out result.

## Hash-bound evidence

The evaluation configuration is
`configs/stage5_multifamily.yaml`, SHA-256
`5bcf87ce6cafe898412172c3f7a5bfd5299474719ae0940041f19b62f4d2cfa3`.
Its seven required source claims were rehashed before evaluation:

| Source | SHA-256 |
| --- | --- |
| `reports/stage4_protocol.json` | `29431c68e84cee75a280c5b5faf3d2a15f1eb2ec2c16f4f5ce37796ef5f307f6` |
| `reports/stage4_completion.json` | `7fefb110d29b0bfae2ece24a3506bd6fa53e6e81257f57779ce2067e9910ee36` |
| `results/processed/stage4_final.json` | `58c6b6bc2454de9237a102a3d3d6b3628d0bb98b0f0758cf0353d9edc64885aa` |
| `reports/stage4_fe4s4_family_registry.json` | `cfeb5f60e29d01068c68b9d348739fba4b4e204e5165edce899aff5dfa94395d` |
| `reports/phaseb_final_protocol.json` | `bf5b27d5213e02b08c5836e7a91da4702431d7c6ee9b01c58d76d660add73e98` |
| `reports/phaseb_final_completion.json` | `9a75df34696ee05e683e50ce4583eaefcfbbed4f8f8265b3836a892ce0c7326d` |
| `results/processed/phaseb_n2_h2o_grid_final.json` | `f7deacc86e923614fded5f8e6bdfa7206fe8339e3a4d035d6db7ee967212768d` |

The sealed outputs are:

| Artifact | SHA-256 |
| --- | --- |
| `source_manifest.json` | `2a51193041b0e4d5f365769a67e0cd0b9aee86d48bbe85739f16c928b8e63ec6` |
| `balanced_dataset.json` | `ba6a5506af54df7c5b1f4b888117d34c8ecb86d300d305c834c31fe02e15a846` |
| `split_manifest.json` | `54aad40f6f012bcc483c0072e5de2b9d91430698904fea875556484618bb5811` |
| `evaluation.json` | `c0f7e6cead38bd431c4da7907beb7df7408cae99989a743eaef4044f61420c50` |
| `models.json` | `f5114b0a8c2ff5bef52940ddd673757eabbab85b893849a8e9d475462b49c286` |
| `policy_predictions.csv` | `e29de16120ad611a13adde46fa5e21624880f04afc5d5621c83b249cb58629c4` |
| `policy_summary.json` | `4967162ff54c41fb8061f5b3024167573c485edecfefe80c2d0f563806100d56` |
| `policy_summary.csv` | `5f34333500332f3c28b181b3b333d7662f49a0246a984506ebafba1f640cd154` |
| `selector_ablation.csv` | `3baee7ba9a45485d9788350c6291054eacd86a1e6540de943b3198bcfd8cd968` |

The source manifest also binds the path, SHA-256, size, trial ID, and family of
each of the 90 selected raw records. Pilot, correctness, warmup, and measured
repetitions 3–4 are excluded from this balanced dataset.

## Held-out results

All six policies produced 15 valid out-of-family decisions with zero invalid
selection and zero failure. The upstream default is only an alias for fixed
GPU; it is not a seventh policy.

| Pooled policy | Correct | Geometric selected/oracle | Speedup vs fixed CPU16 | Speedup vs fixed GPU | Maximum normalized regret |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fixed CPU16 | 5/15 | `1.8750253246988415` | `1.0` | `0.5765138778218245` | `5.482571387657153` |
| Fixed GPU | 10/15 | `1.080978120956255` | `1.7345636219169327` | `1.0` | `0.3869591107344933` |
| Static training-only threshold | 13/15 | `1.0377461353348265` | `1.8068246759539786` | `1.0416595004783897` | `0.3841755352561985` |
| Size-only tree | 12/15 | `1.1717731863098702` | `1.6001606339906465` | `0.9225148122397769` | `5.482571387657153` |
| AutoSBD full tree | 13/15 | `1.0229922425736244` | `1.8328832288910508` | `1.0566826178825666` | `0.25943483534277495` |
| Measured feasible oracle | 15/15 | `1.0` | — | — | `0.0` |

Per held-out family, the full tree records Fe₄S₄ 4/5 with geometric
selected/oracle `1.0472132783479557`, N₂ 4/5 with
`1.0223082863870683`, and H₂O 5/5 with `1.0`. The static threshold records
4/5 and `1.0472132783479557`, 5/5 and `1.0`, and 4/5 and
`1.0671813668697498`, respectively. The size-only tree records 4/5 and
`1.0472132783479557`, 5/5 and `1.0`, and 3/5 and
`1.536368970070679`, respectively.

| Held-out family | Policy | Correct | Geometric selected/oracle | Speedup vs CPU16 | Speedup vs GPU |
| --- | --- | ---: | ---: | ---: | ---: |
| Fe₄S₄ | Fixed CPU16 | 1/5 | `2.0779687720600366` | `1.0` | `0.4955664118022451` |
| Fe₄S₄ | Fixed GPU | 4/5 | `1.0297715282069095` | `2.0178930132961637` | `1.0` |
| Fe₄S₄ | Threshold | 4/5 | `1.0472132783479557` | `1.9842842093619764` | `0.9833446056293694` |
| Fe₄S₄ | Size-only tree | 4/5 | `1.0472132783479557` | `1.9842842093619764` | `0.9833446056293694` |
| Fe₄S₄ | Full tree | 4/5 | `1.0472132783479557` | `1.9842842093619764` | `0.9833446056293694` |
| N₂ | Fixed CPU16 | 2/5 | `1.6849341677835585` | `1.0` | `0.6389633217620321` |
| N₂ | Fixed GPU | 3/5 | `1.0766111327973276` | `1.5650350590427602` | `1.0` |
| N₂ | Threshold | 5/5 | `1.0` | `1.6849341677835585` | `1.0766111327973276` |
| N₂ | Size-only tree | 5/5 | `1.0` | `1.6849341677835585` | `1.0766111327973276` |
| N₂ | Full tree | 4/5 | `1.0223082863870683` | `1.648166399724951` | `1.0531178775848238` |
| H₂O | Fixed CPU16 | 2/5 | `1.8827794941768619` | `1.0` | `0.6051339315127189` |
| H₂O | Fixed GPU | 3/5 | `1.1393337574827729` | `1.6525267348670922` | `1.0` |
| H₂O | Threshold | 4/5 | `1.0671813668697498` | `1.7642544675413703` | `1.067610242132188` |
| H₂O | Size-only tree | 3/5 | `1.536368970070679` | `1.2254735228675222` | `0.7415756108575656` |
| H₂O | Full tree | 5/5 | `1.0` | `1.8827794941768619` | `1.1393337574827729` |

The full tree's two exact misses are Fe₄S₄ at 3,025 configurations (CPU16
selected, GPU oracle; normalized regret `0.25943483534277495`) and N₂ at
10,000 (CPU16 selected, GPU oracle; regret `0.11663029153925956`). The
threshold misses Fe₄S₄ at 3,025 (CPU16 selected, GPU oracle; regret
`0.25943483534277495`) and H₂O at 3,025 (GPU selected, CPU16 oracle; regret
`0.3841755352561985`). The size-only tree additionally exposes why pooled
accuracy alone is insufficient: its H₂O full-size miss has normalized regret
`5.482571387657153`.

## Hardening and interpretation

The combined preproduction completion/evaluation suite passed 25 tests, and
the independent audit separately passed 13 focused checks and mutation probes.
The hardening covers exact source and raw claims, symlink/hash failures,
completion-view and family-registry bindings, deterministic changed-only
outputs, exact dataset geometry, predictor allowlists, held-out-source
exclusion from fitted models, split leakage, input-order determinism, and the
complete pooled/per-family policy metric set.

The supported conclusion is narrow: on these 15 correlated prefixes from
three chemistry families and these two candidates on one CPU/L4 node, the
frozen full tree has lower pooled selected/oracle runtime than the frozen
size-only ablation and modestly improves on the training-only threshold. This
is held-out-family evidence, not universal generalization and not a broad
autotuning result. It does not establish behavior on independent machines,
other accelerators, unseen solver parameters, unrelated chemistry families,
or multi-node/exascale systems.

Important limitations remain: only three families and five correlated prefixes
per family are available; there are no confidence intervals, independent-node
replication, or comprehensive autotuner; Fe₄S₄'s basis is correctly recorded as
unknown; and the selector considers only the already-pruned CPU16 and L4 GPU
candidates. `shuffle`, `bit_length`, cache/decomposition variants, and other
axes require separately correctness-gated, bounded timing protocols.
