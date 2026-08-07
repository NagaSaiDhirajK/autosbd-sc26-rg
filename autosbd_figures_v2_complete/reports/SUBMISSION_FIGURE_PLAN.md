# AutoSBD submission figure plan

This figure suite is designed for the SC26 ACM Student Research Competition submission and poster. It reads only tracked, sealed artifacts. It does not rerun SBD, refit a model, interpolate a crossover, or add synthetic scientific data.

## Figure priority

### Main poster / submission figures

1. **Pipeline architecture** — establishes the original contribution: pre-execution features, feasibility filtering, runtime selection, and execution through the official AMD-HPC CPU/GPU binaries.
2. **Runtime scaling by family** — the essential CPU–GPU crossover evidence. It shows repeated medians and IQR for Fe4S4, N2, and H2O and labels only observed winner-flip brackets.
3. **Pooled policy performance** — the headline held-out result. It compares geometric runtime overhead and exact selection accuracy for fixed CPU16, fixed GPU, the training-only threshold, the size-only ablation, AutoSBD, and the measured oracle.
4. **Held-out-family generalization** — shows whether the learned policies transfer when an entire chemistry family is excluded from training.
5. **Instance decision map** — makes the 15 held-out decisions inspectable and marks each wrong backend selection.

### Strong supporting figures

6. **Regret distribution** — demonstrates why selection accuracy alone is insufficient and exposes high-cost mistakes.
7. **Deployment tree** — explains the final interpretable selector. The caption explicitly states that this all-data deployment tree was not used for held-out metrics.

### Supplementary / methods figures

8. **Inference overhead** — shows hot and object-cold selection latency; the object-cold result is not described as storage-cache-cold.
9. **GPU memory headroom** — shows cross-family measured peak memory, conservative guard, and admission cap. It explicitly states that the memory boundary was not reached.
10. **Energy error margin** — expresses measured energy error relative to the registered 1e-10 tolerance. It is more legible than the previous identity-line energy scatter.

## Figures intentionally excluded from the main poster

- **Run-eligibility bar chart:** the prior plot combines counts with different scopes and is not a valid flow diagram. The evidence remains in reports and manifests.
- **CPU-thread pilot:** useful for candidate pruning, but it is single-repetition pilot evidence and distracts from the held-out selector result.
- **Raw measured-versus-reference energy scatter:** the three chemistry energy scales make the points visually collapse onto the identity line. The tolerance-margin plot is more informative.
- **Telemetry timelines and Davidson convergence histories:** the tracked data do not contain the required time series. These figures must not be fabricated.
- **bit_length, shuffle, cache, and decomposition sensitivity:** these parameters were not varied in the sealed evaluation.

## Claim boundaries encoded by the generator

- Three chemistry families; five correlated determinant-prefix instances per family.
- Two retained candidates only: CPU16 and NVIDIA L4.
- Leave-one-chemistry-family-out held-out evaluation.
- Runtime bands are IQR, not confidence intervals.
- No fitted or interpolated crossover.
- The deployment tree is excluded from held-out metrics.
- The GPU memory boundary was not reached.

## Reproduction

From the repository root:

```bash
PYTHONPATH=src .venv/bin/python scripts/make_submission_figures.py
```

Outputs:

- vector/raster figures: `figures/submission/`
- normalized companion tables and SHA-256 manifest: `results/processed/submission_figure_data/`

For the poster, prefer SVG or PDF. PNG is included for rapid preview and portal compatibility.
