"""
Input validation — every snapshot is checked BEFORE it reaches the models.

A snapshot is the 84 measurement values the notebook's pipeline reads:
    Vm_1..14 (p.u.), Va_1..14 (degrees), Pd_1..14 and Qd_1..14 (MW / MVAr),
    Pg_ref_1..14 and Qg_ref_1..14 (generator outputs, MW / MVAr).
Ground-truth columns (Label, Attack_Type, bus_label_*) are NOT inputs and are ignored.

Rejected (with a clear message) when:
  • a required column is missing, or a positional list does not have exactly 84 values;
  • a value is not a number, or is NaN / infinite;
  • a value is outside the sanity limits below.

The sanity limits are set for this dashboard; they are NOT from the notebook. They are
deliberately wide (they only stop impossible input such as a voltage of 50 p.u.); the
independent test set lies well inside them (Vm 0.976–1.126 p.u., Va −18.6–0.5°,
powers −23–277 MW/MVAr).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

N_BUSES = 14
MEAS_COLS = ([f"Vm_{i+1}" for i in range(N_BUSES)] + [f"Va_{i+1}" for i in range(N_BUSES)] +
             [f"Pd_{i+1}" for i in range(N_BUSES)] + [f"Qd_{i+1}" for i in range(N_BUSES)] +
             [f"Pg_ref_{i+1}" for i in range(N_BUSES)] + [f"Qg_ref_{i+1}" for i in range(N_BUSES)])
GROUND_TRUTH_COLS = ["Label", "Attack_Type"] + [f"bus_label_{i+1}" for i in range(N_BUSES)]

LIMITS = {  # prefix: (low, high, unit)
    "Vm": (0.5, 1.5, "p.u."),
    "Va": (-180.0, 180.0, "degrees"),
    "Pd": (-1000.0, 1000.0, "MW"),
    "Qd": (-1000.0, 1000.0, "MVAr"),
    "Pg_ref": (-1000.0, 1000.0, "MW"),
    "Qg_ref": (-1000.0, 1000.0, "MVAr"),
}


class InvalidSnapshot(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _prefix(col: str) -> str:
    return col.rsplit("_", 1)[0]


def validate_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a float DataFrame with exactly MEAS_COLS (in the expected order), or raise InvalidSnapshot."""
    errors: list[str] = []
    if len(df) == 0:
        raise InvalidSnapshot(["no snapshot rows"])
    missing = [c for c in MEAS_COLS if c not in df.columns]
    if missing:
        show = ", ".join(missing[:8]) + (f" … ({len(missing)} missing in total)" if len(missing) > 8 else "")
        raise InvalidSnapshot([f"missing required column(s): {show}"])
    out = pd.DataFrame(index=df.index)
    for c in MEAS_COLS:  # selected BY NAME, so a different column order in the input cannot shift values
        vals = pd.to_numeric(df[c], errors="coerce")
        bad = vals.isna() & df[c].notna()
        if bad.any():
            errors.append(f"{c}: not a number ({df[c][bad].iloc[0]!r})")
            continue
        if vals.isna().any():
            errors.append(f"{c}: value is empty / NaN")
            continue
        arr = vals.to_numpy(dtype=float)
        if not np.isfinite(arr).all():
            errors.append(f"{c}: value is infinite")
            continue
        lo, hi, unit = LIMITS[_prefix(c)]
        off = (arr < lo) | (arr > hi)
        if off.any():
            errors.append(f"{c} = {arr[off][0]:g} {unit} is outside the sanity limit {lo:g}…{hi:g} {unit}")
            continue
        out[c] = arr
    if errors:
        raise InvalidSnapshot(errors)
    return out[MEAS_COLS]


def validate_payload(payload) -> pd.DataFrame:
    """Accepts {col: value}, a list of such dicts, or a list of exactly 84 numbers in MEAS_COLS order."""
    if isinstance(payload, dict):
        return validate_frame(pd.DataFrame([payload]))
    if isinstance(payload, list):
        if len(payload) == 0:
            raise InvalidSnapshot(["empty list"])
        if all(isinstance(r, dict) for r in payload):
            return validate_frame(pd.DataFrame(payload))
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in payload):
            if len(payload) != len(MEAS_COLS):
                raise InvalidSnapshot([f"a plain list must have exactly {len(MEAS_COLS)} values "
                                       f"in the order Vm, Va, Pd, Qd, Pg_ref, Qg_ref (got {len(payload)})"])
            if any(isinstance(v, float) and not math.isfinite(v) for v in payload):
                raise InvalidSnapshot(["list contains NaN or infinite values"])
            return validate_frame(pd.DataFrame([payload], columns=MEAS_COLS))
    raise InvalidSnapshot(["snapshot must be an object of column → value, a list of such objects, "
                           f"or a list of {len(MEAS_COLS)} numbers"])
