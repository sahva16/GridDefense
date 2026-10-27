"""Weighted decision fusion (notebook Section 8).

    fusion = w_AE × AE score + w_RF × RF score + w_Physics × physics score
    alarm when fusion ≥ threshold

Weights and threshold are chosen on VALIDATION data by the best F1, over the same
grid as the notebook. The final system uses 0.30 / 0.40 / 0.30 and 0.40.
"""
import numpy as np

from . import config as C


def _f1(pred, y):
    tp = ((pred == 1) & (y == 1)).sum(); fp = ((pred == 1) & (y == 0)).sum(); fn = ((pred == 0) & (y == 1)).sum()
    prec = tp / (tp + fp) if tp + fp > 0 else 0
    rec = tp / (tp + fn) if tp + fn > 0 else 0
    return 2 * prec * rec / (prec + rec) if prec + rec > 0 else 0


def select_fusion(ae_s, rf_s, ph_s, y_val):
    """Grid search on validation data (same grid and tie rule as the notebook)."""
    best_f1, best_w, best_thr = 0, (0.3, 0.5, 0.2), 0.5
    for w_rf in C.FUSION_W_RF:
        for w_ae in C.FUSION_W_AE:
            w_ph = 1.0 - w_rf - w_ae
            if w_ph < C.FUSION_W_PH_RANGE[0] or w_ph > C.FUSION_W_PH_RANGE[1]:
                continue
            fused = w_ae * ae_s + w_rf * rf_s + w_ph * ph_s
            for thr in np.arange(0.2, 0.8, 0.05):
                f1 = _f1((fused >= thr).astype(int), y_val)
                if f1 > best_f1:
                    best_f1, best_w, best_thr = f1, (w_ae, w_rf, w_ph), thr
    return {"w_ae": float(best_w[0]), "w_rf": float(best_w[1]), "w_phys": float(best_w[2]),
            "threshold": float(best_thr), "val_f1": float(best_f1)}


def fuse(cfg, ae_s, rf_s, ph_s):
    return cfg["w_ae"] * ae_s + cfg["w_rf"] * rf_s + cfg["w_phys"] * ph_s
