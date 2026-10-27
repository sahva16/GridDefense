"""Simulated GPS spoofing — an angle-only time-synchronisation attack (notebook Section 16b).

SIMULATION ONLY: no GPS signal is generated. A PMU whose GPS clock is off by Δt
reports every angle shifted by 360° × f × Δt; Vm and the SCADA power readings do
not depend on GPS time and are unchanged. At 60 Hz, 1 µs ≈ 0.0216°.
"""
import numpy as np
import pandas as pd

from . import config as C
from .data import BASE_COLS, add_noise, add_gen_noise
from .features import add_physics_features
from .grid import N_BUSES, ATTACKABLE, ADJ, run_pf, measurements

GPS_F_HZ = 60
GPS_TYPE = 4          # reporting label only — not an RF class


def deg_to_us(deg, f_hz=GPS_F_HZ):
    return deg / (360.0 * f_hz) * 1e6


def gps_spoof_attack(meas, rng, offset_deg):
    """Shift the angle of one spoofed area (a bus + 0–2 neighbours, buses 2–14) by the same offset."""
    attacked = meas.copy()
    centre = int(rng.choice(ATTACKABLE))
    nbrs = np.where(ADJ[centre] == 1)[0]
    nbrs = nbrs[np.isin(nbrs, ATTACKABLE)]
    n_nb = min(int(rng.integers(0, 3)), len(nbrs))
    targets = np.array([centre] + list(rng.choice(nbrs, size=n_nb, replace=False)), dtype=int)
    attacked[N_BUSES + targets] += int(rng.choice([-1, 1])) * offset_deg
    assert set(np.where(attacked != meas)[0]) <= set(N_BUSES + targets), "only the spoofed angles may change"
    return attacked, targets


def gps_dataset(seed, offset_deg, n):
    """n spoofed snapshots, built like the main generator apart from the attack (with physics features)."""
    rng = np.random.default_rng(seed)
    rows, pgs, qgs, labels = [], [], [], []
    while len(rows) < n:
        pf = run_pf(rng.uniform(C.LOAD_MIN, C.LOAD_MAX, N_BUSES))
        if pf is None:
            continue
        result, pg, qg = pf
        att, targets = gps_spoof_attack(measurements(result), rng, offset_deg)
        bl = np.zeros(N_BUSES, dtype=int); bl[targets] = 1
        rows.append(add_noise(att, rng)); pg, qg = add_gen_noise(pg, qg, rng)
        pgs.append(pg); qgs.append(qg); labels.append(bl)
    d = pd.DataFrame(rows, columns=BASE_COLS)
    d["Label"] = 1
    d["Attack_Type"] = GPS_TYPE
    pgs, qgs, labels = np.array(pgs), np.array(qgs), np.array(labels)
    for i in range(N_BUSES):
        d[f"Pg_ref_{i+1}"] = pgs[:, i]; d[f"Qg_ref_{i+1}"] = qgs[:, i]; d[f"bus_label_{i+1}"] = labels[:, i]
    return add_physics_features(d)
