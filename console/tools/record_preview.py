"""
Record real backend results for the browser-only preview (frontend/src/demo-data.json).
Run with the backend on port 8000:   python tools/record_preview.py

Every result is a real backend call scored by the models the backend has loaded; the preview
only replays them.
"""
import json
import sys
import urllib.request
from pathlib import Path

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "demo-data.json"
SIZES = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0]


def call(path, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


call("/api/live", {"webhook": ""})
status = call("/api/status")
topology = call("/api/topology")
scenarios = call("/api/scenarios")
live = [e for e in call("/api/events?limit=400") if e["source"] == "live"][:150]
scen = {s["id"]: call(f"/api/scenarios/{s['id']}/run", {})["event"] for s in scenarios}
sims = {}
for t in ["Additive", "Scaling", "Coordinated"]:
    for bus in range(2, 15):
        for size in SIZES:
            for d in (1, -1):
                seed = 1000 * bus + int(size * 100) + (0 if d > 0 else 7) + ["Additive", "Scaling", "Coordinated"].index(t) * 100000
                sims[f"{t}|{bus}|{size}|{d}"] = call("/api/simulate", {"attack": t, "buses": [bus], "size_pct": size, "direction": d, "seed": seed})["event"]
    print(f"  {t} done")
data = dict(status=status, topology=topology, scenarios=scenarios, live=live, scenario_runs=scen, sims=sims)
OUT.write_text(json.dumps(data, separators=(",", ":")))
print(f"Saved {OUT}: {len(live)} live, {len(scen)} scenarios, {len(sims)} custom attacks, {OUT.stat().st_size / 1e6:.1f} MB")
