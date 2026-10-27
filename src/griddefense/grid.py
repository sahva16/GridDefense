"""IEEE 14-bus network data and AC power flow (PYPOWER).

Notebook Sections 2–3. The admittance matrices come from the internally
indexed case (ext2int); the Bus 9 shunt is read from the RAW case, because
ext2int shifts column positions and the converted value reads as zero.
"""
import numpy as np
from pypower.api import case14, runpf, ppoption
from pypower.ext2int import ext2int
from pypower.makeYbus import makeYbus
from pypower.idx_bus import PD, QD, VM, VA, BS
from pypower.idx_gen import GEN_BUS, PG, QG
from pypower.idx_brch import RATE_A

N_BUSES = 14
SLACK_BUS = 0                         # Bus 1 (0-based index 0), never attacked
ATTACKABLE = np.arange(1, N_BUSES)    # buses 2–14

_raw = case14()
_int = ext2int(case14())

BASE_MVA = _int["baseMVA"]
YBUS, YF, YT = (m.toarray() for m in makeYbus(BASE_MVA, _int["bus"], _int["branch"]))
FROM_BUSES = _int["branch"][:, 0].astype(int)
TO_BUSES = _int["branch"][:, 1].astype(int)
N_BRANCHES = len(FROM_BUSES)          # 20
RATE_A_MVA = _int["branch"][:, RATE_A].astype(float)
BS_BUS = _raw["bus"][:, BS]           # Bus 9: 19 MVAr shunt capacitor

BASE_PD = _raw["bus"][:, PD].copy()
BASE_QD = _raw["bus"][:, QD].copy()
GEN_BUSES = np.unique(_raw["gen"][:, GEN_BUS].astype(int) - 1)

# Bus adjacency (0-based) from the branch list
ADJ = np.zeros((N_BUSES, N_BUSES), dtype=int)
for _br in _raw["branch"]:
    _f, _t = int(_br[0]) - 1, int(_br[1]) - 1
    ADJ[_f, _t] = ADJ[_t, _f] = 1

# Same adjacency, 1-based, as used by the localiser's topology features
NEIGHBORS = {b + 1: [int(n) + 1 for n in np.where(ADJ[b])[0]] for b in range(N_BUSES)}

_PPOPT = ppoption(VERBOSE=0, OUT_ALL=0)


def run_pf(load_factors):
    """Solve an AC power flow with every bus load scaled by its own factor.

    Returns (result, pg, qg) — pg/qg are generator outputs per bus (MW, MVAr) —
    or None when the power flow does not converge.
    """
    ppc = case14()
    ppc["bus"][:, PD] = BASE_PD * load_factors
    ppc["bus"][:, QD] = BASE_QD * load_factors
    result, success = runpf(ppc, _PPOPT)
    if not success:
        return None
    pg, qg = np.zeros(N_BUSES), np.zeros(N_BUSES)
    for gen in result["gen"]:
        idx = int(round(gen[GEN_BUS])) - 1
        pg[idx] += gen[PG]
        qg[idx] += gen[QG]
    return result, pg, qg


def measurements(result):
    """56 true measurements of one solved power flow: Vm, Va (deg), Pd, Qd at 14 buses."""
    return np.concatenate([result["bus"][:, VM].copy(), result["bus"][:, VA].copy(),
                           result["bus"][:, PD].copy(), result["bus"][:, QD].copy()])
