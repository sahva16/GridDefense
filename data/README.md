# Datasets

All data is **synthetic**: AC power flows of the IEEE 14-bus system solved with PYPOWER, with random
loads, simulated attacks and meter noise. Normal and attacked snapshots are in the same file.

| File | Seed | Rows | Used for |
|---|---|---|---|
| `dev_dataset_raw.csv` | 42 | 11,000 (5,000 normal + 2,000 per attack type) | Development data, raw measurements only |
| `dev_dataset_physics.csv` | 42 | 11,000 | The same rows plus the physics features — split 70/15/15 into training, validation and internal test |
| `test_dataset_seed20261014.csv` | 20261014 | 11,000 (5,000 normal + 2,000 per attack type) | Independent test set — never used for training or tuning |

They can be rebuilt exactly with `python scripts/generate_data.py`.

## Columns

| Columns | Meaning |
|---|---|
| `Vm_1`…`Vm_14` | Voltage magnitude per bus (p.u.) |
| `Va_1`…`Va_14` | Voltage angle per bus (degrees) |
| `Pd_1`…`Pd_14`, `Qd_1`…`Qd_14` | Active (MW) and reactive (MVAr) load per bus |
| `Pg_ref_*`, `Qg_ref_*` | Generator output per bus, as measured (with noise); not attacked |
| `Label` | 0 = normal, 1 = attacked |
| `Attack_Type` | 0 = Normal, 1 = Additive, 2 = Scaling, 3 = Coordinated |
| `bus_label_1`…`bus_label_14` | 1 if that bus was attacked (all 0 for normal rows; Bus 1 is never attacked) |
| `P_res_*`, `Q_res_*` | Active / reactive power mismatch per bus (model inputs) |
| `LineFlow_1`…`LineFlow_20` | Apparent power per branch (model inputs) |
| `BusBalance_*`, `Q_KCL_*` | Stored for checking only: exactly −P_res and −Q_res, not model inputs |

`Label`, `Attack_Type` and `bus_label_*` are the ground truth written by the generator. They are used to
choose training rows and to score results, and are never model inputs.
