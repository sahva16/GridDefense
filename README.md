# GridDefense

**False Data Injection Attack Detection and Bus Localisation in Smart Grids Using AI and Physics Checks**

GridDefense is a research prototype for the simulated IEEE 14-bus system. It scores individual measurement snapshots using an autoencoder (AE), a Random Forest (RF), and bus-specific physics checks. A weighted fusion score triggers alarms; a separate topology-aware localiser identifies suspected attacked buses, and the notebook generates structured alarm reports.

> **Scope:** Simulated snapshots and research evaluation. Not a live grid monitoring, attack mitigation, or grid-control system. The dashboard is a separate work-in-progress and is not yet verified as integrated.

## Current working implementation

- **Source of truth:** [`notebooks/GridDefense_Final.ipynb`](notebooks/GridDefense_Final.ipynb) — original 20-section notebook, preserved without refactoring.
- Input: voltage magnitude and angle plus active and reactive loads at 14 buses.
- Main simulated attacks: additive, scaling, and coordinated FDIA.
- Fusion rule: `0.30 × AE + 0.40 × RF + 0.30 × physics`; alarm threshold `0.40`.
- The RF assigns an attack class for each snapshot; localisation runs when an alarm is raised.

## Reported evaluation (independent synthetic test set)

| Metric | Reported result |
| --- | ---: |
| Attack detection | 99.32% |
| False-alarm rate | 0.30% |
| Exact attacked-bus set localisation | 96.35% |

These results apply to the project's independent simulated IEEE 14-bus test set and **must not** be interpreted as performance guarantees on live grids. Notebook sections also evaluate weak and stealthy attacks and a separate `fdia-graph` benchmark with model retraining; outcomes differ under those conditions.

## Run the notebook

1. Open the notebook in **Google Colab**.
2. Run notebook cells in order, starting from Section 1. Its installation/setup cells may install additional dependencies.
3. Review generated metrics and evaluation output inside the notebook.
4. For the external benchmark, follow the notebook's `fdia-graph` section and its data download instructions.

**Environment note:** `requirements.txt` is an initial dependency inventory, not an exact lockfile. A clean fresh-runtime end-to-end run has not been independently verified for this repository package.

## Repository roadmap

- `notebooks/` — verified reference notebook.
- `src/` — future extracted and tested Python modules (`grid.py`, `data_generation.py`, `physics_features.py`, `autoencoder.py`, `random_forest.py`, `physics_layer.py`, `fusion.py`, `localiser.py`, `evaluation.py`). **Not implemented in this Stage 1 package.**
- `experiments/` — future reproducible evaluation scripts, currently represented in the notebook.
- `dashboard/` — put actual dashboard HTML/CSS/JS here when ready; do not mistake example values for connected results.
- `results/` — selected, lightweight plots and metrics after checking against the notebook.
- `docs/` — technical architecture, UML, and project documentation.

See [`docs/REPO_PLAN.md`](docs/REPO_PLAN.md) for next steps.

## Authors and acknowledgments

Graduation project team (five members). Add member names and supervisor details before public release.
