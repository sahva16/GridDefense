"""Generate the GridDefense datasets (notebook Sections 3 and 10).

    python scripts/generate_data.py            # writes data/dev_dataset_raw.csv,
                                               #        data/dev_dataset_physics.csv,
                                               #        data/test_dataset_seed20261014.csv
Takes a few minutes (22,000 AC power flows).
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from griddefense import config as C                              # noqa: E402
from griddefense.data import generate_dataset                    # noqa: E402
from griddefense.features import add_physics_features            # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "data"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    print(f"Development data (seed {C.DEV_SEED})")
    dn, da = generate_dataset(C.DEV_SEED)
    pd.concat([dn, da], ignore_index=True).to_csv(os.path.join(args.out, "dev_dataset_raw.csv"), index=False)
    dev = pd.concat([add_physics_features(dn), add_physics_features(da)], ignore_index=True)
    dev.to_csv(os.path.join(args.out, "dev_dataset_physics.csv"), index=False)
    print(f"  saved: {dev.shape}")

    print(f"Independent test set (seed {C.TEST_SEED})")
    tn, ta = generate_dataset(C.TEST_SEED)
    test = pd.concat([add_physics_features(tn), add_physics_features(ta)], ignore_index=True)
    test.to_csv(os.path.join(args.out, f"test_dataset_seed{C.TEST_SEED}.csv"), index=False)
    print(f"  saved: {test.shape}")


if __name__ == "__main__":
    main()
