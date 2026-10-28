# Results

Result tables (CSV) and figures (PNG) saved by the final run of `notebook/GridDefense_Final.ipynb`
(Google Colab). Each file is written by the notebook section shown below.

| Notebook section | Files |
|---|---|
| 5 Autoencoder | `ae_detection_results.png` |
| 8 Fusion (internal test split) | `devtest_evaluation.csv`, `devtest_evaluation_with_loc.csv` |
| 9 Feature importance | `fi_rf_permutation.csv`, `fi_rf_families.csv`, `fi_ae_features.csv` |
| 10 Independent test set | `final_results_seed20261014.csv`, `final_summary_seed20261014.json`, `alarm_log.csv`, `localisation_per_bus.csv`, `localisation_*.png` |
| 11 Unseen attack type | `unseen_attack_type.csv` |
| 12 Attack size | `attack_size_sensitivity.csv`, `attack_size_sensitivity.png` |
| 13 Physics ablation and repeat datasets | `physics_ablation*.csv`, `repeatability_*.csv` |
| 14 Stealthy attacks | `stealthy_attack_stress_test.csv` |
| 15 Fixes for unseen attacks | `generalisation_*.csv` |
| 16 Classical bad-data test | `classical_bad_data_baseline.csv` |
| 16b GPS spoofing | `gps_spoofing_*.csv` |
| 16c GridDefense + bad-data test | `griddefense_plus_classical.csv` |
| 17b External benchmark, partial physics | `external_partial_physics.csv` |
| 18 Model comparison | `model_comparison*.csv`, `small_attacks_*.csv`, `fusion_rf_vs_xgboost_*.csv` |
| 19 Report figures | `fig_roc_independent_test.png`, `fig_rf_confusion_matrix.png`, `fig_fusion_score_distribution.png` |

`MANIFEST.json` (notebook Section 20) lists the MD5 fingerprint of every file in the notebook's output folder and the
library versions. Every result file here matches its fingerprint. The manifest also lists the saved models (see
`models/README.md`) and a few leftover files from earlier development runs in the same Drive folder
(`FINAL_*_fresh_seed2026.*`, `devsplit_evaluation.csv`, `final_evaluation_with_loc.csv`,
`repeatability_generator_check.csv`, `griddefense_dataset_*.csv`, `fresh_test_seed2026.csv`); the final notebook no
longer writes these, so they are not included.

Results produced by the package scripts (`scripts/evaluate.py`) go to `results/package_run/`, which is not committed.
