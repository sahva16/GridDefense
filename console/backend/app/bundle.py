"""
Loading the exported model bundle, and proving it reproduces the notebook.

Provenance status shown in the dashboard (one of):
  verified     — bundle exported from the notebook, files unchanged since export (SHA-256 match),
                 AND the app reproduced the notebook's decisions on ALL test snapshots.
  development  — bundle made by a developer from the repo package; NOT the notebook's models.
  unverified   — anything else: no manifest, a fingerprint mismatch, or the comparison failed.
"Verified" is never shown without the full comparison actually passing.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from .pipeline import N_BUSES

# Tolerance: alarm_log.csv stores scores rounded to 3 decimals, so a true match differs by ≤ 0.0005.
ROUND_TOL = 0.0005 + 1e-9


class BundleError(SystemExit):
    pass


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_bundle(folder: Path) -> tuple[dict, dict, pd.DataFrame, dict]:
    """Returns (bundle, manifest, test_df, integrity). Refuses to start without a real bundle."""
    model, test = folder / "griddefense_model.joblib", folder / "test_snapshots.csv.gz"
    if not model.exists() or not test.exists():
        raise BundleError(
            f"[GridDefense] No model bundle in {folder}.\n"
            "  Run notebook/export_bundle_cell.py in Colab, download MyDrive/GridDefense/app_bundle,\n"
            "  and copy its contents into backend/bundle (or set GRIDDEFENSE_BUNDLE=/path/to/app_bundle).\n"
            "  The app does not fall back to any other models.")
    man_p = folder / "bundle_manifest.json"
    manifest = json.loads(man_p.read_text()) if man_p.exists() else {}
    integrity = dict(manifest_present=bool(manifest))
    if manifest:
        integrity["model_sha256_ok"] = _sha256(model) == manifest.get("model_sha256")
        integrity["test_sha256_ok"] = _sha256(test) == manifest.get("test_snapshots_sha256")
    bundle = joblib.load(model)
    df = pd.read_csv(test, keep_default_na=False)
    needed = {"nb_alarm", "nb_fusion", "nb_ae", "nb_rf", "nb_phys", "nb_named_buses"}
    if not needed.issubset(df.columns):
        raise BundleError(f"[GridDefense] {test.name} has no notebook reference columns {sorted(needed - set(df.columns))}. "
                          "This is an old-format bundle; re-export it with notebook/export_bundle_cell.py.")
    return bundle, manifest, df, integrity


def _named_matrix(col) -> np.ndarray:
    m = np.zeros((len(col), N_BUSES), dtype=bool)
    for i, v in enumerate(col.astype(str)):
        for b in v.split():
            m[i, int(b) - 1] = True
    return m


def verify_against_notebook(pipe, test: pd.DataFrame) -> dict:
    """Score EVERY test snapshot and compare with the notebook's own Section 10 output (alarm_log.csv)."""
    t0 = datetime.now(timezone.utc)
    s = pipe.score(test)
    nb_loc = _named_matrix(test["nb_named_buses"])
    rf_type = np.array([{0: "Normal", 1: "Additive", 2: "Scaling", 3: "Coordinated"}[int(c)] for c in s["rf_cls"]])
    checks = {
        "alarm": (s["alarm"].astype(int) == test["nb_alarm"].values.astype(int)),
        "named_buses": (s["loc"] == nb_loc).all(axis=1),
        "fusion_score": np.abs(s["fus"] - test["nb_fusion"].values.astype(float)) <= ROUND_TOL,
        "ae_score": np.abs(s["ae"] - test["nb_ae"].values.astype(float)) <= ROUND_TOL,
        "rf_score": np.abs(s["rf"] - test["nb_rf"].values.astype(float)) <= ROUND_TOL,
        "physics_score": np.abs(s["ph"] - test["nb_phys"].values.astype(float)) <= ROUND_TOL,
    }
    if "nb_rf_type" in test.columns:
        checks["attack_type"] = rf_type == test["nb_rf_type"].values.astype(str)
    n = len(test)
    rows = {k: dict(match=int(v.sum()), total=n) for k, v in checks.items()}
    first_bad = {k: [int(i) for i in np.where(~v)[0][:5]] for k, v in checks.items() if not v.all()}
    return dict(
        snapshots=n,
        checks=rows,
        mismatches=first_bad,
        fusion_max_abs_diff=float(np.abs(s["fus"] - test["nb_fusion"].values.astype(float)).max()),
        app_alarms=int(s["alarm"].sum()), notebook_alarms=int(test["nb_alarm"].sum()),
        passed=bool(all(v.all() for v in checks.values())),
        tolerance=f"scores within {ROUND_TOL - 1e-9:.4f} (alarm_log stores 3 decimals); alarms, named buses and type exact",
        checked_at=t0.isoformat(timespec="seconds"),
        seconds=round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
    )


def provenance(manifest: dict, integrity: dict, check: dict, bundle: dict) -> dict:
    reasons = []
    kind = manifest.get("provenance", "notebook") if manifest else None
    if not manifest:
        reasons.append("no bundle_manifest.json (bundle not made by the current export cell)")
    else:
        if not integrity.get("model_sha256_ok"):
            reasons.append("model file fingerprint does not match the manifest (file changed after export)")
        if not integrity.get("test_sha256_ok"):
            reasons.append("test-snapshot file fingerprint does not match the manifest")
    if not check["passed"]:
        reasons.append("the app did NOT reproduce every notebook decision (see mismatches)")
    if bundle.get("sklearn_version") and bundle["sklearn_version"] != sklearn.__version__:
        reasons.append(f"scikit-learn {sklearn.__version__} here vs {bundle['sklearn_version']} in Colab")
    if reasons:
        status = "unverified"
    elif kind == "notebook":
        status = "verified"
    else:
        status = "development"
    sha = manifest.get("model_sha256", "")
    return dict(status=status, kind=kind, reasons=reasons,
                bundle_id=sha[:12] if sha else "unknown",
                label={"verified": "Notebook models · verified",
                       "development": "DEVELOPMENT models · not the notebook's",
                       "unverified": "Models NOT verified"}[status])
