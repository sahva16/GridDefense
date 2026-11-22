"""
GridDefense backend — FastAPI.

Run (from the backend folder):   uvicorn app.main:app --port 8000
Bundle folder:                   ./bundle  (or set GRIDDEFENSE_BUNDLE=/path/to/app_bundle)
n8n alerts:                      set N8N_WEBHOOK_URL, or paste the URL in the dashboard's Settings
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import httpx
import joblib
import numpy as np
import pandas as pd
import sklearn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from fastapi.responses import PlainTextResponse

from .bundle import load_bundle, provenance, verify_against_notebook
from .explain import explain_text
from .pipeline import BRANCHES, N_BUSES, TYPE_NAME, Pipeline
from .validate import GROUND_TRUTH_COLS, MEAS_COLS, InvalidSnapshot, LIMITS, validate_frame, validate_payload
from .scenarios import BY_ID as SCENARIO_BY_ID, SCENARIOS
from .simulator import make_snapshot
from .store import EventStore

_ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path(os.environ.get("GRIDDEFENSE_BUNDLE", _ROOT / "bundle"))
# ── Load the exported system. There is NO fallback: without a real bundle the app refuses to start. ──
_bundle, MANIFEST, TEST, INTEGRITY = load_bundle(BUNDLE)
PIPE = Pipeline(_bundle)
Y, T = TEST["Label"].values, TEST["Attack_Type"].values
BUS_LABELS = [f"bus_label_{i+1}" for i in range(N_BUSES)]
STORE = EventStore(Path(os.environ.get("GRIDDEFENSE_DB", _ROOT / "data" / "events.db")))


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Verification: the app must reproduce the notebook's Section 10 decisions on EVERY test snapshot ──
CHECK = verify_against_notebook(PIPE, TEST)
PROV = provenance(MANIFEST, INTEGRITY, CHECK, _bundle)
BUNDLE_ID = PROV["bundle_id"]
print(f"[GridDefense] bundle {BUNDLE_ID} · {PROV['label']} · "
      + ", ".join(f"{k} {v['match']}/{v['total']}" for k, v in CHECK["checks"].items()))
for r in PROV["reasons"]:
    print(f"[GridDefense]   ! {r}")
if os.environ.get("GRIDDEFENSE_STRICT") == "1" and PROV["status"] != "verified":
    raise SystemExit("[GridDefense] GRIDDEFENSE_STRICT=1 and the bundle is not verified — refusing to start.")


def _base_flows():
    """Active power on each branch in the IEEE 14-bus base case (MW, from-end), for the flow animation."""
    from pypower.api import case14, runpf, ppoption
    r, ok = runpf(case14(), ppoption(VERBOSE=0, OUT_ALL=0))
    return [round(float(x), 2) for x in r["branch"][:, 13]] if ok else [0.0] * len(BRANCHES)


BASE_FLOW = _base_flows()


# ── State ──
class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.events: deque = deque(maxlen=400)
        self.alarms: dict[int, dict] = {}
        self.next_id = STORE.max_id() + 1
        self.running = True
        self.interval = 2.0
        # quiet: normal snapshots only (Open Day default, so only visitors' attacks raise alarms)
        # realistic: ~8 % attacks; test: the test set as it is
        self.mode = os.environ.get("FEED_MODE", "quiet")
        self.webhook = os.environ.get("N8N_WEBHOOK_URL", "")
        # which alarms go to n8n: "visitor" (attack simulator only), "all", or "off"
        self.alert_scope = os.environ.get("ALERT_SCOPE", "visitor")
        self.loop: asyncio.AbstractEventLoop | None = None
        self.stats = dict(scored=0, alarms=0, started=_now())
        self.clients: set[WebSocket] = set()


S = State()
_rng = random.Random(2026)


def _truth(row) -> dict:
    """Ground truth — shown in the dashboard for demonstration only; the pipeline never uses it."""
    return dict(type=TYPE_NAME[int(row["Attack_Type"])],
                buses=[i + 1 for i in range(N_BUSES) if int(row[BUS_LABELS[i]]) == 1])


def _verdict(named: list[int], truth: dict | None) -> dict | None:
    """Localisation verdict — only where the true attacked buses are known (simulator, scenario, test-set replay)."""
    if truth is None:
        return None
    actual, pred = set(truth["buses"]), set(named)
    return dict(actual=sorted(actual), predicted=sorted(pred), correct=sorted(actual & pred),
                missed=sorted(actual - pred), extra=sorted(pred - actual), exact=actual == pred)


def _result(df_row: pd.DataFrame) -> dict:
    """Validate → score → explain one snapshot. Ground truth is never passed to the pipeline."""
    clean = validate_frame(df_row)
    s = PIPE.score(clean)
    res = PIPE.explain(s, 0)
    ph = PIPE.ph
    res["explanation"] = explain_text(res, ph["Z"], ph["score_final"], ph["n_checks"], PIPE.loc_thr, PIPE.ae_thr)
    return res


def _record(df_row: pd.DataFrame, source: str, snapshot=None, extra=None, truth_known=True) -> dict:
    res = _result(df_row)
    truth = _truth(df_row.iloc[0]) if truth_known else None
    with S.lock:
        eid = S.next_id; S.next_id += 1
        ev = dict(id=eid, time=_now(), source=source, snapshot=snapshot, result=res, bundle_id=BUNDLE_ID,
                  truth=truth or dict(type=None, buses=[]), truth_known=truth_known,
                  verdict=_verdict(res["named_buses"], truth), **(extra or {}))
        S.events.appendleft(ev)
        STORE.add(ev)
        S.stats["scored"] += 1
        if res["alarm"]:
            S.stats["alarms"] += 1
            sev = "critical" if res["fusion"]["score"] >= 0.75 else "high" if res["fusion"]["score"] >= 0.55 else "medium"
            S.alarms[eid] = dict(id=eid, event_id=eid, time=ev["time"], source=source, severity=sev,
                                 attack_type=res["attack_type"], buses=res["named_buses"],
                                 score=res["fusion"]["score"], status="new", notes=[], webhook=None)
    if res["alarm"] and (S.alert_scope == "all" or (S.alert_scope == "visitor" and source in ("simulator", "scenario"))):
        with S.lock:
            if S.webhook:
                S.alarms[eid]["webhook"] = dict(ok=None, pending=True, at=_now())
        threading.Thread(target=_send_webhook, args=(eid,), daemon=True).start()
    return ev


for _ev in reversed(STORE.recent(300)):      # restore the recent history after a restart
    _ev.setdefault("bundle_id", None)
    _ev["verdict"] = _verdict(_ev["result"]["named_buses"], _ev["truth"]) if _ev["truth_known"] else None
    S.events.appendleft(_ev)


def _send_webhook(eid: int):
    with S.lock:
        url, a = S.webhook, dict(S.alarms.get(eid, {}))
        ev = next((e for e in S.events if e["id"] == eid), None)
    if not url or not a or ev is None:
        return
    r = ev["result"]
    failed = [b for b in r["buses"] if b["physics_alarm"]]
    plain = dict(P_res="real-power balance", Q_res="reactive-power balance",
                 Va_neighbor="angle vs neighbours", Vm_neighbor="voltage vs neighbours", S_loading="line loading")
    # Phone-friendly: physics evidence for the named buses first; other flagged buses (usually neighbours,
    # because two of the four checks compare a bus with its neighbours) only listed by number.
    named = set(a["buses"])
    on_named = [b for b in failed if b["bus"] in named]
    others = [b["bus"] for b in failed if b["bus"] not in named]
    if on_named:
        phys = "Physics checks failed: " + "; ".join(
            f"bus {b['bus']}: {', '.join(plain.get(c, c) for c in b['checks_failed'])}" for b in on_named)
        if others:
            phys += f"\nAlso flagged nearby: bus {', '.join(map(str, others))}"
    elif failed:
        phys = f"Physics checks failed at bus {', '.join(str(b['bus']) for b in failed)}"
    else:
        phys = "No physics check failed (caught by the learned detectors)"
    msg = (f"GridDefense ALARM ({a['severity'].upper()})\n"
           f"{a['attack_type']} attack on bus {', '.join(map(str, a['buses'])) or '?'}\n"
           f"Fusion score {r['fusion']['score']:.2f} (alarm at {r['fusion']['threshold']:.2f})\n" + phys +
           f"\nTime {a['time']}\nModels: bundle {BUNDLE_ID} ({PROV['label']})" +
           ("" if PROV["status"] == "verified" else "\nNOT the verified notebook models - test alert only."))
    payload = dict(event="griddefense.alarm", message=msg, alarm_id=eid, time=a["time"], severity=a["severity"],
                   source=a["source"], attack_type=a["attack_type"], buses=a["buses"],
                   fusion_score=round(r["fusion"]["score"], 3), threshold=round(r["fusion"]["threshold"], 3),
                   physics_checks=[dict(bus=b["bus"], failed=b["checks_failed"]) for b in r["buses"] if b["physics_alarm"]],
                   bundle_id=BUNDLE_ID, models=PROV["status"],
                   dashboard_url=os.environ.get("DASHBOARD_URL", "http://localhost:8000"))
    try:
        resp = httpx.post(url, json=payload, timeout=8)
        status = dict(ok=resp.is_success, code=resp.status_code, at=_now())
    except Exception as e:  # noqa: BLE001
        status = dict(ok=False, error=str(e)[:200], at=_now())
    with S.lock:
        if eid in S.alarms:
            S.alarms[eid]["webhook"] = status
            out = dict(S.alarms[eid])
        else:
            out = None
    if out and S.loop:
        asyncio.run_coroutine_threadsafe(_broadcast(dict(type="alarm_update", alarm=out)), S.loop)


def _pick_snapshot() -> int:
    if S.mode == "test":
        return _rng.randrange(len(TEST))
    if S.mode == "quiet":
        pool = np.where(Y == 0)[0]
        return int(pool[_rng.randrange(len(pool))])
    pool = np.where(Y == 1)[0] if _rng.random() < 0.08 else np.where(Y == 0)[0]
    return int(pool[_rng.randrange(len(pool))])


async def _broadcast(msg: dict):
    dead = []
    for ws in list(S.clients):
        try:
            await ws.send_text(json.dumps(msg, default=float))
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        S.clients.discard(ws)


async def _live_loop():
    while True:
        await asyncio.sleep(S.interval)
        if not S.running:
            continue
        i = _pick_snapshot()
        ev = await asyncio.to_thread(_record, TEST.iloc[[i]], "live", i)
        await _broadcast(dict(type="event", event=ev, alarm=S.alarms.get(ev["id"]), stats=S.stats))


app = FastAPI(title="GridDefense API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def _start():
    S.loop = asyncio.get_running_loop()
    asyncio.create_task(_live_loop())


# ── API ──
@app.get("/api/status")
def status():
    fu = PIPE.fu
    return dict(
        self_check=CHECK, provenance=PROV, bundle_id=BUNDLE_ID, running=S.running, interval=S.interval, mode=S.mode, webhook=bool(S.webhook), alert_scope=S.alert_scope,
        stats=S.stats, test_snapshots=int(len(TEST)), logged_events=STORE.count(),
        model=dict(sklearn_bundle=_bundle.get("sklearn_version"), sklearn_app=sklearn.__version__,
                   numpy_bundle=_bundle.get("numpy_version"), numpy_app=np.__version__,
                   exported_at=MANIFEST.get("exported_at_utc"), manifest_versions=MANIFEST.get("versions"),
                   model_sha256=MANIFEST.get("model_sha256"), source_md5=MANIFEST.get("source_md5"),
                   integrity=INTEGRITY, colab_checks=MANIFEST.get("colab_checks"),
                   features=dict(ae=len(PIPE.ae_cols), rf=len(PIPE.rf_cols), localiser=172,
                                 ae_cols=PIPE.ae_cols, rf_cols=PIPE.rf_cols),
                   fusion_bounds=dict(ae_lo=fu["ae_lo"], ae_hi=fu["ae_hi"]),
                   fusion=dict(w_ae=fu["w_ae"], w_rf=fu["w_rf"], w_phys=fu["w_phys"], threshold=fu["threshold"]),
                   physics=dict(Z=PIPE.ph["Z"], votes=PIPE.ph["score_final"], checks=PIPE.check_names),
                   loc_threshold=PIPE.loc_thr, ae_threshold=PIPE.ae_thr),
        config={k: v for k, v in PIPE.cfg.items()})


@app.get("/api/topology")
def topology():
    return dict(buses=list(range(1, N_BUSES + 1)), branches=BRANCHES, slack=1,
                generators=[1, 2], condensers=[3, 6, 8], shunt=[9],
                base_flow_mw=BASE_FLOW)


@app.get("/api/events")
def events(limit: int = 60):
    with S.lock:
        return list(S.events)[:limit]


@app.get("/api/events/{eid}")
def event(eid: int):
    with S.lock:
        ev = next((e for e in S.events if e["id"] == eid), None)
        al = S.alarms.get(eid)
    if ev is None:
        raise HTTPException(404, "event no longer in memory")
    return dict(event=ev, alarm=al)


@app.get("/api/alarms")
def alarms():
    with S.lock:
        return sorted(S.alarms.values(), key=lambda a: -a["id"])


class AlarmAction(BaseModel):
    action: str = Field(pattern="^(acknowledge|escalate|dismiss|resolve)$")
    note: str = ""


@app.post("/api/alarms/{aid}")
async def alarm_action(aid: int, body: AlarmAction):
    with S.lock:
        a = S.alarms.get(aid)
        if a is None:
            raise HTTPException(404, "unknown alarm")
        a["status"] = {"acknowledge": "acknowledged", "escalate": "escalated",
                       "dismiss": "dismissed", "resolve": "resolved"}[body.action]
        a["notes"].append(dict(time=_now(), action=body.action, note=body.note))
        out = dict(a)
    STORE.action(aid, _now(), body.action, body.note)
    await _broadcast(dict(type="alarm_update", alarm=out))
    return out


class LiveControl(BaseModel):
    running: bool | None = None
    interval: float | None = Field(default=None, ge=0.5, le=30)
    mode: str | None = Field(default=None, pattern="^(quiet|realistic|test)$")
    webhook: str | None = None
    alert_scope: str | None = Field(default=None, pattern="^(visitor|all|off)$")


@app.post("/api/live")
def live_control(body: LiveControl):
    if body.running is not None:
        S.running = body.running
    if body.interval is not None:
        S.interval = body.interval
    if body.mode is not None:
        S.mode = body.mode
    if body.webhook is not None:
        S.webhook = body.webhook.strip()
    if body.alert_scope is not None:
        S.alert_scope = body.alert_scope
    return dict(running=S.running, interval=S.interval, mode=S.mode, webhook=S.webhook,
                alert_scope=S.alert_scope)


class SimRequest(BaseModel):
    attack: str = Field(pattern="^(Normal|Additive|Scaling|Coordinated)$")
    buses: list[int] = []
    size_pct: float = Field(default=2.0, ge=0.05, le=10)
    direction: int = Field(default=1)
    seed: int | None = None


@app.post("/api/simulate")
async def simulate(req: SimRequest):
    buses = sorted({b for b in req.buses if 2 <= b <= 14})
    if req.attack != "Normal" and not buses:
        raise HTTPException(400, "choose at least one bus (2–14)")
    seed = req.seed if req.seed is not None else random.randrange(1_000_000)
    row = await asyncio.to_thread(make_snapshot, PIPE.cfg, PIPE.raw_cols, req.attack, buses, req.size_pct,
                                  1 if req.direction >= 0 else -1, seed)
    ev = await asyncio.to_thread(_record, row, "simulator", None,
                                 dict(simulation=dict(attack=req.attack, buses=buses, size_pct=req.size_pct,
                                                      direction=1 if req.direction >= 0 else -1, seed=seed)))
    await _broadcast(dict(type="event", event=ev, alarm=S.alarms.get(ev["id"]), stats=S.stats))
    return dict(event=ev, alarm=S.alarms.get(ev["id"]))


class ScoreRequest(BaseModel):
    snapshot: dict | list


@app.post("/api/score")
async def score_snapshot(req: ScoreRequest):
    """Score a snapshot supplied from outside (e.g. an uploaded CSV row). It is validated first;
    an invalid snapshot is rejected with HTTP 422 and the list of problems. Ground truth is unknown here."""
    try:
        df = validate_payload(req.snapshot)
    except InvalidSnapshot as e:
        raise HTTPException(422, dict(message="Snapshot rejected — not scored.", errors=e.errors))
    if len(df) != 1:
        raise HTTPException(422, dict(message="Send one snapshot at a time.", errors=[f"got {len(df)} rows"]))
    ev = await asyncio.to_thread(_record, df, "upload", None, None, False)
    await _broadcast(dict(type="event", event=ev, alarm=S.alarms.get(ev["id"]), stats=S.stats))
    return dict(event=ev, alarm=S.alarms.get(ev["id"]))


@app.get("/api/reference")
def reference():
    """What the inputs must look like, and the normal reference used by the measurement table."""
    return dict(measurement_columns=MEAS_COLS, ignored_columns=GROUND_TRUTH_COLS,
                sanity_limits={k: dict(low=v[0], high=v[1], unit=v[2]) for k, v in LIMITS.items()},
                normal_reference_source=(PIPE.normal_ref or {}).get("source"))


@app.get("/api/sample.csv", response_class=PlainTextResponse)
def sample_csv(i: int = 0):
    """One test-set row with only the 84 measurement columns — a ready-made file for the Upload tab."""
    if not 0 <= i < len(TEST):
        raise HTTPException(404, "no such test snapshot")
    return PlainTextResponse(TEST.iloc[[i]][MEAS_COLS].to_csv(index=False), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=griddefense_snapshot_{i}.csv"})


@app.get("/api/verification")
def verification():
    return dict(check=CHECK, provenance=PROV, manifest=MANIFEST, integrity=INTEGRITY)


@app.get("/api/scenarios")
def scenarios():
    return SCENARIOS


@app.post("/api/scenarios/{sid}/run")
async def run_scenario(sid: str):
    sc = SCENARIO_BY_ID.get(sid)
    if sc is None:
        raise HTTPException(404, "unknown scenario")
    row = await asyncio.to_thread(make_snapshot, PIPE.cfg, PIPE.raw_cols, sc["attack"], sc["buses"],
                                  max(sc["size_pct"], 0.05), sc["direction"], sc["seed"])
    ev = await asyncio.to_thread(_record, row, "scenario", None, dict(
        scenario=dict(id=sc["id"], title=sc["title"]),
        simulation=dict(attack=sc["attack"], buses=sc["buses"], size_pct=sc["size_pct"],
                        direction=sc["direction"], seed=sc["seed"])))
    await _broadcast(dict(type="event", event=ev, alarm=S.alarms.get(ev["id"]), stats=S.stats))
    return dict(event=ev, alarm=S.alarms.get(ev["id"]))


@app.post("/api/reset")
async def reset_demo():
    """Clear the active alarm list for the next demonstration (the event log is kept)."""
    with S.lock:
        for a in S.alarms.values():
            if a["status"] in ("new", "acknowledged", "escalated"):
                a["status"] = "cleared"
                a["notes"].append(dict(time=_now(), action="reset", note="demo reset"))
    await _broadcast(dict(type="reset"))
    return dict(ok=True)


@app.get("/api/export/events.csv", response_class=PlainTextResponse)
def export_events():
    return PlainTextResponse(STORE.export_csv(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=griddefense_events.csv"})


@app.get("/api/performance")
def performance():
    """The notebook's SAVED result files, copied unchanged into the bundle by the export cell.
    These are notebook results, not live console results. Files over 2,000 rows are listed but not sent."""
    import hashlib
    files = {}
    for p in sorted((BUNDLE / "results").glob("*")):
        if p.suffix not in (".json", ".csv"):
            continue
        meta = dict(file=p.name, md5=hashlib.md5(p.read_bytes()).hexdigest(),
                    source_md5=(MANIFEST.get("source_md5") or {}).get(f"results/{p.name}"))
        if p.suffix == ".json":
            files[p.stem] = dict(meta, kind="json", data=json.loads(p.read_text()))
        else:
            df = pd.read_csv(p)
            if len(df) > 2000:
                files[p.stem] = dict(meta, kind="csv", rows_total=len(df), columns=list(df.columns), rows=None)
            else:
                files[p.stem] = dict(meta, kind="csv", rows_total=len(df), columns=list(df.columns),
                                     rows=json.loads(df.to_json(orient="records")))
    return dict(provenance=PROV, bundle_id=BUNDLE_ID, exported_at=MANIFEST.get("exported_at_utc"), files=files)


@app.post("/api/webhook/test")
def webhook_test():
    if not S.webhook:
        raise HTTPException(400, "no webhook URL set")
    try:
        r = httpx.post(S.webhook, json=dict(event="griddefense.test", time=_now(),
                                            message="GridDefense test alert: the phone link works."), timeout=8)
        return dict(ok=r.is_success, code=r.status_code)
    except Exception as e:  # noqa: BLE001
        return dict(ok=False, error=str(e)[:200])


@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    S.clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        S.clients.discard(ws)


# ── Serve the built 3D app (frontend/dist) from the same address, so one window runs everything ──
_DIST = _ROOT.parent / "frontend" / "dist"
if (_DIST / "index.html").exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="app")
    print(f"[GridDefense] Console: http://localhost:8000  (serving {_DIST})")
