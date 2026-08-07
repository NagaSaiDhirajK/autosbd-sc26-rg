SELF-CONTAINED AUTOSBD FIGURE PATCH

1. Upload this ZIP into the repository root in GitHub Codespaces.
2. From the repository root, run:

   unzip -o autosbd_figures_v2_complete.zip
   bash autosbd_figures_v2_complete/install_and_generate.sh

The installer copies the figure module, generator, focused tests, and figure plan.
It uses the existing .venv when present. Otherwise it uses python3 and creates a
.venv only when required dependencies are unavailable.
