"""Feature sets: 48 physics features (Section 3) and 68 topology features (Section 7).

Physics features (model inputs):
    P_res (14)    = P_calc − (Pg − Pd)        AC active-power mismatch per bus
    Q_res (14)    = Q_calc − (Qg − Qd)        AC reactive-power mismatch per bus
    LineFlow (20) = max(|S_from|, |S_to|)     apparent power per branch
Stored but NOT model inputs:
    BusBalance (14) = −P_res exactly (algebraic identity)
    Q_KCL (14)      = −Q_res exactly (used only to prove the duplicate)
"""
import numpy as np
import pandas as pd

from .grid import N_BUSES, N_BRANCHES, YBUS, YF, YT, FROM_BUSES, TO_BUSES, BASE_MVA, BS_BUS, NEIGHBORS

AE_FEATURES = ([f"Vm_{i+1}" for i in range(14)] + [f"Va_{i+1}" for i in range(14)] +
               [f"Pd_{i+1}" for i in range(14)] + [f"Qd_{i+1}" for i in range(14)])          # 56
RF_FEATURES = (AE_FEATURES + [f"P_res_{i+1}" for i in range(14)] + [f"Q_res_{i+1}" for i in range(14)] +
               [f"LineFlow_{i+1}" for i in range(20)])                                        # 104


def build_V(Vm, Va_deg):
    return Vm * np.exp(1j * np.deg2rad(Va_deg))


def add_physics_features(df, verbose=False):
    """Append P_res, Q_res, BusBalance, Q_KCL and LineFlow columns (same loop as the notebook)."""
    df = df.copy()
    n = len(df)
    P_res = np.zeros((n, N_BUSES)); Q_res = np.zeros((n, N_BUSES))
    BB = np.zeros((n, N_BUSES)); QK = np.zeros((n, N_BUSES)); S_mag = np.zeros((n, N_BRANCHES))
    Vm_a = df[[f"Vm_{i+1}" for i in range(N_BUSES)]].values
    Va_a = df[[f"Va_{i+1}" for i in range(N_BUSES)]].values
    Pd_a = df[[f"Pd_{i+1}" for i in range(N_BUSES)]].values
    Qd_a = df[[f"Qd_{i+1}" for i in range(N_BUSES)]].values
    Pg_a = df[[f"Pg_ref_{i+1}" for i in range(N_BUSES)]].values
    Qg_a = df[[f"Qg_ref_{i+1}" for i in range(N_BUSES)]].values
    if verbose:
        print(f"  Processing {n} samples...")
    for r in range(n):
        Vm, Va, Pd, Qd, Pg, Qg = Vm_a[r], Va_a[r], Pd_a[r], Qd_a[r], Pg_a[r], Qg_a[r]
        V = build_V(Vm, Va)
        S = (V * np.conj(YBUS @ V)) * BASE_MVA
        P_res[r] = np.real(S) - (Pg - Pd)
        Q_res[r] = np.imag(S) - (Qg - Qd)
        Sf = V[FROM_BUSES] * np.conj(YF @ V) * BASE_MVA
        St = V[TO_BUSES] * np.conj(YT @ V) * BASE_MVA
        Pf, Qf, Pt, Qt = np.real(Sf), np.imag(Sf), np.real(St), np.imag(St)
        S_mag[r] = np.maximum(np.abs(Sf), np.abs(St))
        P_net = np.zeros(N_BUSES); Q_net = np.zeros(N_BUSES)
        for k in range(N_BRANCHES):
            f, t = FROM_BUSES[k], TO_BUSES[k]
            P_net[f] += Pf[k]; P_net[t] += Pt[k]
            Q_net[f] += Qf[k]; Q_net[t] += Qt[k]
        BB[r] = (Pg - Pd) - P_net
        QK[r] = Qg + BS_BUS * Vm ** 2 - Qd - Q_net
    for i in range(N_BUSES):
        df[f"P_res_{i+1}"] = P_res[:, i]
        df[f"Q_res_{i+1}"] = Q_res[:, i]
        df[f"BusBalance_{i+1}"] = BB[:, i]
        df[f"Q_KCL_{i+1}"] = QK[:, i]
    for k in range(N_BRANCHES):
        df[f"LineFlow_{k+1}"] = S_mag[:, k]
    return df


# ── Topology features for the localiser (104 → 172) ───────────────────
def _two_hop(bus):
    cand = set()
    for nb in NEIGHBORS[bus]:
        cand.update(NEIGHBORS[nb])
    cand.discard(bus)
    cand -= set(NEIGHBORS[bus])
    return sorted(cand)


NEIGHBORS_2 = {b: _two_hop(b) for b in (3, 11, 14)}   # selected buses, as in the notebook


def _circ_mean_deg(a_deg):
    a = np.deg2rad(a_deg)
    return np.rad2deg(np.arctan2(np.sin(a).mean(axis=1), np.cos(a).mean(axis=1)))


def add_topo_features(X):
    """104 RF features → 172: per bus the neighbour-mean Vm/Va and own-minus-neighbour differences
    (56), plus the same with two-hop neighbours for buses 3, 11 and 14 (12). Angles use a circular
    mean and differences are wrapped to ±180°."""
    X = np.asarray(X)
    if X.ndim != 2 or X.shape[1] != 104:
        raise ValueError(f"Expected an (n, 104) array; received {X.shape}")
    df = pd.DataFrame(X, columns=RF_FEATURES)
    new = {}
    for prefix, groups in (("", {b: NEIGHBORS[b] for b in range(1, 15)}), ("2", NEIGHBORS_2)):
        for bus, nbs in groups.items():
            own_vm, own_va = df[f"Vm_{bus}"].to_numpy(), df[f"Va_{bus}"].to_numpy()
            nvm = df[[f"Vm_{n}" for n in nbs]].to_numpy().mean(axis=1)
            nva = _circ_mean_deg(df[[f"Va_{n}" for n in nbs]].to_numpy())
            new[f"neigh{prefix}_Vm_{bus}"] = nvm
            new[f"diff{prefix}_Vm_{bus}"] = own_vm - nvm
            new[f"neigh{prefix}_Va_{bus}"] = nva
            new[f"diff{prefix}_Va_{bus}"] = ((own_va - nva + 180) % 360) - 180
    out = np.hstack([X, pd.DataFrame(new).to_numpy()])
    assert out.shape == (len(X), 172) and np.isfinite(out).all()
    return out
