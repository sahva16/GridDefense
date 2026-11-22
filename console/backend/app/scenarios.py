"""
Prepared demonstration scenarios. Each one has a fixed random seed, so running it again
gives the same operating point, the same meter noise and therefore the same result.
"""

SCENARIOS = [
    dict(id="S0", title="Normal operation", attack="Normal", buses=[], size_pct=0.0, direction=1, seed=1101,
         note="A clean snapshot. GridDefense should stay quiet."),
    dict(id="S1", title="Voltage + angle bias at the central substation", attack="Additive", buses=[4], size_pct=2.0, direction=1, seed=1201,
         note="Additive attack, 2% at bus 4 (132 kV hub, 5 lines)."),
    dict(id="S2", title="Voltage scaling at the city substation", attack="Scaling", buses=[9], size_pct=1.5, direction=-1, seed=1301,
         note="Scaling attack, −1.5% on the voltage reading at bus 9 (capacitor bank)."),
    dict(id="S3", title="Coordinated attack, city and industrial park", attack="Coordinated", buses=[9, 14], size_pct=2.0, direction=1, seed=1401,
         note="The same bias at two connected buses, so they agree with each other."),
    dict(id="S4", title="Coordinated attack on the northern 33 kV area", attack="Coordinated", buses=[6, 11, 12], size_pct=1.0, direction=-1, seed=1501,
         note="Three neighbouring buses, 1% each."),
    dict(id="S5", title="Multi-site additive attack", attack="Additive", buses=[2, 7, 13], size_pct=2.0, direction=1, seed=1601,
         note="Three buses far apart, 2% each."),
    dict(id="S6", title="Small bias at the harbour", attack="Additive", buses=[13], size_pct=1.0, direction=-1, seed=1701,
         note="1% — the lower end of the trained range."),
    dict(id="S7", title="Stealth test: very small bias", attack="Additive", buses=[10], size_pct=0.5, direction=1, seed=1801,
         note="0.5% — below the trained range. Expected to be hard to detect."),
    dict(id="S8", title="Stealth test: tiny scaling", attack="Scaling", buses=[5], size_pct=0.25, direction=1, seed=1901,
         note="0.25% — close to the meter noise. Shows the system's limit."),
]
BY_ID = {s["id"]: s for s in SCENARIOS}
