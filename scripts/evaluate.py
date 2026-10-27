"""Evaluate a trained GridDefense on the independent test set (notebook Section 10).

    python scripts/evaluate.py                  # reads models/trained and data/test_dataset_seed20261014.csv
Writes results/package_run/summary.json and alarm_log.csv, and prints the main table.
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, accuracy_score, f1_score

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
from griddefense import GridDefense, config as C                # noqa: E402
from griddefense.data import BUS_LABEL_COLS                     # noqa: E402


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h) * 100, (c + h) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=os.path.join(HERE, "..", "models", "trained"))
    ap.add_argument("--data", default=os.path.join(HERE, "..", "data", f"test_dataset_seed{C.TEST_SEED}.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "results", "package_run"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    gd = GridDefense.load(args.models)
    T = pd.read_csv(args.data)
    y, t = T["Label"].astype(int).values, T["Attack_Type"].astype(int).values
    o = gd.predict(T)

    summary = {}
    print(f"Independent test set: {len(T)} snapshots ({(y == 0).sum()} normal, {(y == 1).sum()} attacked)\n")
    print(f"  {'Detector':<18}{'Detection % [95% CI]':>26}{'False alarms % [95% CI]':>28}{'AUC':>8}")
    for name, flag, score in [("AE alone", o["ae_flag"], o["ae_score"]), ("RF alone", o["rf_flag"], o["rf_score"]),
                              ("Physics alone", o["phys_flag"], o["phys_score"]), ("2-of-3 voting", o["vote_2of3"], None),
                              ("Weighted fusion", o["alarm"], o["fusion_score"])]:
        tp, fn = int(flag[y == 1].sum()), int((flag[y == 1] == 0).sum())
        fp, tn = int(flag[y == 0].sum()), int((flag[y == 0] == 0).sum())
        det, fa = tp / (tp + fn) * 100, fp / (fp + tn) * 100
        auc = roc_auc_score(y, score) if score is not None else None
        summary[name] = dict(detection=det, detection_ci=wilson(tp, tp + fn), false_alarm=fa,
                             false_alarm_ci=wilson(fp, fp + tn), auc=auc, TN_FP_FN_TP=[tn, fp, fn, tp])
        dc, fc = summary[name]["detection_ci"], summary[name]["false_alarm_ci"]
        print(f"  {name:<18}{det:>8.2f} [{dc[0]:5.2f},{dc[1]:6.2f}]{fa:>12.2f} [{fc[0]:5.2f},{fc[1]:6.2f}]"
              f"{(f'{auc:.4f}' if auc is not None else '—'):>10}")

    acc, mf1 = accuracy_score(t, o["rf_class"]) * 100, f1_score(t, o["rf_class"], average="macro")
    summary["RF 4-class"] = dict(accuracy=acc, macro_f1=mf1)
    print(f"\n  RF attack type: accuracy {acc:.2f}%, macro F1 {mf1:.4f}")

    bus = T[BUS_LABEL_COLS].values.astype(int); yp = o["buses"]; atk, nor = y == 1, y == 0; Cc = np.arange(1, 14)
    e2e = yp.copy(); e2e[(y == 1) & (o["alarm"] == 0)] = 0
    loc = dict(exact_match=float(np.mean(np.all(yp[atk][:, Cc] == bus[atk][:, Cc], axis=1)) * 100),
               micro_f1=float(f1_score(bus[atk][:, Cc], yp[atk][:, Cc], average="micro", zero_division=0) * 100),
               false_localisation=float(np.mean(np.any(yp[nor] == 1, axis=1)) * 100),
               end_to_end_exact=float(np.mean(np.all(e2e[atk][:, Cc] == bus[atk][:, Cc], axis=1)) * 100))
    summary["Localisation"] = loc
    print(f"  Localisation: exact {loc['exact_match']:.2f}% | micro F1 {loc['micro_f1']:.2f}% | "
          f"false localisation {loc['false_localisation']:.2f}% | end-to-end exact {loc['end_to_end_exact']:.2f}%")
    summary["settings"] = {"fusion": gd.fusion, "ae_seed": int(gd.ae.seed), "ae_threshold": gd.ae.threshold,
                           "physics_z": gd.physics.z, "localiser_threshold": gd.loc.threshold}

    with open(os.path.join(args.out, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2, default=float)
    alarms = np.where(o["alarm"] == 1)[0]
    pd.DataFrame({"snapshot": np.arange(len(T)), "alarm": o["alarm"], "fusion_score": o["fusion_score"].round(3),
                  "ae_score": o["ae_score"].round(3), "rf_score": o["rf_score"].round(3),
                  "physics_score": o["phys_score"].round(3),
                  "rf_type": [C.ATTACK_TYPES[int(c)] for c in o["rf_class"]],
                  "named_buses": [" ".join(str(int(b) + 1) for b in np.where(r)[0]) for r in yp],
                  "true_type": [C.ATTACK_TYPES[int(v)] for v in t]}).to_csv(os.path.join(args.out, "alarm_log.csv"), index=False)
    true_alarms = np.where((o["alarm"] == 1) & (y == 1))[0]
    print(f"\n{len(alarms)} alarms ({len(true_alarms)} on attacked snapshots). Example report (snapshot 6888, as in the notebook):\n")
    ex = 6888 if len(T) > 6888 else int(true_alarms[0])
    print(gd.report(o, ex))
    print(f"  [ground truth: {C.ATTACK_TYPES[int(t[ex])]}, buses {[int(b) + 1 for b in np.where(bus[ex])[0]]}]")
    print(f"\n✓ Saved summary.json and alarm_log.csv to {args.out}")


if __name__ == "__main__":
    main()
