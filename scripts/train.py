"""Train GridDefense on the development data and save the models.

    python scripts/train.py                     # reads data/dev_dataset_physics.csv, writes models/
Every threshold, weight and model choice is made on the validation split only.
"""
import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
from griddefense import GridDefense                              # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "..", "data", "dev_dataset_physics.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "models", "trained"))
    args = ap.parse_args()
    dev = pd.read_csv(args.data)
    print(f"Development data: {dev.shape}")
    gd = GridDefense().fit(dev)
    gd.save(args.out)
    print(f"✓ Saved to {args.out}")


if __name__ == "__main__":
    main()
