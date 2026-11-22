"""
Attack simulator — builds a NEW snapshot exactly the way the notebook generates
data (Section 3): random load levels → AC power flow (PYPOWER) → attack on the
chosen buses → meter noise. Only the attack choices (type, buses, size,
direction) come from the user instead of being random.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pypower.api import case14, runpf, ppoption
from pypower.idx_bus import PD, QD, VM, VA
from pypower.idx_gen import GEN_BUS, PG, QG

N_BUSES = 14
_PPOPT = ppoption(VERBOSE=0, OUT_ALL=0)
_BASE = case14()
_BASE_PD, _BASE_QD = _BASE["bus"][:, PD].copy(), _BASE["bus"][:, QD].copy()
GEN_BUSES = np.unique(_BASE["gen"][:, GEN_BUS].astype(int) - 1)
BASE_COLS = ([f"Vm_{i+1}" for i in range(N_BUSES)] + [f"Va_{i+1}" for i in range(N_BUSES)] +
             [f"Pd_{i+1}" for i in range(N_BUSES)] + [f"Qd_{i+1}" for i in range(N_BUSES)])
TYPE_CODE = {"Normal": 0, "Additive": 1, "Scaling": 2, "Coordinated": 3}


def _run_pf(load_factors):
    ppc = case14()
    ppc["bus"][:, PD] = _BASE_PD * load_factors
    ppc["bus"][:, QD] = _BASE_QD * load_factors
    result, success = runpf(ppc, _PPOPT)
    if not success:
        return None
    pg, qg = np.zeros(N_BUSES), np.zeros(N_BUSES)
    for gen in result["gen"]:
        idx = int(round(gen[GEN_BUS])) - 1
        pg[idx] += gen[PG]
        qg[idx] += gen[QG]
    return result, pg, qg


def make_snapshot(cfg: dict, raw_cols: list, attack: str, buses: list[int], size_pct: float,
                  direction: int, seed: int) -> pd.DataFrame:
    """One snapshot as a 1-row DataFrame with the notebook's raw columns."""
    rng = np.random.default_rng(int(seed))
    while True:
        pf = _run_pf(rng.uniform(cfg["LOAD_MIN"], cfg["LOAD_MAX"], N_BUSES))
        if pf is not None:
            break
    result, pg, qg = pf
    meas = np.concatenate([result["bus"][:, VM].copy(), result["bus"][:, VA].copy(),
                           result["bus"][:, PD].copy(), result["bus"][:, QD].copy()])
    targets = [b - 1 for b in buses] if attack != "Normal" else []
    mag, va_per_unit = size_pct / 100.0, cfg["VA_ATTACK_MAX_DEG"] / cfg["ATTACK_MAX"]
    for b in targets:
        meas[b] *= (1 + direction * mag)                       # voltage magnitude (all attack types)
        if attack in ("Additive", "Coordinated"):
            meas[N_BUSES + b] += direction * va_per_unit * mag  # angle bias (Scaling leaves angles alone)
    # meter noise — notebook add_noise() / add_gen_noise()
    Pd, Qd = meas[2 * N_BUSES:3 * N_BUSES].copy(), meas[3 * N_BUSES:4 * N_BUSES].copy()
    meas[0:N_BUSES] += rng.normal(0, cfg["VM_NOISE_STD"], N_BUSES)
    meas[N_BUSES:2 * N_BUSES] += rng.normal(0, cfg["VA_NOISE_STD"], N_BUSES)
    meas[2 * N_BUSES:3 * N_BUSES] += rng.normal(0, cfg["PD_NOISE_REL"] * np.maximum(np.abs(Pd), cfg["PD_NOISE_FLOOR"]), N_BUSES)
    meas[3 * N_BUSES:4 * N_BUSES] += rng.normal(0, cfg["QD_NOISE_REL"] * np.maximum(np.abs(Qd), cfg["QD_NOISE_FLOOR"]), N_BUSES)
    if cfg["PG_NOISE_REL"] > 0:
        pg[GEN_BUSES] += rng.normal(0, cfg["PG_NOISE_REL"] * np.maximum(np.abs(pg[GEN_BUSES]), cfg["PD_NOISE_FLOOR"]))
    if cfg["QG_NOISE_REL"] > 0:
        qg[GEN_BUSES] += rng.normal(0, cfg["QG_NOISE_REL"] * np.maximum(np.abs(qg[GEN_BUSES]), cfg["QD_NOISE_FLOOR"]))
    row = pd.DataFrame([meas], columns=BASE_COLS)
    row["Label"] = int(attack != "Normal")
    row["Attack_Type"] = TYPE_CODE[attack]
    for i in range(N_BUSES):
        row[f"Pg_ref_{i+1}"], row[f"Qg_ref_{i+1}"] = pg[i], qg[i]
        row[f"bus_label_{i+1}"] = int(i in targets)
    return row[raw_cols]
