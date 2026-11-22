import sys, numpy as np, pandas as pd
sys.path.insert(0, '.')
import joblib
from app.pipeline import Pipeline
from app.simulator import make_snapshot
B = sys.argv[1]
P = Pipeline(joblib.load(f'{B}/griddefense_model.joblib'))
rng = np.random.default_rng(777)
rows, meta = [], []
for i in range(1000):
    rows.append(make_snapshot(P.cfg, P.raw_cols, 'Normal', [], 1, 1, 10_000 + i)); meta.append(('Normal', []))
for i in range(1200):
    t = ['Additive', 'Scaling', 'Coordinated'][i % 3]
    k = int(rng.integers(1, 4)); buses = sorted(rng.choice(np.arange(2, 15), k, replace=False).tolist())
    size = float(rng.uniform(1, 3)); d = int(rng.choice([-1, 1]))
    rows.append(make_snapshot(P.cfg, P.raw_cols, t, buses, size, d, 20_000 + i)); meta.append((t, buses))
df = pd.concat(rows, ignore_index=True)
s = P.score(df)
n = df.Label.values == 0
print(f"simulated normals: {n.sum()}, false alarms {s['alarm'][n].mean()*100:.2f}%")
print(f"simulated attacks (1–3%, 1–3 buses): {(~n).sum()}, detected {s['alarm'][~n].mean()*100:.2f}%")
truth = df[[f'bus_label_{i}' for i in range(1, 15)]].values.astype(bool)
ex = (s['loc'][~n] == truth[~n]).all(axis=1).mean() * 100
print(f"localiser exact (all simulated attacks): {ex:.2f}%")
