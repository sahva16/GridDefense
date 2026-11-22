# GridDefense — FDI detection console

An operator console for GridDefense, laid out like a control-room energy management system.
It runs the **trained** detection pipeline (Autoencoder + Random Forest + physics checks →
weighted fusion → bus localiser) on IEEE 14-bus snapshots. It shows every decision with its
evidence on a 3D network view.

**Simulation mode only:** the console never connects to, or sends commands to, a real grid.

| Area | What it shows |
|---|---|
| **Network view (3D)** | The IEEE 14-bus system: 14 selectable buses and the real 20 branches, with lattice towers and moving power-flow particles. Every bus shows its **measured voltage**. Rotate (drag), zoom (scroll), pan (right-drag). Click a bus to inspect it. |
| **Detection centre** | The decision on the shown snapshot: NORMAL/ALARM, fusion score against the threshold, each layer's score, weight and flag, attack-type probabilities, suspected buses (localiser), and physics evidence per bus |
| **Bus inspection** | Measured Vm, Va, P and Q; z-score and vote of each physics check; localiser probability; autoencoder error share; flows on connected lines |
| **Attack simulator** | 9 prepared scenarios (S0–S8) with fixed seeds, so the same scenario always gives the same result, plus a custom attack. **Reset** clears the alarm list for the next visitor. |
| **Alarm summary** | Newest first, priority 1–3, UNACK / ACK / CLR states, Ack and Ack all. Click a row to show that event. |
| **Event history & replay** | Fusion score of recent snapshots against the threshold. Click any point, or use ⏮ ◀ ▶ ▶❘, to put a past event back on the grid. **LIVE** returns to the feed. |
| **Measurements** | Voltage profile, line flows (\|S\| from the measured voltages), and each detector's history |

## Start (one window)

Install **Python 3.12** from python.org once. On Windows, tick *Add python.exe to PATH*.

| Windows | macOS / Linux |
|---|---|
| double-click `START_GridDefense_Windows.bat` | run `./START_GridDefense_Mac_Linux.sh` |

The first start installs the Python packages (about 5 minutes, needs internet). After that it
starts in seconds and works offline. The console opens at **http://localhost:8000**. Keep the
black window open; closing it stops GridDefense. Use Chrome or Edge and press **F11** for full
screen.

## Put the notebook's models in (required)

The console has **no built-in models and no fallback**. Without a bundle it refuses to start and
says what to do.

1. In Colab, run notebook cells **1, 2 and 3** only (imports, Drive, CONFIG).
2. Paste `notebook/export_bundle_cell.py` into a new cell and run it. It loads the files the
   notebook already saved on Drive; nothing is retrained. It must print three ✓ lines.
3. Download `MyDrive/GridDefense/app_bundle` and put its contents in `backend/bundle/`
   (or set `GRIDDEFENSE_BUNDLE=/path/to/app_bundle`).
4. Start the console.

On start the backend scores **all 11,000** independent-test snapshots and compares them with the
notebook's own `results/alarm_log.csv` (alarm, named buses, attack type, and all four scores to the
3 decimals the log stores). The top bar then shows one of:

| Badge | Meaning |
|---|---|
| **Notebook models · verified** | exported by the notebook, files unchanged since export (SHA-256), and every comparison passed |
| **DEVELOPMENT models** (amber banner) | a bundle made from the repo package for testing — not the notebook's |
| **Models NOT verified** (red banner) | no manifest, a changed file, a version mismatch, or a failed comparison — the reason is listed |

Click the badge for the full provenance panel (checks, fingerprints, versions, thresholds,
feature lists). Set `GRIDDEFENSE_STRICT=1` to refuse to start unless verified.

scikit-learn is pinned to 1.6.1, the version used in Colab.

## Tests

```bash
cd backend
GRIDDEFENSE_BUNDLE=/path/to/app_bundle python -m pytest -q tests
```

22 tests: notebook reproduction on all test snapshots, ground-truth separation (outputs unchanged
when Label / Attack_Type / bus_label columns are removed or scrambled), input validation, normal /
attack / borderline cases, missing and tampered bundles, and bundle-ID tracking.
`tools/simulator_sanity_check.py` compares the attack simulator's alarm rates with the notebook's.

