"""
Plain-language "why was this alarm raised?" — built from fixed rules, not from a language model.

Every sentence is filled in from numbers the pipeline already computed for this snapshot
(fusion parts, detector scores, physics z-scores, localiser probabilities). Nothing is
guessed, and the text always ends by saying this is model evidence, not proof.
"""
from __future__ import annotations

PLAIN_CHECK = {
    "P_res": "real-power balance (power flowing in vs out of the bus)",
    "Q_res": "reactive-power balance",
    "Va_neighbor": "voltage angle compared with neighbouring buses",
    "Vm_neighbor": "voltage magnitude compared with neighbouring buses",
    "S_loading": "line loading",
}
BORDERLINE = 0.05   # |fusion − threshold| below this is called "close to the threshold" (dashboard wording only)


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def explain_text(res: dict, z_limit: float, votes_needed: int, n_checks: int, loc_threshold: float,
                 ae_threshold: float) -> dict:
    f = res["fusion"]
    d = res["detectors"]
    score, thr = f["score"], f["threshold"]
    w, parts = f["weights"], f["parts"]
    lines: list[str] = []

    # 1 — the decision
    if res["alarm"]:
        head = f"Alarm: the combined (fusion) score {score:.3f} is at or above the alarm threshold {thr:.2f}."
    else:
        head = f"No alarm: the combined (fusion) score {score:.3f} is below the alarm threshold {thr:.2f}."
    if abs(score - thr) < BORDERLINE:
        head += f" This is a borderline case — only {abs(score - thr):.3f} from the threshold."
    lines.append(head)

    # 2 — how the score is made up, largest part first
    order = sorted([("Random Forest", "rf"), ("Autoencoder", "ae"), ("Physics layer", "physics")],
                   key=lambda t: -parts[t[1]])
    lines.append("Score = " + " + ".join(f"{name} {parts[k]:.3f} ({w[k]:.2f} × {d[k]['score']:.3f})"
                                         for name, k in order) + ".")

    # 3 — each detector in one sentence
    probs = res.get("type_probabilities", {})
    p_normal = probs.get("Normal")
    best = max(((t, p) for t, p in probs.items() if t != "Normal"), key=lambda t: t[1], default=None)
    rf_line = "Random Forest: "
    if p_normal is not None:
        rf_line += f"probability {_pct(1 - p_normal)} that the snapshot is not Normal"
        if best:
            rf_line += f"; most likely attack type {best[0]} ({_pct(best[1])})"
    lines.append(rf_line + ".")
    err = d["ae"]["error"]
    lines.append(f"Autoencoder: reconstruction error {err:.5f}, "
                 + ("above" if err > ae_threshold else "below")
                 + f" its own alarm level {ae_threshold:.5f} — the snapshot looks "
                 + ("unlike" if err > ae_threshold else "like") + " the normal training data.")

    flagged = [b for b in res["buses"] if b["physics_alarm"]]
    if flagged:
        fl = sorted(flagged, key=lambda b: (-b["votes"], b["bus"]))
        top_bus, top_check = max(((b, c) for b in fl for c in b["checks_failed"] if c in b["z"]),
                                 key=lambda t: t[0]["z"][t[1]])
        lines.append(f"Physics layer: {len(fl)} bus{'es' if len(fl) > 1 else ''} had {votes_needed} or more of the "
                     f"{n_checks} checks above z = {z_limit:g} — "
                     + ", ".join(f"bus {b['bus']} ({b['votes']})" for b in fl)
                     + f". Strongest: {PLAIN_CHECK.get(top_check, top_check)} at bus {top_bus['bus']} "
                       f"(z = {top_bus['z'][top_check]:.1f}).")
        if len(fl) > 1:
            lines.append("Physics checks often also fire at buses connected to an attacked bus, because one wrong "
                         "reading changes the power balance and the neighbour comparisons of the buses around it. "
                         "Which buses were attacked is decided by the localiser, not by this list.")
    else:
        top = max(res["buses"], key=lambda b: max(b["z"].values()) if b["z"] else 0)
        zmax = max(top["z"].values()) if top["z"] else 0.0
        lines.append(f"Physics layer: no bus had {votes_needed} or more checks above z = {z_limit:g} "
                     f"(largest single z-score: {zmax:.1f} at bus {top['bus']}).")

    # 4 — localisation
    if res["alarm"]:
        named = [b for b in res["buses"] if b["named"]]
        if named:
            lines.append("Localiser names " + ", ".join(f"bus {b['bus']} (probability {b['loc_probability']:.2f})"
                                                       for b in named)
                         + f" — each at or above its threshold {loc_threshold:.2f}.")
        else:
            lines.append(f"Localiser: no bus reached its threshold {loc_threshold:.2f}, so no bus is named.")

    lines.append("This is evidence from the models, not proof of an attack. An operator should confirm it.")
    return dict(summary=lines[0], lines=lines, borderline=abs(score - thr) < BORDERLINE)
