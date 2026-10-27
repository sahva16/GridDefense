"""Classical baseline: WLS AC state estimation + chi-square bad-data test (notebook Section 16).

Measurements (56): Vm and Va at 14 buses, net P and Q injection at 14 buses.
State (27): 13 angles (slack = 0) and 14 magnitudes → χ² with 29 degrees of freedom.
Meter sigmas = the generator's noise settings (the best case for this detector).
    J = Σ ((measured − model) / sigma)²     alarm when J is too large
"""
import numpy as np

from . import config as C
from .grid import N_BUSES as NB, YBUS, BASE_MVA, GEN_BUSES

NONSLACK = np.arange(1, NB)
M_MEAS, N_STATE = 4 * NB, (NB - 1) + NB
DOF = M_MEAS - N_STATE
_IS_GEN = np.zeros(NB, bool); _IS_GEN[GEN_BUSES] = True
_c = lambda p: [f"{p}_{i+1}" for i in range(NB)]


def h_and_H(va, vm):
    """Measurement model h(x) and its Jacobian H at state (angles in rad, magnitudes in p.u.)."""
    V = vm * np.exp(1j * va)
    I = YBUS @ V
    S = V * np.conj(I)
    dS_dVm = np.diag(V) @ np.conj(YBUS @ np.diag(V / vm)) + np.diag(np.conj(I) * V / vm)
    dS_dVa = 1j * np.diag(V) @ np.conj(np.diag(I) - YBUS @ np.diag(V))
    h = np.concatenate([vm, va, S.real, S.imag])
    H = np.zeros((M_MEAS, N_STATE))
    H[0:NB, NB - 1:] = np.eye(NB)
    H[NB + NONSLACK, np.arange(NB - 1)] = 1.0
    H[2 * NB:3 * NB, :NB - 1] = dS_dVa.real[:, NONSLACK]; H[2 * NB:3 * NB, NB - 1:] = dS_dVm.real
    H[3 * NB:, :NB - 1] = dS_dVa.imag[:, NONSLACK]; H[3 * NB:, NB - 1:] = dS_dVm.imag
    return h, H


def bdd_J(df, max_iter=15, tol=1e-7):
    """WLS state estimation per snapshot. Returns (J, converged). A snapshot that does not
    converge gets J = inf (counted as an alarm)."""
    Vm, Va = df[_c("Vm")].values, np.deg2rad(df[_c("Va")].values)
    Pd, Qd, Pg, Qg = df[_c("Pd")].values, df[_c("Qd")].values, df[_c("Pg_ref")].values, df[_c("Qg_ref")].values
    sP = np.sqrt((C.PD_NOISE_REL * np.maximum(np.abs(Pd), C.PD_NOISE_FLOOR)) ** 2
                 + _IS_GEN * (C.PG_NOISE_REL * np.maximum(np.abs(Pg), C.PD_NOISE_FLOOR)) ** 2) / BASE_MVA
    sQ = np.sqrt((C.QD_NOISE_REL * np.maximum(np.abs(Qd), C.QD_NOISE_FLOOR)) ** 2
                 + _IS_GEN * (C.QG_NOISE_REL * np.maximum(np.abs(Qg), C.QD_NOISE_FLOOR)) ** 2) / BASE_MVA
    J, conv = np.empty(len(df)), np.zeros(len(df), bool)
    for k in range(len(df)):
        z = np.concatenate([Vm[k], Va[k], (Pg[k] - Pd[k]) / BASE_MVA, (Qg[k] - Qd[k]) / BASE_MVA])
        w = 1.0 / np.concatenate([np.full(NB, C.VM_NOISE_STD), np.full(NB, np.deg2rad(C.VA_NOISE_STD)), sP[k], sQ[k]]) ** 2
        va, vm = Va[k].copy(), Vm[k].copy(); va[0] = 0.0
        ok = False
        for _ in range(max_iter):
            h, H = h_and_H(va, vm)
            HW = H.T * w
            dx = np.linalg.solve(HW @ H, HW @ (z - h))
            va[NONSLACK] += dx[:NB - 1]; vm += dx[NB - 1:]
            if np.max(np.abs(dx)) < tol:
                ok = True
                break
        h, _ = h_and_H(va, vm)
        J[k] = np.sum(w * (z - h) ** 2) if ok else np.inf
        conv[k] = ok
    return J, conv