## Event log

Every scored snapshot is written to `backend/data/events.db` (SQLite) in two separate tables:

- `events`: time, **model bundle ID**, source, scenario, all scores, the decision, named buses and the full result
- `ground_truth`: what was really injected (type, buses, size, seed). It is kept apart to make
  clear the models never receive it.

**Export event log (CSV)** in the simulator panel downloads both tables joined. Operator
actions (Ack, reset) are stored in `operator_actions`. Delete `backend/data/events.db` to start
with an empty log.

## Alarm tone and phone alerts

- A new alarm plays a short three-beep annunciator tone (two groups for priority 1). The
  speaker button mutes it.
- Phone alerts go through **n8n**: import `n8n/griddefense_phone_alert.json`, put your ntfy
  topic in the HTTP node, and publish the workflow. Then paste the webhook's production URL in
  **⚙ Settings → Phone alerts** and press **Test**.
  - By default only simulated attacks are sent; this can be changed in Settings.
  - Step-by-step setup (phone, n8n, console) and troubleshooting: `n8n/README.md`.
  - The console → webhook step is covered by an automated test. The n8n → ntfy → phone hop
    has to be tested once on your own network.

## Inspecting a decision

- **Details** (network view) opens five tabs for the shown snapshot: *Why* (plain-language
  explanation built by fixed rules from the snapshot's numbers — no language model), *Measurements*
  (Vm, Va, Pd, Qd observed vs the normal reference from the 5,000 development normals),
  *Physics map* (14 buses × 4 checks coloured by z-score against the 3.5 limit), *Localisation*
  (actual vs named buses: correct / missed / extra, exact yes/no — only where the truth is known)
  and *Compare* (side by side with any other event, or with the same snapshot re-simulated
  without the attack).
- **Large view**, **+ / −**, **Top** and **Reset** control the 3D network.
- **Upload** (attack simulator) scores your own one-row CSV after validating every value.
- **Research results** (top bar) shows only the notebook's saved result files, labelled
  "notebook results, not live", each with its MD5 fingerprint.

## Settings (⚙)

- **Live feed:** *Normal snapshots only* (default, for demos), *Realistic mix*, *Test set as
  it is*, or *Paused*. The live feed replays the notebook's independent test set.
- **Phone alerts:** which alarms go to n8n.
- Model check details.

## What is real and what is simulated

| Part | What it is |
|---|---|
| Scores, decisions, attack type, named buses, physics evidence | **Real**: the trained models, scoring each snapshot live |
| Scenario and custom attacks | A new AC power flow (PYPOWER) with false readings and the notebook's meter noise |
| Live feed | The notebook's independent test set |
| 3D network | The real IEEE 14-bus topology. Positions follow the usual one-line diagram; towers are illustrative. |
| Ground truth | Shown for the demo (toggle *Show ground truth*). Never given to the models. |

## Preview without Python

`frontend/dist-preview/index.html` replays results recorded from the backend
(`tools/record_preview.py`). It shows the design anywhere, but it does not run the models live.

## Folder layout

```
START_GridDefense_*            one-click start
backend/app/main.py            API, live feed, alarms, scenarios, reset, export, n8n webhook, serves the console
backend/app/pipeline.py        the notebook's detection pipeline (nothing is trained here)
backend/app/simulator.py       power flow + attack + meter noise
backend/app/scenarios.py       the 9 prepared scenarios (edit to add your own)
backend/app/store.py           SQLite event log (events / ground_truth / operator_actions)
backend/app/bundle.py          bundle loading, full notebook verification, provenance status
backend/app/validate.py        input validation (84 measurement columns, sanity limits)
backend/app/explain.py         rule-based alarm explanations
backend/tests/                 automated tests
notebook/export_bundle_cell.py standalone export cell (run after notebook cells 1–3)
frontend/src/scene/Network3D.tsx   3D network view
frontend/src/ui/                   console panels
```

To change the frontend you need Node.js LTS. Edit, then run `npm run build` in `frontend`.
