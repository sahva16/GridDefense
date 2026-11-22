"""
Automated tests for the GridDefense console backend.

    GRIDDEFENSE_BUNDLE=/path/to/app_bundle python -m pytest -q tests

Covers: notebook reproduction on all test snapshots, ground-truth separation, input
validation, normal / attack / borderline cases, missing and tampered bundles, and
bundle-ID tracking in the event log.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
BUNDLE = os.environ.get("GRIDDEFENSE_BUNDLE")
if not BUNDLE:
    pytest.skip("set GRIDDEFENSE_BUNDLE to an exported app_bundle folder", allow_module_level=True)
_DB = tempfile.mkdtemp()
os.environ["GRIDDEFENSE_DB"] = str(Path(_DB) / "test_events.db")
sys.path.insert(0, str(BACKEND))

import app.main as M  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

C = TestClient(M.app)
GT = ["Label", "Attack_Type"] + [f"bus_label_{i+1}" for i in range(14)]


def _snap(i: int) -> dict:
    return {c: float(M.TEST[c].iloc[i]) for c in M.MEAS_COLS}


# ── 1. The app reproduces the notebook ──────────────────────────────
def test_reproduces_notebook_on_every_test_snapshot():
    assert M.CHECK["snapshots"] == len(M.TEST) == 11000
    for name, r in M.CHECK["checks"].items():
        assert r["match"] == r["total"], f"{name}: {r}"
    assert M.CHECK["passed"]
    assert M.CHECK["app_alarms"] == M.CHECK["notebook_alarms"]


# ── 2. Ground-truth separation (to-do 13) ───────────────────────────
def _outputs(df):
    s = M.PIPE.score(df)
    return s["fus"], s["alarm"], s["loc"], s["rf_cls"], s["votes"]


def test_output_unchanged_when_ground_truth_removed_or_altered():
    df = M.TEST.iloc[:2000].copy()
    base = _outputs(df)
    removed = df.drop(columns=GT + [c for c in df.columns if c.startswith("nb_")])
    altered = df.copy()
    rng = np.random.default_rng(0)
    altered["Label"] = 1 - altered["Label"]
    altered["Attack_Type"] = rng.integers(0, 4, len(altered))
    for c in GT[2:]:
        altered[c] = rng.integers(0, 2, len(altered))
    # Scoring the SAME input twice can differ by ~1e-16 in the scores, because the Random Forest adds its
    # trees' probabilities in parallel threads (summation order varies). So decisions must be identical
    # and scores equal to within 1e-12 — far below anything that could change a decision.
    for other in (_outputs(removed), _outputs(altered)):
        fus, alarm, loc, cls, votes = other
        assert np.abs(fus - base[0]).max() < 1e-12
        assert np.array_equal(alarm, base[1]) and np.array_equal(loc, base[2])
        assert np.array_equal(cls, base[3]) and np.array_equal(votes, base[4])


def test_pipeline_never_reads_ground_truth_columns():
    df = M.TEST.iloc[:50].copy()
    for c in GT:
        df[c] = "NOT-A-NUMBER"          # any read of these columns as numbers would crash
    M.PIPE.score(df)


# ── 3. Input validation (to-do 11) ──────────────────────────────────
def test_valid_snapshot_is_scored_and_matches_notebook():
    i = int(np.where(M.TEST.nb_alarm.values == 1)[0][0])
    r = C.post("/api/score", json=dict(snapshot=_snap(i)))
    assert r.status_code == 200
    ev = r.json()["event"]
    assert ev["result"]["alarm"] is True
    assert abs(ev["result"]["fusion"]["score"] - M.TEST.nb_fusion.iloc[i]) <= 0.0005 + 1e-9
    assert ev["truth_known"] is False and ev["verdict"] is None


def test_column_order_does_not_matter():
    snap = _snap(3)
    rev = dict(reversed(list(snap.items())))
    a = C.post("/api/score", json=dict(snapshot=snap)).json()["event"]["result"]["fusion"]["score"]
    b = C.post("/api/score", json=dict(snapshot=rev)).json()["event"]["result"]["fusion"]["score"]
    assert a == b


def test_positional_list_of_84_values():
    snap = _snap(3)
    r = C.post("/api/score", json=dict(snapshot=[snap[c] for c in M.MEAS_COLS]))
    assert r.status_code == 200


@pytest.mark.parametrize("mutate, expect", [
    (lambda s: s.pop("Vm_5"), "missing required column"),
    (lambda s: s.update(Va_3="abc"), "not a number"),
    (lambda s: s.update(Pd_4=None), "empty / NaN"),
    (lambda s: s.update(Vm_2=50.0), "outside the sanity limit"),
    (lambda s: s.update(Qg_ref_1=-5000), "outside the sanity limit"),
])
def test_invalid_snapshots_are_rejected(mutate, expect):
    s = _snap(0)
    mutate(s)
    n_before = M.STORE.count()
    r = C.post("/api/score", json=dict(snapshot=s))
    assert r.status_code == 422
    assert any(expect in e for e in r.json()["detail"]["errors"]), r.json()
    assert M.STORE.count() == n_before            # nothing was scored or logged


def test_wrong_length_list_rejected():
    r = C.post("/api/score", json=dict(snapshot=[1.0] * 56))
    assert r.status_code == 422 and "exactly 84" in r.json()["detail"]["errors"][0]


def test_infinite_value_rejected():
    from app.validate import InvalidSnapshot, validate_frame
    df = pd.DataFrame([_snap(0)])
    df.loc[0, "Va_7"] = np.inf
    with pytest.raises(InvalidSnapshot, match="infinite"):
        validate_frame(df)


# ── 4. Normal, attack and borderline cases (to-do 6) ───────────────
def test_normal_scenario_no_alarm():
    ev = C.post("/api/scenarios/S0/run").json()["event"]
    assert ev["truth"]["type"] == "Normal"
    assert ev["result"]["alarm"] is False
    assert ev["result"]["explanation"]["summary"].startswith("No alarm")
    assert ev["verdict"]["exact"] is True and ev["verdict"]["actual"] == []


def test_attack_simulation_has_verdict_and_explanation():
    ev = C.post("/api/simulate", json=dict(attack="Additive", buses=[4, 9], size_pct=2.5, direction=1, seed=5)).json()["event"]
    assert ev["result"]["alarm"] is True
    v = ev["verdict"]
    assert v["actual"] == [4, 9]
    assert set(v["correct"]) | set(v["missed"]) == {4, 9}
    assert v["exact"] == (v["missed"] == [] and v["extra"] == [])
    assert ev["result"]["explanation"]["lines"][-1].startswith("This is evidence")
    assert ev["result"]["measurement_table"]["rows"][3]["bus"] == 4


def test_borderline_snapshot_matches_notebook_and_is_flagged():
    gap = np.abs(M.TEST.nb_fusion.values - M.PIPE.fu["threshold"])
    i = int(np.argmin(gap))
    ev = C.post("/api/score", json=dict(snapshot=_snap(i))).json()["event"]
    assert ev["result"]["alarm"] == bool(M.TEST.nb_alarm.iloc[i])
    assert ev["result"]["explanation"]["borderline"] is True


def test_test_set_replay_has_ground_truth_verdict():
    i = int(np.where(M.TEST.Label.values == 1)[0][0])
    ev = M._record(M.TEST.iloc[[i]], "live", i)
    truth = [b + 1 for b in range(14) if int(M.TEST[f"bus_label_{b+1}"].iloc[i]) == 1]
    assert ev["verdict"]["actual"] == truth


# ── 5. Bundle tracking (to-do 12) ──────────────────────────────────
def test_every_event_carries_bundle_id():
    ev = C.post("/api/scenarios/S1/run").json()["event"]
    assert ev["bundle_id"] == M.BUNDLE_ID != "unknown"
    rows = M.STORE.db.execute("SELECT DISTINCT bundle_id FROM events").fetchall()
    assert rows == [(M.BUNDLE_ID,)]
    assert C.get("/api/export/events.csv").text.splitlines()[1].split(",")[2] == M.BUNDLE_ID


def test_status_reports_provenance_and_versions():
    st = C.get("/api/status").json()
    assert st["provenance"]["status"] in ("verified", "development")
    assert st["model"]["features"]["ae"] == 56 and st["model"]["features"]["rf"] == 104
    assert st["model"]["exported_at"]


# ── 6. Missing / tampered bundle (to-do 1, 4, 6) ───────────────────
def _start(bundle_dir: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, GRIDDEFENSE_BUNDLE=bundle_dir, GRIDDEFENSE_DB=str(Path(_DB) / "x.db"))
    code = "import app.main as m; print('STATUS', m.PROV['status']); print('REASONS', m.PROV['reasons'])"
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=300)


def test_missing_bundle_refuses_to_start():
    empty = tempfile.mkdtemp()
    p = _start(empty)
    assert p.returncode != 0
    assert "No model bundle" in (p.stdout + p.stderr)
    assert "does not fall back" in (p.stdout + p.stderr)


def test_tampered_manifest_is_unverified():
    d = Path(tempfile.mkdtemp())
    for f in ("griddefense_model.joblib", "test_snapshots.csv.gz"):
        os.symlink(Path(BUNDLE, f).resolve(), d / f)
    man = json.loads(Path(BUNDLE, "bundle_manifest.json").read_text())
    man["model_sha256"] = "0" * 64
    (d / "bundle_manifest.json").write_text(json.dumps(man))
    p = _start(str(d))
    assert "STATUS unverified" in p.stdout, p.stdout + p.stderr
    assert "fingerprint" in p.stdout


def test_wrong_notebook_reference_is_unverified():
    d = Path(tempfile.mkdtemp())
    os.symlink(Path(BUNDLE, "griddefense_model.joblib").resolve(), d / "griddefense_model.joblib")
    t = pd.read_csv(Path(BUNDLE, "test_snapshots.csv.gz"), keep_default_na=False)
    t.loc[0, "nb_alarm"] = 1 - t.loc[0, "nb_alarm"]
    t.to_csv(d / "test_snapshots.csv.gz", index=False, compression="gzip")
    shutil.copy(Path(BUNDLE, "bundle_manifest.json"), d / "bundle_manifest.json")
    p = _start(str(d))
    assert "STATUS unverified" in p.stdout, p.stdout + p.stderr
    assert "did NOT reproduce" in p.stdout


# ── Phone alerts (n8n webhook) ──────────────────────────────────────
def test_alarm_is_sent_to_n8n_webhook_and_normal_is_not():
    import http.server, json as _json, threading, time
    got = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            got.append(_json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200); self.end_headers()

        def log_message(self, *a): pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    old = (M.S.webhook, M.S.alert_scope)
    M.S.webhook, M.S.alert_scope = f"http://127.0.0.1:{srv.server_port}/webhook/griddefense-alarm", "visitor"
    try:
        assert C.post("/api/webhook/test").json()["ok"]
        C.post("/api/scenarios/S0/run")          # normal operation: no alert
        C.post("/api/scenarios/S3/run")          # coordinated attack on buses 9 and 14
        for _ in range(50):
            if len(got) >= 2: break
            time.sleep(0.1)
        time.sleep(0.3)
        assert [g["event"] for g in got] == ["griddefense.test", "griddefense.alarm"]
        a = got[1]
        assert a["attack_type"] == "Coordinated" and a["buses"] == [9, 14]
        assert a["fusion_score"] >= a["threshold"] and a["models"] == "verified"
        assert "attack on bus 9, 14" in a["message"] and "bus 9:" in a["message"]
    finally:
        M.S.webhook, M.S.alert_scope = old
        srv.shutdown()
