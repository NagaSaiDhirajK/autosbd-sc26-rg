# AutoSBD figure redesign v2

This is a drop-in replacement for `src/autosbd/submission_figures.py`.
It preserves the existing tracked-data loaders, validators, CSV exports, SHA-256 manifest, and figure names.
It changes only presentation and derived arithmetic that can be computed from the existing policy summary.

## Main changes

- Removes in-image figure titles from all ten figures.
- Uses direct labels and shorter text rather than large legends and footers.
- Figure 3 adds an explicitly conditional portfolio-impact card: hours recovered per 1,000 fixed-GPU hours under the same measured workload mix and hardware.
- Figure 4 combines held-out accuracy and overhead into one compact matrix.
- Figure 5 includes the measured oracle as a direct reference row and marks misses with borders instead of large X marks.
- Figure 6 displays only nonzero-regret events with large lollipops and a broken axis for the 548% outlier.
- Figure 7 manually reconstructs the serialized deployment tree and converts log thresholds back to readable units when possible.
- Figure 8 compares selector latency directly with the shortest measured SBD runtime using three bars.
- Figure 9 uses linear y-axes for measured memory and guard estimates, and a logarithmic y-axis only for cap headroom.
- Figure 10 replaces scattered error points with orders-of-magnitude safety margin below the 1e-10 tolerance.

## Install and render

From the repository root:

```bash
cp autosbd_figures_v2_patch/src/autosbd/submission_figures.py src/autosbd/submission_figures.py
PYTHONPATH=src .venv/bin/python scripts/make_submission_figures.py
```

Run the existing test suite afterward:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

The preview montage in this package uses synthetic layout fixtures only. It demonstrates layout, not scientific values.
