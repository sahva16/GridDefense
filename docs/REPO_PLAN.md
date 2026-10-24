# GridDefense repository plan

## Stage 1 — now
- Keep notebook unchanged and visible in `notebooks/`.
- Add README, initial dependency inventory, `.gitignore`, and folders.
- Upload this structure **to the existing GitHub GridDefense repository**, not a new repository.
- Do not claim the notebook has been successfully modularised.

## Stage 2 — later, one component at a time
- Review cell dependencies and identify notebook configuration/paths.
- Extract config, grid and snapshot generation, physics features, AE, RF, physics validator, fusion, localiser, evaluation.
- Add simple tests for feature dimensions, fusion threshold, and alarm-log consistency.
- Compare extracted code against the original notebook before switching entry points.

## Stage 3 — reproducibility and documentation
- Test installation/run instructions in a fresh environment.
- Save selected validated figures/metrics and a small example output.
- Add diagrams and dashboard source when available.
- Document dataset licensing, versions, and acquisition. Do not commit the large fdia-graph HDF5 dataset.

## Integration instructions
1. Unzip this package locally.
2. In your existing repository checkout, copy the *contents* of this folder into the repository root.
3. Compare the notebook against the one already on GitHub and decide whether to retain both or move the existing notebook with git history. Avoid deleting the previous notebook before confirming.
4. Commit/push in GitHub Desktop, e.g. `Organise GridDefense Stage 1 repository`.
