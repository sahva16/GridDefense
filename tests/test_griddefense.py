"""Checks that the package behaves like the notebook.

    pytest -q
The last test compares the generator with the saved dataset in data/ (skipped if it is absent).
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

from griddefense import config as C                                             # noqa: E402
from griddefense.grid import NEIGHBORS, BS_BUS, N_BRANCHES, ATTACKABLE, run_pf, measurements   # noqa: E402
from griddefense.data import (generate_dataset, additive_attack, scaling_attack, coordinated_attack,   # noqa: E402
                              split_indices, BUS_LABEL_COLS, BASE_COLS)
from griddefense.features import add_physics_features, add_topo_features, NEIGHBORS_2, RF_FEATURES, AE_FEATURES  # noqa: E402
from griddefense.bad_data import bdd_J, h_and_H, DOF                             # noqa: E402
from griddefense.gps import gps_spoof_attack, deg_to_us                          # noqa: E402


# ── grid ──
def test_network_matches_notebook():
    assert NEIGHBORS == {1: [2, 5], 2: [1, 3, 4, 5], 3: [2, 4], 4: [2, 3, 5, 7, 9], 5: [1, 2, 4, 6],
                         6: [5, 11, 12, 13], 7: [4, 8, 9], 8: [7], 9: [4, 7, 10, 14], 10: [9, 11],
                         11: [6, 10], 12: [6, 13], 13: [6, 12, 14], 14: [9, 13]}
    assert NEIGHBORS_2 == {3: [1, 5, 7, 9], 11: [5, 9, 12, 13], 14: [4, 6, 7, 10, 12]}
    assert BS_BUS[8] == 19.0 and N_BRANCHES == 20
    assert len(AE_FEATURES) == 56 and len(RF_FEATURES) == 104


# ── attacks ──
def _clean_meas():
    result, pg, qg = run_pf(np.ones(14))
    return measurements(result)


def test_scaling_changes_only_voltage_magnitude():
    m, rng = _clean_meas(), np.random.default_rng(0)
    for _ in range(200):
        a, tg = scaling_attack(m, rng)
        d = np.nonzero(a - m)[0]
        assert set(d) <= set(tg) and 0 not in tg and 1 <= len(tg) <= 3
        assert np.all(np.abs(a[tg] / m[tg] - 1) <= C.ATTACK_MAX + 1e-12)


def test_additive_angle_bias_at_most_half_degree():
    m, rng = _clean_meas(), np.random.default_rng(1)
    for _ in range(200):
        a, tg = additive_attack(m, rng)
        assert np.all(np.abs(a[14 + tg] - m[14 + tg]) <= C.VA_ATTACK_MAX_DEG + 1e-12)
        assert set(np.nonzero(a - m)[0]) <= set(tg) | set(14 + tg)


def test_coordinated_attack_is_a_bus_and_its_neighbours_in_one_direction():
    m, rng = _clean_meas(), np.random.default_rng(2)
    for _ in range(200):
        a, tg = coordinated_attack(m, rng)
        centre = tg[0] + 1
        assert all(int(b) + 1 in NEIGHBORS[centre] for b in tg[1:])
        signs = np.sign(a[tg] - m[tg])
        assert len(set(signs)) == 1 and 0 not in tg


def test_gps_attack_changes_only_spoofed_angles():
    m, rng = _clean_meas(), np.random.default_rng(3)
    for off in (0.1, 5.0):
        for _ in range(200):
            a, tg = gps_spoof_attack(m, rng, off)
            d = a - m
            assert np.allclose(np.abs(d[14 + tg]), off) and np.count_nonzero(d) == len(tg) and 0 not in tg
    assert abs(deg_to_us(1.0) - 46.296) < 1e-3


# ── data ──
def test_generator_labels_and_repeatability():
    n1, a1 = generate_dataset(7, n_normal=20, n_attack=10, verbose=False)
    n2, a2 = generate_dataset(7, n_normal=20, n_attack=10, verbose=False)
    pd.testing.assert_frame_equal(a1, a2)                       # same seed → same data
    assert (n1[BUS_LABEL_COLS].values == 0).all() and (n1.Label == 0).all()
    assert (a1[BUS_LABEL_COLS].values.sum(axis=1) >= 1).all() and (a1.bus_label_1 == 0).all()
    assert sorted(a1.Attack_Type.unique()) == [1, 2, 3]
    assert list(a1.columns[:56]) == BASE_COLS


def test_split_is_stratified_70_15_15():
    df = pd.DataFrame({"Attack_Type": [0] * 500 + [1] * 200 + [2] * 200 + [3] * 200})
    tr, va, te = split_indices(df)
    assert (len(tr), len(va), len(te)) == (770, 165, 165)


# ── physics features ──
def test_physics_identities():
    n, a = generate_dataset(11, n_normal=30, n_attack=10, verbose=False)
    d = add_physics_features(pd.concat([n, a], ignore_index=True))
    P = d[[f"P_res_{i+1}" for i in range(14)]].values
    Q = d[[f"Q_res_{i+1}" for i in range(14)]].values
    BB = d[[f"BusBalance_{i+1}" for i in range(14)]].values
    QK = d[[f"Q_KCL_{i+1}" for i in range(14)]].values
    assert np.abs(P + BB).max() < 1e-9                         # BusBalance = −P_res
    assert np.abs(Q + QK).max() < 1e-9                         # Q_KCL = −Q_res
    assert add_topo_features(d[RF_FEATURES].values).shape == (len(d), 172)


def test_residuals_are_zero_on_a_clean_power_flow():
    result, pg, qg = run_pf(np.full(14, 1.05))
    m = measurements(result)
    row = dict(zip(BASE_COLS, m))
    row.update({f"Pg_ref_{i+1}": pg[i] for i in range(14)}); row.update({f"Qg_ref_{i+1}": qg[i] for i in range(14)})
    d = add_physics_features(pd.DataFrame([row]))
    assert np.abs(d[[f"P_res_{i+1}" for i in range(14)]].values).max() < 1e-4
    assert np.abs(d[[f"Q_res_{i+1}" for i in range(14)]].values).max() < 1e-4


# ── classical bad-data test ──
def test_bad_data_test_on_clean_and_noisy_data():
    assert DOF == 29
    result, pg, qg = run_pf(np.full(14, 0.95))
    va, vm = np.deg2rad(result["bus"][:, 8]), result["bus"][:, 7]
    h0, H0 = h_and_H(va, vm); Hn = np.zeros_like(H0); eps = 1e-7
    for j in range(H0.shape[1]):                               # Jacobian vs finite differences
        va1, vm1 = va.copy(), vm.copy()
        if j < 13: va1[j + 1] += eps
        else: vm1[j - 13] += eps
        Hn[:, j] = (h_and_H(va1, vm1)[0] - h0) / eps
    assert np.max(np.abs(H0 - Hn)) < 1e-4
    n, _ = generate_dataset(5, n_normal=200, n_attack=1, verbose=False)
    J, conv = bdd_J(n)
    assert conv.all() and 20 < J.mean() < 40                  # χ² with 29 dof has mean 29


# ── same data as the notebook ──
DEV_RAW = os.path.join(ROOT, "data", "dev_dataset_raw.csv")


@pytest.mark.skipif(not os.path.exists(DEV_RAW), reason="data/dev_dataset_raw.csv not present")
def test_generator_reproduces_saved_development_data():
    saved = pd.read_csv(DEV_RAW)
    n, a = generate_dataset(C.DEV_SEED, verbose=False)
    new = pd.concat([n, a], ignore_index=True)
    assert list(new.columns) == list(saved.columns) and new.shape == saved.shape
    np.testing.assert_allclose(new.values.astype(float), saved.values.astype(float), rtol=0, atol=1e-9)
