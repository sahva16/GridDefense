"""
Local event log (SQLite, backend/data/events.db).

Two separate tables:
  events        — what GridDefense saw and decided (time, source, scores, prediction, full result)
  ground_truth  — what was really injected (only known in simulation). Kept apart so that it is
                  clear the models never receive it; it is joined in only for display and export.
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import threading
from pathlib import Path


class EventStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, time TEXT, source TEXT, scenario_id TEXT, snapshot INTEGER,
                alarm INTEGER, fusion_score REAL, threshold REAL, ae_score REAL, rf_score REAL, physics_score REAL,
                attack_type TEXT, named_buses TEXT, result TEXT);
            CREATE TABLE IF NOT EXISTS ground_truth (
                event_id INTEGER PRIMARY KEY REFERENCES events(id), attack_type TEXT, buses TEXT,
                size_pct REAL, direction INTEGER, seed INTEGER);
            CREATE TABLE IF NOT EXISTS operator_actions (
                alarm_id INTEGER, time TEXT, action TEXT, note TEXT);
            """)
            cols = {r[1] for r in self.db.execute("PRAGMA table_info(events)")}
            if "bundle_id" not in cols:   # older logs: rows written before tracking keep NULL = "not recorded"
                self.db.execute("ALTER TABLE events ADD COLUMN bundle_id TEXT")
            self.db.commit()

    def max_id(self) -> int:
        with self.lock:
            r = self.db.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()
        return int(r[0])

    def add(self, ev: dict):
        r = ev["result"]
        sim = ev.get("simulation") or {}
        with self.lock:
            self.db.execute(
                "INSERT INTO events (id, time, source, scenario_id, snapshot, alarm, fusion_score, threshold, ae_score, "
                "rf_score, physics_score, attack_type, named_buses, result, bundle_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ev["id"], ev["time"], ev["source"], (ev.get("scenario") or {}).get("id"), ev.get("snapshot"),
                 int(r["alarm"]), r["fusion"]["score"], r["fusion"]["threshold"], r["detectors"]["ae"]["score"],
                 r["detectors"]["rf"]["score"], r["detectors"]["physics"]["score"], r["attack_type"],
                 json.dumps(r["named_buses"]), json.dumps({k: v for k, v in ev.items() if k not in ("truth", "verdict")}, default=float),
                 ev.get("bundle_id")))
            if not ev.get("truth_known", True):
                self.db.commit()
                return
            self.db.execute(
                "INSERT INTO ground_truth VALUES (?,?,?,?,?,?)",
                (ev["id"], ev["truth"]["type"], json.dumps(ev["truth"]["buses"]),
                 sim.get("size_pct"), sim.get("direction"), sim.get("seed")))
            self.db.commit()

    def action(self, alarm_id: int, time: str, action: str, note: str):
        with self.lock:
            self.db.execute("INSERT INTO operator_actions VALUES (?,?,?,?)", (alarm_id, time, action, note))
            self.db.commit()

    def recent(self, limit: int) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                "SELECT e.result, g.attack_type, g.buses FROM events e LEFT JOIN ground_truth g ON g.event_id = e.id "
                "ORDER BY e.id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for res, t, b in rows:
            ev = json.loads(res)
            ev["truth"] = dict(type=t, buses=json.loads(b) if b else [])
            ev["truth_known"] = t is not None
            out.append(ev)
        return out

    def count(self) -> int:
        with self.lock:
            return int(self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def export_csv(self) -> str:
        with self.lock:
            rows = self.db.execute(
                "SELECT e.id, e.time, e.bundle_id, e.source, e.scenario_id, e.snapshot, e.alarm, e.fusion_score, e.threshold, "
                "e.ae_score, e.rf_score, e.physics_score, e.attack_type, e.named_buses, "
                "g.attack_type, g.buses, g.size_pct, g.direction, g.seed "
                "FROM events e LEFT JOIN ground_truth g ON g.event_id = e.id ORDER BY e.id").fetchall()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["event_id", "time", "bundle_id", "source", "scenario_id", "test_snapshot", "alarm", "fusion_score", "threshold",
                    "ae_score", "rf_score", "physics_score", "predicted_type", "named_buses",
                    "true_type", "true_buses", "true_size_pct", "true_direction", "seed"])
        w.writerows(rows)
        return buf.getvalue()
