"""
Task 7: what-if. Before changing the network, the twin predicts the effect of the change; then the change is
"applied" and the result compared.
"Actual" is not a measurement from a real network: it is the same change simulated again on the same
ray-traced channel, with random 4 dB shadowing added to every UE-sector link, a fresh draw the twin never sees.
Scenarios: now, 2x UEs, site B off, UEs moved ~30 m. The Twin strategy is used in all of them.
Run after task 2:  python tasks/task7_whatif.py   (--quick for the quick data)
"""
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from twin import scene as sc
from twin import radio
from twin.allocation import run
from twin.twin_data import save_demo_part

SHADOWING_DB = 4.0
WHAT_ACTUAL_IS = ('"Actual" is not a measurement from a real network: it is the same change simulated again on the '
                  f'same ray-traced channel, with random {SHADOWING_DB:.0f} dB shadowing added to every UE-sector link, '
                  'a fresh draw the twin never sees.')
RAYS = 200_000 if sc.quick() else sc.RAYS_PER_SECTOR
data, results = sc.folders()
m = np.load(data / "measurements.npz")
xy, pg = m["ue_xy"], m["path_gain_db"]
site_b_off = np.array([not name.startswith("B") for name in m["sectors"]])

# 1. the extra positions the scenarios need: as many new UEs again, and every UE moved ~30 m (traced once, then cached)
extra = data / "whatif.npz"
if not extra.exists():
    scene = sc.load()
    rng = np.random.default_rng(2)
    new_xy = sc.random_ue_positions(scene, len(xy), rng)
    moved = []
    for x, y in xy:                                                   # try directions until the new spot is outdoors
        for angle in rng.uniform(0, 2 * np.pi, 20):
            p = [x + 30 * np.cos(angle), y + 30 * np.sin(angle)]
            if sc.outdoor(scene, p)[0]:
                break
        moved.append(p)
    moved = np.array(moved)
    np.savez(extra, new_xy=new_xy, new_pg=sc.trace(scene, new_xy, RAYS)[0],
             moved_xy=moved, moved_pg=sc.trace(scene, moved, RAYS)[0])
e = np.load(extra)

scenarios = {
    "now": (xy, pg, None),
    "2x UEs": (np.r_[xy, e["new_xy"]], np.r_[pg, e["new_pg"]], None),
    "site B off": (xy, pg, site_b_off),
    "UEs moved ~30 m": (e["moved_xy"], e["moved_pg"], None),
}

# 2. for each scenario: the twin's prediction, then the "actual" result with fresh shadowing
rows, cases = [], {}
for i, (name, (ue_xy, gain_db, active)) in enumerate(scenarios.items()):
    plan = run("Twin", radio.prb_power_mw(gain_db), ue_xy, active)
    predicted = radio.kpis(plan)
    shadow = np.random.default_rng(100 + i).normal(0, SHADOWING_DB, gain_db.shape)
    actual = radio.kpis(run("Twin", radio.prb_power_mw(gain_db + shadow), ue_xy, active))
    for k in ["mean throughput (Mbps)", "5th-percentile throughput (Mbps)", "mean SINR (dB)"]:
        rows.append([name, k, round(predicted[k], 2), round(actual[k], 2), round(predicted[k] - actual[k], 2)])
    # for the demo's What-if tab: where the UEs are, who serves them, and predicted / actual
    cases[name] = {"ue_xy": np.round(ue_xy, 1).tolist(), "serving": plan["serving"].tolist(),
                   "active": (np.ones(len(m["sectors"]), bool) if active is None else active).tolist(),
                   "predicted": {k: round(v, 2) for k, v in predicted.items()},
                   "actual": {k: round(v, 2) for k, v in actual.items()}}

# 3. the table: printed, and saved as CSV
print(WHAT_ACTUAL_IS)
print(f"{'scenario':18s}{'metric':36s}{'predicted':>10s}{'actual':>10s}{'error':>8s}")
for r in rows:
    print(f"{r[0]:18s}{r[1]:36s}{r[2]:10.1f}{r[3]:10.1f}{r[4]:8.1f}")
with open(results / "task7_whatif.csv", "w", newline="") as f:
    csv.writer(f).writerows([["scenario", "metric", "predicted", "actual", "error"]] + rows)
print(f"saved {results / 'task7_whatif.csv'}")
if not sc.quick():                                                   # the demo's What-if tab
    save_demo_part("whatif", {"cases": cases, "shadowing_db": SHADOWING_DB, "what_actual_is": WHAT_ACTUAL_IS})
    print("saved the What-if tab's data in data/demo_tasks.json")
