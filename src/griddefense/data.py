"""Synthetic IEEE 14-bus data: normal snapshots, the three FDIA types, noise, split.

Notebook Sections 3–4. The random draws are made in exactly the same order as
in the notebook, so the same seed gives the same dataset.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from . import config as C
from .grid import N_BUSES, ATTACKABLE, ADJ, GEN_BUSES, run_pf, measurements

BASE_COLS = ([f"Vm_{i+1}" for i in range(N_BUSES)] + [f"Va_{i+1}" for i in range(N_BUSES)] +
             [f"Pd_{i+1}" for i in range(N_BUSES)] + [f"Qd_{i+1}" for i in range(N_BUSES)])
BUS_LABEL_COLS = [f"bus_label_{i+1}" for i in range(N_BUSES)]


@dataclass
class AttackSettings:
    """Size of the injected attacks (fraction of the true value) and the angle bias at the maximum size."""
    attack_min: float = C.ATTACK_MIN
    attack_max: float = C.ATTACK_MAX
    va_max_deg: float = C.VA_ATTACK_MAX_DEG


# ── Measurement noise ────────────────────────────────────────────────
def add_noise(meas, rng):
    """Meter noise on Vm, Va, Pd and Qd (added AFTER the attack)."""
    noisy = meas.copy()
    Pd = meas[2 * N_BUSES:3 * N_BUSES]
    Qd = meas[3 * N_BUSES:4 * N_BUSES]
    noisy[0:N_BUSES] += rng.normal(0, C.VM_NOISE_STD, N_BUSES)
    noisy[N_BUSES:2 * N_BUSES] += rng.normal(0, C.VA_NOISE_STD, N_BUSES)
    noisy[2 * N_BUSES:3 * N_BUSES] += rng.normal(0, C.PD_NOISE_REL * np.maximum(np.abs(Pd), C.PD_NOISE_FLOOR), N_BUSES)
    noisy[3 * N_BUSES:4 * N_BUSES] += rng.normal(0, C.QD_NOISE_REL * np.maximum(np.abs(Qd), C.QD_NOISE_FLOOR), N_BUSES)
    return noisy


def add_gen_noise(pg, qg, rng):
    """Meter noise on generator outputs (the notebook uses the load floors for generators too)."""
    pg, qg = pg.copy(), qg.copy()
    if C.PG_NOISE_REL > 0:
        pg[GEN_BUSES] += rng.normal(0, C.PG_NOISE_REL * np.maximum(np.abs(pg[GEN_BUSES]), C.PD_NOISE_FLOOR))
    if C.QG_NOISE_REL > 0:
        qg[GEN_BUSES] += rng.normal(0, C.QG_NOISE_REL * np.maximum(np.abs(qg[GEN_BUSES]), C.QD_NOISE_FLOOR))
    return pg, qg


# ── The three attack types ──────────────────────────────────────────
def additive_attack(meas, rng, s: AttackSettings = AttackSettings()):
    """Vm × (1 ± 1–3 %) at 1–3 buses, plus an angle bias proportional to the size (≤ 0.5°)."""
    attacked = meas.copy()
    targets = rng.choice(ATTACKABLE, size=int(rng.integers(1, 4)), replace=False)
    for bus in targets:
        mag = float(rng.uniform(s.attack_min, s.attack_max))
        direction = int(rng.choice([-1, 1]))
        attacked[bus] *= (1 + direction * mag)
        attacked[N_BUSES + bus] += direction * s.va_max_deg * (mag / s.attack_max)
    return attacked, targets


def scaling_attack(meas, rng, s: AttackSettings = AttackSettings()):
    """Vm × (1 ± 1–3 %) at 1–3 buses; angles unchanged."""
    attacked = meas.copy()
    targets = rng.choice(ATTACKABLE, size=int(rng.integers(1, 4)), replace=False)
    for bus in targets:
        direction = int(rng.choice([-1, 1]))
        magnitude = float(rng.uniform(s.attack_min, s.attack_max))
        attacked[bus] *= (1 + direction * magnitude)
    return attacked, targets


def coordinated_attack(meas, rng, s: AttackSettings = AttackSettings(), adj=ADJ):
    """A bus and 1–2 of its neighbours, all pushed in the same direction."""
    attacked = meas.copy()
    center = int(rng.choice(ATTACKABLE))
    neighbors = np.where(adj[center] == 1)[0]
    neighbors = neighbors[np.isin(neighbors, ATTACKABLE)]
    if len(neighbors) > 0:
        n_nb = min(int(rng.integers(1, 3)), len(neighbors))
        targets = np.concatenate([[center], rng.choice(neighbors, size=n_nb, replace=False)])
    else:
        targets = np.array([center])
    direction = int(rng.choice([-1, 1]))
    for bus in targets:
        mag = float(rng.uniform(s.attack_min, s.attack_max))
        attacked[bus] *= (1 + direction * mag)
        attacked[N_BUSES + bus] += direction * s.va_max_deg * (mag / s.attack_max)
    return attacked, targets


ATTACKS = [("Additive", additive_attack, 1), ("Scaling", scaling_attack, 2), ("Coordinated", coordinated_attack, 3)]


def _frame(rows, pgs, qgs, labels, label, types):
    df = pd.DataFrame(rows, columns=BASE_COLS)
    df["Label"] = label
    df["Attack_Type"] = types
    pgs, qgs, labels = np.array(pgs), np.array(qgs), np.array(labels)
    for i in range(N_BUSES):
        df[f"Pg_ref_{i+1}"] = pgs[:, i]
        df[f"Qg_ref_{i+1}"] = qgs[:, i]
        df[f"bus_label_{i+1}"] = labels[:, i]
    return df


def generate_dataset(seed, n_normal=C.N_NORMAL, n_attack=C.N_ATTACK, settings: AttackSettings = None, verbose=True):
    """Return (df_normal, df_attacked) for one seed — raw measurements, before physics features.

    Same procedure and same order of random draws as the notebook's generate_dataset().
    """
    s = settings or AttackSettings()
    rng = np.random.default_rng(seed)
    say = print if verbose else (lambda *a, **k: None)

    rows, pgs, qgs = [], [], []
    while len(rows) < n_normal:
        pf = run_pf(rng.uniform(C.LOAD_MIN, C.LOAD_MAX, N_BUSES))
        if pf is None:
            continue
        result, pg, qg = pf
        rows.append(add_noise(measurements(result), rng))
        pg, qg = add_gen_noise(pg, qg, rng)
        pgs.append(pg); qgs.append(qg)
    say(f"  normal: {len(rows)} (seed {seed})")
    df_normal = _frame(rows, pgs, qgs, np.zeros((len(rows), N_BUSES), dtype=int), 0, 0)

    rows, pgs, qgs, types, labels = [], [], [], [], []
    for name, fn, code in ATTACKS:
        done = 0
        while done < n_attack:
            pf = run_pf(rng.uniform(C.LOAD_MIN, C.LOAD_MAX, N_BUSES))
            if pf is None:
                continue
            result, pg, qg = pf
            attacked, targets = fn(measurements(result), rng, s)
            bl = np.zeros(N_BUSES, dtype=int); bl[targets] = 1
            rows.append(add_noise(attacked, rng))
            pg, qg = add_gen_noise(pg, qg, rng)
            pgs.append(pg); qgs.append(qg); types.append(code); labels.append(bl)
            done += 1
        say(f"  {name}: {done}")
    df_attacked = _frame(rows, pgs, qgs, labels, 1, types)
    return df_normal, df_attacked


def split_indices(df_full, seed=C.SPLIT_SEED):
    """Stratified 70/15/15 split on Attack_Type (same calls as the notebook)."""
    all_idx = list(range(len(df_full)))
    labels = df_full["Attack_Type"].fillna(0).astype(int).tolist()
    train_idx, temp_idx = train_test_split(all_idx, test_size=C.TEST_FRACTION, random_state=seed, stratify=labels)
    val_idx, test_idx = train_test_split(temp_idx, test_size=0.50, random_state=seed,
                                         stratify=[labels[i] for i in temp_idx])
    assert not (set(train_idx) & set(val_idx)) and not (set(train_idx) & set(test_idx)) and not (set(val_idx) & set(test_idx))
    return train_idx, val_idx, test_idx
