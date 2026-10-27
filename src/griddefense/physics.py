"""Physics validation layer (notebook Section 8).

Four per-bus checks, each standardised with the mean and standard deviation of
normal TRAINING data:
    P_res        active-power mismatch
    Q_res        reactive-power mismatch
    Va_neighbor  largest deviation of a connected branch's angle difference from normal
    Vm_neighbor  largest deviation of a connected branch's voltage difference from normal
A check fires at a bus when its z-score exceeds Z; the layer flags a snapshot when
at least SCORE (2) checks fire at the same bus. Z is the first value in the grid
whose false-alarm rate on VALIDATION normals is below 5 %.
"""
import numpy as np

from . import config as C
from .features import build_V
from .grid import N_BUSES, N_BRANCHES, YF, YT, FROM_BUSES, TO_BUSES, BASE_MVA, RATE_A_MVA, BS_BUS

CHECK_NAMES = ["P_res", "Q_res", "Va_neighbor", "Vm_neighbor"] + (["S_loading"] if C.USE_S_LOADING else [])


class PhysicsValidator:
    def __init__(self):
        self.fitted = False

    # ── raw check quantities ──
    def compute(self, df):
        """Return P_res, Q_res, Q_KCL, Va-deviation, Vm-deviation and loading per bus (each n × 14)."""
        n = len(df)
        Vm_a = df[[f"Vm_{i+1}" for i in range(N_BUSES)]].values
        Va_a = df[[f"Va_{i+1}" for i in range(N_BUSES)]].values
        P = df[[f"P_res_{i+1}" for i in range(N_BUSES)]].values
        Q = df[[f"Q_res_{i+1}" for i in range(N_BUSES)]].values
        Qg_a = df[[f"Qg_ref_{i+1}" for i in range(N_BUSES)]].values
        Qd_a = df[[f"Qd_{i+1}" for i in range(N_BUSES)]].values
        QK, VAd, VMd, SL = (np.zeros((n, N_BUSES)) for _ in range(4))
        sr = np.where(RATE_A_MVA > 0, RATE_A_MVA, np.nan)
        for r in range(n):
            Vm, Va = Vm_a[r], Va_a[r]
            V = build_V(Vm, Va)
            Va_br = Va[FROM_BUSES] - Va[TO_BUSES]
            Vm_br = Vm[FROM_BUSES] - Vm[TO_BUSES]
            vad, vmd = np.zeros(N_BUSES), np.zeros(N_BUSES)
            for k in range(N_BRANCHES):
                f, t = FROM_BUSES[k], TO_BUSES[k]
                d = abs(abs(Va_br[k]) - self.baseline_va[k])
                vad[f] = max(vad[f], d); vad[t] = max(vad[t], d)
                d = abs(Vm_br[k] - self.baseline_vm[k])
                vmd[f] = max(vmd[f], d); vmd[t] = max(vmd[t], d)
            VAd[r], VMd[r] = vad, vmd
            Sf = V[FROM_BUSES] * np.conj(YF @ V) * BASE_MVA
            St = V[TO_BUSES] * np.conj(YT @ V) * BASE_MVA
            S = np.maximum(np.abs(Sf), np.abs(St))
            sp = np.where(np.isnan(sr), 0.0, S / sr)
            sb, Q_net = np.zeros(N_BUSES), np.zeros(N_BUSES)
            for k in range(N_BRANCHES):
                f, t = FROM_BUSES[k], TO_BUSES[k]
                sb[f] = max(sb[f], sp[k]); sb[t] = max(sb[t], sp[k])
                Q_net[f] += np.imag(Sf[k]); Q_net[t] += np.imag(St[k])
            SL[r] = sb
            QK[r] = Qg_a[r] + BS_BUS * Vm ** 2 - Qd_a[r] - Q_net
        return P, Q, QK, VAd, VMd, SL

    # ── fitting ──
    def fit(self, train_normal_df, val_normal_df):
        """Reference statistics from training normals; Z chosen on validation normals."""
        Vm = train_normal_df[[f"Vm_{i+1}" for i in range(N_BUSES)]].values
        Va = train_normal_df[[f"Va_{i+1}" for i in range(N_BUSES)]].values
        self.baseline_va = np.mean(np.abs(Va[:, FROM_BUSES] - Va[:, TO_BUSES]), axis=0)
        self.baseline_vm = np.mean(Vm[:, FROM_BUSES] - Vm[:, TO_BUSES], axis=0)
        P, Q, QK, VAd, VMd, _ = self.compute(train_normal_df)
        self.P_mu, self.P_sig = np.abs(P).mean(0), np.abs(P).std(0) + 1e-6
        self.Q_mu, self.Q_sig = np.abs(Q).mean(0), np.abs(Q).std(0) + 1e-6
        self.Vad_mu, self.Vad_sig = VAd.mean(0), VAd.std(0) + 1e-6
        self.Vmd_mu, self.Vmd_sig = VMd.mean(0), VMd.std(0) + 1e-6
        self.qkcl_duplicate_gap = float(np.abs(np.abs(Q) - np.abs(QK)).max())   # ≈ 0: Q_KCL = −Q_res
        self.score_votes = C.PHYSICS_VOTES
        self.fitted = True
        vals = self.compute(val_normal_df)
        self.val_fpr = {}
        self.z = None
        for z in C.PHYSICS_Z_GRID:
            fp = (self._votes(*vals, z) >= self.score_votes).any(axis=1).mean() * 100
            self.val_fpr[z] = fp
            if self.z is None and fp < C.PHYSICS_MAX_VAL_FPR:
                self.z = z
        if self.z is None:
            self.z = max(C.PHYSICS_Z_GRID)
        return self

    # ── scoring ──
    def check_flags(self, P, Q, QK, VAd, VMd, SL, z=None):
        z = self.z if z is None else z
        flags = {"P_res": (np.abs(P) - self.P_mu) / self.P_sig > z,
                 "Q_res": (np.abs(Q) - self.Q_mu) / self.Q_sig > z,
                 "Va_neighbor": (VAd - self.Vad_mu) / self.Vad_sig > z,
                 "Vm_neighbor": (VMd - self.Vmd_mu) / self.Vmd_sig > z}
        if C.USE_S_LOADING:
            flags["S_loading"] = SL > C.S_LOADING_THRESHOLD
        return flags

    def _votes(self, P, Q, QK, VAd, VMd, SL, z=None):
        return sum(f.astype(int) for f in self.check_flags(P, Q, QK, VAd, VMd, SL, z).values())

    def score(self, df):
        """Return dict: votes (n × 14), flag (0/1), score (max votes / number of checks), per-check flags."""
        vals = self.compute(df)
        flags = self.check_flags(*vals)
        votes = sum(f.astype(int) for f in flags.values())
        return {"votes": votes, "flag": (votes >= self.score_votes).any(axis=1).astype(int),
                "score": votes.max(axis=1) / len(CHECK_NAMES), "check_flags": flags}
