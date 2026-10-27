"""GridDefense end to end: train on the development data, score new snapshots, write alarm reports.

    detect   → AE (unusual?)  +  RF (known attack?)  +  physics layer (obeys power flow?)
    decide   → weighted fusion  0.30·AE + 0.40·RF + 0.30·Physics ≥ 0.40
    explain  → RF attack type, localiser buses, physics checks that fired at which bus
"""
import json
import os

import joblib
import numpy as np

from . import config as C
from .data import split_indices, BUS_LABEL_COLS
from .features import AE_FEATURES, RF_FEATURES
from .fusion import select_fusion, fuse
from .models import AutoencoderDetector, Localiser, train_rf
from .physics import PhysicsValidator, CHECK_NAMES


class GridDefense:
    # ── training ────────────────────────────────────────────────────
    def fit(self, df_dev, verbose=True):
        """df_dev: development data WITH physics features (normal + attacked, seed 42)."""
        say = print if verbose else (lambda *a, **k: None)
        tr, va, te = split_indices(df_dev)
        self.split = {"train": tr, "val": va, "internal_test": te}
        D_tr, D_va = df_dev.iloc[tr], df_dev.iloc[va]
        y_va = D_va["Label"].astype(int).values

        say("Autoencoder (normal training snapshots only)...")
        self.ae = AutoencoderDetector().fit(D_tr[D_tr.Label == 0][AE_FEATURES].to_numpy(),
                                            D_va[D_va.Label == 0][AE_FEATURES].to_numpy(), verbose=verbose)
        say(f"  seed {self.ae.seed}, threshold {self.ae.threshold:.6f}")

        say("Random Forest (attack type, 104 features)...")
        self.rf = train_rf(D_tr[RF_FEATURES].values, D_tr["Attack_Type"].astype(int).values)

        say("Physics layer (reference statistics from training normals, Z on validation normals)...")
        self.physics = PhysicsValidator().fit(D_tr[D_tr.Label == 0].reset_index(drop=True),
                                              D_va[D_va.Label == 0].reset_index(drop=True))
        say(f"  Z = {self.physics.z}, ≥{self.physics.score_votes} checks at one bus")

        say("Localiser (172 features, all training snapshots)...")
        self.loc = Localiser().fit(D_tr[RF_FEATURES].values, D_tr[BUS_LABEL_COLS].values.astype(int),
                                   D_va[RF_FEATURES].values, D_va[BUS_LABEL_COLS].values.astype(int),
                                   D_va["Attack_Type"].astype(int).values)
        say(f"  threshold {self.loc.threshold:.2f}")

        say("Fusion weights and threshold (validation, best F1)...")
        v_err = self.ae.error(D_va[AE_FEATURES].values)
        self.ae.set_score_bounds(v_err, y_va == 0)
        v_rf = 1 - self.rf.predict_proba(D_va[RF_FEATURES].values)[:, 0]
        v_ph = self.physics.score(D_va.reset_index(drop=True))["score"]
        self.fusion = select_fusion(self.ae.score(v_err), v_rf, v_ph, y_va)
        say(f"  {self.fusion}")
        return self

    # ── scoring ─────────────────────────────────────────────────────
    def predict(self, df):
        """Score snapshots (DataFrame with physics features). Returns a dict of arrays."""
        df = df.reset_index(drop=True)
        err = self.ae.error(df[AE_FEATURES].values)
        X = df[RF_FEATURES].values
        proba = self.rf.predict_proba(X)
        ph = self.physics.score(df)
        out = {"ae_error": err, "ae_flag": (err > self.ae.threshold).astype(int), "ae_score": self.ae.score(err),
               "rf_class": proba.argmax(axis=1), "rf_score": 1 - proba[:, 0],
               "phys_votes": ph["votes"], "phys_flag": ph["flag"], "phys_score": ph["score"],
               "phys_check_flags": ph["check_flags"]}
        out["rf_class"] = self.rf.classes_[out["rf_class"]]
        out["rf_flag"] = (out["rf_class"] != 0).astype(int)
        out["fusion_score"] = fuse(self.fusion, out["ae_score"], out["rf_score"], out["phys_score"])
        out["alarm"] = (out["fusion_score"] >= self.fusion["threshold"]).astype(int)
        out["vote_2of3"] = ((out["ae_flag"] + out["rf_flag"] + out["phys_flag"]) >= 2).astype(int)
        out["buses"] = self.loc.predict(X)
        return out

    def report(self, out, i):
        """Readable alarm report for snapshot i (same content as the notebook's alarm report)."""
        f = self.fusion
        if out["alarm"][i] == 0:
            return f"Snapshot {i}: no alarm (fusion score {out['fusion_score'][i]:.2f} < threshold {f['threshold']:.2f})"
        named = [int(b) + 1 for b in np.where(out["buses"][i])[0]]
        reasons = []
        for b in np.where(out["phys_votes"][i] >= self.physics.score_votes)[0]:
            fired = [n for n, fl in out["phys_check_flags"].items() if fl[i, b]]
            reasons.append(f"Bus {b + 1}: {' + '.join(fired)}")
        return "\n".join([
            f"ALARM — snapshot {i}",
            f"  Fusion score {out['fusion_score'][i]:.2f} (threshold {f['threshold']:.2f}) = "
            f"{f['w_ae']:.2f}×AE {out['ae_score'][i]:.2f} + {f['w_rf']:.2f}×RF {out['rf_score'][i]:.2f} + "
            f"{f['w_phys']:.2f}×Physics {out['phys_score'][i]:.2f}",
            f"  Attack type (RF)     : {C.ATTACK_TYPES[int(out['rf_class'][i])]}",
            f"  Attacked buses       : {named if named else 'none named'}",
            f"  Physics checks fired : {'; '.join(reasons) if reasons else 'none (alarm came from AE/RF)'}"])

    # ── saving ──────────────────────────────────────────────────────
    def save(self, folder):
        os.makedirs(folder, exist_ok=True)
        self.ae.model.save(os.path.join(folder, "autoencoder.keras"))
        model, self.ae.model = self.ae.model, None
        try:
            joblib.dump({"ae": self.ae, "rf": self.rf, "physics": self.physics, "loc": self.loc,
                         "fusion": self.fusion}, os.path.join(folder, "griddefense.joblib"))
        finally:
            self.ae.model = model
        with open(os.path.join(folder, "settings.json"), "w") as fh:
            json.dump({"fusion": self.fusion, "ae_seed": int(self.ae.seed), "ae_threshold": self.ae.threshold,
                       "physics_z": self.physics.z, "physics_votes": self.physics.score_votes,
                       "physics_checks": CHECK_NAMES, "localiser_threshold": self.loc.threshold}, fh, indent=2)

    @classmethod
    def load(cls, folder):
        from tensorflow import keras
        obj = cls()
        parts = joblib.load(os.path.join(folder, "griddefense.joblib"))
        for k, v in parts.items():
            setattr(obj, k, v)
        obj.ae.model = keras.models.load_model(os.path.join(folder, "autoencoder.keras"))
        return obj
