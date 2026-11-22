"""
GridDefense detection pipeline — the same steps as the notebook (Sections 3, 5–8, 10).

    raw snapshot  →  physics features (P_res, Q_res, LineFlow)   [notebook Section 3]
                  →  AE reconstruction error                      [Section 5]
                  →  RF attack-type probabilities                 [Section 6]
                  →  physics checks (per-bus votes)               [Section 8]
                  →  weighted fusion → alarm                      [Section 8]
                  →  RF localiser → attacked buses                [Section 7]

All trained parts and reference values come from the bundle exported by the
notebook (Section 20). Nothing is trained or tuned here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pypower.api import case14
from pypower.ext2int import ext2int
from pypower.idx_brch import F_BUS, T_BUS, RATE_A
from pypower.makeYbus import makeYbus

from .validate import MEAS_COLS

N_BUSES = 14

# ── Grid model (identical construction to notebook Sections 3 and 8) ──
_raw_case = case14()
_case_int = ext2int(_raw_case.copy())
BASE_MVA = _case_int["baseMVA"]
_branch = _case_int["branch"]
_Ybus, _Yf, _Yt = (m.toarray() for m in makeYbus(BASE_MVA, _case_int["bus"], _branch))
FROM_BUS = _branch[:, F_BUS].astype(int)
TO_BUS = _branch[:, T_BUS].astype(int)
RATE_A_ = _branch[:, RATE_A].astype(float)
N_BRANCHES = len(_branch)
BRANCHES = [(int(f) + 1, int(t) + 1) for f, t in zip(FROM_BUS, TO_BUS)]
TYPE_NAME = {0: "Normal", 1: "Additive", 2: "Scaling", 3: "Coordinated"}


def build_V(Vm, Va_deg):
    return Vm * np.exp(1j * np.deg2rad(Va_deg))


def _cols(prefix, n=N_BUSES):
    return [f"{prefix}_{i + 1}" for i in range(n)]


def add_physics_features(df: pd.DataFrame) -> pd.DataFrame:
    """P_res, Q_res (14 each) and LineFlow (20) — notebook add_physics_features()."""
    df = df.copy()
    Vm, Va = df[_cols("Vm")].values, df[_cols("Va")].values
    Pd, Qd = df[_cols("Pd")].values, df[_cols("Qd")].values
    Pg, Qg = df[_cols("Pg_ref")].values, df[_cols("Qg_ref")].values
    n = len(df)
    P_res, Q_res = np.zeros((n, N_BUSES)), np.zeros((n, N_BUSES))
    S_mag = np.zeros((n, N_BRANCHES))
    for r in range(n):
        V = build_V(Vm[r], Va[r])
        S = (V * np.conj(_Ybus @ V)) * BASE_MVA
        P_res[r] = np.real(S) - (Pg[r] - Pd[r])
        Q_res[r] = np.imag(S) - (Qg[r] - Qd[r])
        Sf = V[FROM_BUS] * np.conj(_Yf @ V) * BASE_MVA
        St = V[TO_BUS] * np.conj(_Yt @ V) * BASE_MVA
        S_mag[r] = np.maximum(np.abs(Sf), np.abs(St))
    new = {}
    for i in range(N_BUSES):
        new[f"P_res_{i + 1}"] = P_res[:, i]
        new[f"Q_res_{i + 1}"] = Q_res[:, i]
    for k in range(N_BRANCHES):
        new[f"LineFlow_{k + 1}"] = S_mag[:, k]
    return pd.concat([df, pd.DataFrame(new, index=df.index)], axis=1)


class Pipeline:
    def __init__(self, bundle: dict):
        b = bundle
        self.b = b
        self.cfg = b["config"]
        self.raw_cols = b["raw_cols"]          # used only by the simulator to lay out a generated row
        self.normal_ref = b.get("normal_reference")
        self.ae_layers = b["ae_layers"]
        self.scaler = b["scaler_ae"]
        self.ae_cols = b["ae_feature_cols"]
        self.ae_thr = b["ae_threshold"]
        self.rf = b["rf_model"]
        self.rf_cols = b["rf_feature_cols"]
        assert int(self.rf.classes_[0]) == 0, "RF class 0 must be Normal"
        self.loc = b["rf_loc"]
        self.loc_thr = b["loc_threshold"]
        self.nb1 = {int(k): list(v) for k, v in b["neighbors"].items()}
        self.nb2 = {int(k): list(v) for k, v in b["neighbors_2"].items()}
        self.ph = b["physics"]
        self.fu = b["fusion"]
        self.check_names = ["P_res", "Q_res", "Va_neighbor", "Vm_neighbor"] + (
            ["S_loading"] if self.ph["use_s_loading"] else [])

    # ── AE (numpy forward pass of the exported Keras weights) ──
    def _ae_forward(self, x):
        for L in self.ae_layers:
            x = x @ L["W"] + L["b"]
            if L["act"] == "relu":
                x = np.maximum(x, 0)
            elif L["act"] == "sigmoid":
                x = 1 / (1 + np.exp(-x))
        return x

    # ── Physics checks (notebook compute_physics + score_samples) ──
    def _physics(self, df):
        ph = self.ph
        Vm, Va = df[_cols("Vm")].values, df[_cols("Va")].values
        n = len(df)
        VAd, VMd, SL = np.zeros((n, N_BUSES)), np.zeros((n, N_BUSES)), np.zeros((n, N_BUSES))
        for r in range(n):
            va_br = Va[r][FROM_BUS] - Va[r][TO_BUS]
            vm_br = Vm[r][FROM_BUS] - Vm[r][TO_BUS]
            for k in range(N_BRANCHES):
                d = abs(abs(va_br[k]) - ph["baseline_va"][k])
                VAd[r, FROM_BUS[k]] = max(VAd[r, FROM_BUS[k]], d)
                VAd[r, TO_BUS[k]] = max(VAd[r, TO_BUS[k]], d)
                d = abs(vm_br[k] - ph["baseline_vm"][k])
                VMd[r, FROM_BUS[k]] = max(VMd[r, FROM_BUS[k]], d)
                VMd[r, TO_BUS[k]] = max(VMd[r, TO_BUS[k]], d)
            if ph["use_s_loading"]:
                V = build_V(Vm[r], Va[r])
                Sf = V[FROM_BUS] * np.conj(_Yf @ V) * BASE_MVA
                St = V[TO_BUS] * np.conj(_Yt @ V) * BASE_MVA
                S = np.maximum(np.abs(Sf), np.abs(St))
                sp = np.where(RATE_A_ > 0, S / np.where(RATE_A_ > 0, RATE_A_, 1), 0.0)
                for k in range(N_BRANCHES):
                    SL[r, FROM_BUS[k]] = max(SL[r, FROM_BUS[k]], sp[k])
                    SL[r, TO_BUS[k]] = max(SL[r, TO_BUS[k]], sp[k])
        P, Q = df[_cols("P_res")].values, df[_cols("Q_res")].values
        z = ph["Z"]
        flags = {
            "P_res": (np.abs(P) - ph["P_mu"]) / ph["P_sig"] > z,
            "Q_res": (np.abs(Q) - ph["Q_mu"]) / ph["Q_sig"] > z,
            "Va_neighbor": (VAd - ph["Vad_mu"]) / ph["Vad_sig"] > z,
            "Vm_neighbor": (VMd - ph["Vmd_mu"]) / ph["Vmd_sig"] > z,
        }
        if ph["use_s_loading"]:
            flags["S_loading"] = SL > ph["thr_S"]
        votes = sum(f.astype(int) for f in flags.values())
        zs = {"P_res": (np.abs(P) - ph["P_mu"]) / ph["P_sig"], "Q_res": (np.abs(Q) - ph["Q_mu"]) / ph["Q_sig"],
              "Va_neighbor": (VAd - ph["Vad_mu"]) / ph["Vad_sig"], "Vm_neighbor": (VMd - ph["Vmd_mu"]) / ph["Vmd_sig"]}
        return votes, flags, zs

    # ── Localiser topology features (notebook add_topo_features) ──
    def _topo(self, X):
        df = pd.DataFrame(X, columns=self.rf_cols)
        new = {}
        def block(bus, nbrs, p1, p2):
            own_vm, own_va = df[f"Vm_{bus}"].to_numpy(), df[f"Va_{bus}"].to_numpy()
            nvm = df[[f"Vm_{n}" for n in nbrs]].to_numpy().mean(axis=1)
            new[f"{p1}_Vm_{bus}"] = nvm
            new[f"{p2}_Vm_{bus}"] = own_vm - nvm
            ang = np.deg2rad(df[[f"Va_{n}" for n in nbrs]].to_numpy())
            nva = np.rad2deg(np.arctan2(np.sin(ang).mean(axis=1), np.cos(ang).mean(axis=1)))
            new[f"{p1}_Va_{bus}"] = nva
            new[f"{p2}_Va_{bus}"] = ((own_va - nva + 180) % 360) - 180
        for bus in range(1, 15):
            block(bus, self.nb1[bus], "neigh", "diff")
        for bus, nbrs in self.nb2.items():
            block(bus, nbrs, "neigh2", "diff2")
        out = np.hstack([X, pd.DataFrame(new).to_numpy()])
        assert out.shape[1] == 172
        return out

    def _loc_proba(self, X172):
        cols = []
        for est in self.loc.estimators_:
            p = est.predict_proba(X172)
            pos = np.where(est.classes_ == 1)[0]
            cols.append(p[:, pos[0]] if len(pos) else np.zeros(len(X172)))
        return np.column_stack(cols)

    # ── Full scoring ──
    def score(self, df_raw: pd.DataFrame) -> dict:
        # Only the 84 measurement columns go in. Ground-truth columns (Label, Attack_Type,
        # bus_label_*) are dropped here, so they cannot influence any score.
        df = add_physics_features(df_raw[MEAS_COLS].astype(float))
        xs = self.scaler.transform(df[self.ae_cols].values)
        recon = self._ae_forward(xs)
        sq = np.square(xs - recon)
        err = sq.mean(axis=1)
        fu = self.fu
        ae = np.clip((err - fu["ae_lo"]) / (fu["ae_hi"] - fu["ae_lo"] + 1e-9), 0, 1)
        X = df[self.rf_cols].values
        prob = self.rf.predict_proba(X)
        rf = 1 - prob[:, 0]
        votes, flags, zs = self._physics(df)
        phs = votes.max(axis=1) / self.ph["n_checks"]
        fus = fu["w_ae"] * ae + fu["w_rf"] * rf + fu["w_phys"] * phs
        alarm = fus >= fu["threshold"]
        loc_p = self._loc_proba(self._topo(X))
        loc = loc_p >= self.loc_thr
        # AE evidence per bus: share of the reconstruction error coming from each bus's 4 readings
        bus_of = np.array([int(c.split("_")[-1]) - 1 for c in self.ae_cols])
        ae_bus = np.stack([sq[:, bus_of == b].sum(axis=1) for b in range(N_BUSES)], axis=1)
        return dict(df=df, err=err, ae=ae, ae_flag=err > self.ae_thr, prob=prob, rf=rf,
                    rf_cls=self.rf.classes_[prob.argmax(axis=1)], votes=votes, flags=flags, zs=zs,
                    ph=phs, ph_flag=(votes >= self.ph["score_final"]).any(axis=1), fus=fus, alarm=alarm,
                    loc_p=loc_p, loc=loc, ae_bus=ae_bus)

    def explain(self, s: dict, i: int) -> dict:
        """One snapshot's result as plain JSON for the dashboard."""
        fu = self.fu
        alarm = bool(s["alarm"][i])
        prob = {TYPE_NAME[int(c)]: float(p) for c, p in zip(self.rf.classes_, s["prob"][i])}
        buses = []
        for b in range(N_BUSES):
            fired = [c for c in self.check_names if c in s["flags"] and bool(s["flags"][c][i, b])]
            buses.append(dict(
                bus=b + 1, votes=int(s["votes"][i, b]), physics_alarm=bool(s["votes"][i, b] >= self.ph["score_final"]),
                checks_failed=fired, z={k: round(float(v[i, b]), 2) for k, v in s["zs"].items()},
                loc_probability=float(s["loc_p"][i, b]), named=bool(alarm and s["loc"][i, b]),
                ae_error=float(s["ae_bus"][i, b])))
        return dict(
            alarm=alarm,
            fusion=dict(score=float(s["fus"][i]), threshold=float(fu["threshold"]),
                        parts=dict(ae=float(fu["w_ae"] * s["ae"][i]), rf=float(fu["w_rf"] * s["rf"][i]),
                                   physics=float(fu["w_phys"] * s["ph"][i])),
                        weights=dict(ae=float(fu["w_ae"]), rf=float(fu["w_rf"]), physics=float(fu["w_phys"]))),
            detectors=dict(ae=dict(score=float(s["ae"][i]), error=float(s["err"][i]), flag=bool(s["ae_flag"][i])),
                           rf=dict(score=float(s["rf"][i]), flag=bool(int(s["rf_cls"][i]) != 0)),
                           physics=dict(score=float(s["ph"][i]), flag=bool(s["ph_flag"][i]))),
            attack_type=TYPE_NAME[int(s["rf_cls"][i])] if alarm else None,
            type_probabilities=prob,
            named_buses=[b + 1 for b in range(N_BUSES) if alarm and s["loc"][i, b]],
            line_flow_mva=[round(float(v), 2) for v in s["df"][_cols("LineFlow", N_BRANCHES)].values[i]],
            buses=buses,
            measurement_table=self.measurement_table(s, i),
            measurements=dict(Vm=[round(float(v), 4) for v in s["df"][_cols("Vm")].values[i]],
                              Va=[round(float(v), 3) for v in s["df"][_cols("Va")].values[i]],
                              Pd=[round(float(v), 2) for v in s["df"][_cols("Pd")].values[i]],
                              Qd=[round(float(v), 2) for v in s["df"][_cols("Qd")].values[i]]),
        )

    def measurement_table(self, s: dict, i: int):
        """Observed value vs the normal reference (development normals) for Vm, Va, Pd, Qd at each bus.
        Display only: the deviation is NOT used by any detector."""
        ref = self.normal_ref
        if not ref:
            return None
        df = s["df"]
        rows = []
        for b in range(1, N_BUSES + 1):
            row = dict(bus=b)
            for q in ("Vm", "Va", "Pd", "Qd"):
                c = f"{q}_{b}"
                obs, mu, sd = float(df[c].values[i]), float(ref["mean"][c]), float(ref["std"][c])
                row[q] = dict(observed=obs, normal_mean=mu, normal_std=sd,
                              normal_p1=float(ref["p1"][c]), normal_p99=float(ref["p99"][c]),
                              deviation=obs - mu, deviation_sd=(obs - mu) / sd if sd > 1e-12 else None)
            rows.append(row)
        return dict(source=ref["source"], rows=rows)
