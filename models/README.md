# Trained models

The trained models are **not stored in git**: the Random Forest files are large, and GitHub rejects
files over 100 MB.

**Option 1 — train them yourself** (about 5 minutes on a 2-core CPU):

```bash
python scripts/train.py        # writes models/trained/
```

**Option 2 — use the notebook's models.** The notebook saves its models to Google Drive
(`MyDrive/GridDefense/final_notebook`): `autoencoder.h5`, `scaler_ae.pkl`, `ae_threshold.json`,
`rf_final.pkl`, `rf_loc_final_172feat.pkl`, `loc_thresholds_and_config.pkl`, `physics_params.npz` and
`fusion_config.json`. If they are attached to a GitHub Release of this repository, download them from
the Releases page. Their MD5 fingerprints are listed in `results/MANIFEST.json`.
