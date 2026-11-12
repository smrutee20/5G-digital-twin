"""
Task 4: the twin strategy. It uses the ray-traced channel twice:
  1. who serves each UE: the sector that is strongest at the UE (not simply the nearest site's sector);
  2. which PRBs: sectors that interfere strongly with each other (estimated from the ray tracing) get
     different PRBs.
Each UE needs 12 PRBs, so sectors are only partly loaded and the choice of PRBs matters.
Run after task 2:  python tasks/task4_twin_allocation.py   (--quick for the quick data)
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from twin import scene as sc
from twin import radio
from twin.allocation import run, evaluate, nearest_sector, strongest_sector, fixed_prbs, coordinated_prbs

data, results = sc.folders()

# 1. the ray-traced measurements of task 2
m = np.load(data / "measurements.npz")
rx = radio.prb_power_mw(m["path_gain_db"])
rsrp = radio.rsrp_dbm(m["path_gain_db"])
active = np.ones(rx.shape[1], bool)
u = np.arange(len(rx))
S = rx.shape[1]

# 2. step 1, who serves each UE: how many UEs the twin moves to another sector, and how much signal they gain
nearest = nearest_sector(m["ue_xy"], active)
strongest = strongest_sector(rx, active)
moved = nearest != strongest
gain_db = np.median((rsrp[u, strongest] - rsrp[u, nearest])[moved])        # signal gain of the UEs that move
print(f"UEs the twin serves from another sector than the nearest site's: {moved.sum()} of {len(rx)}, "
      f"their signal {gain_db:.1f} dB stronger (median)")

# 3. what each step adds: B1, then step 1 alone, then step 2 alone, then both (the Twin)
steps = {
    "B1 (nearest site, fixed PRBs)": run("B1", rx, m["ue_xy"]),
    "step 1 only (strongest sector, fixed PRBs)": evaluate(fixed_prbs(strongest, S), rx, strongest),
    "step 2 only (nearest site, coordinated PRBs)": evaluate(coordinated_prbs(nearest, rx, S), rx, nearest),
    "Twin (both steps)": run("Twin", rx, m["ue_xy"]),
}
for name, result in steps.items():
    k = radio.kpis(result)
    print(f"{name:46s} mean {k['mean throughput (Mbps)']:5.1f} Mbps, 5th percentile "
          f"{k['5th-percentile throughput (Mbps)']:5.2f} Mbps, SINR {k['mean SINR (dB)']:5.1f} dB")

# 4. save for the report
out = radio.kpis(steps["Twin (both steps)"])
out["UEs moved to another sector"] = int(moved.sum())
out["each step, mean / 5th-percentile throughput (Mbps)"] = {
    name: [round(radio.kpis(r)["mean throughput (Mbps)"], 2), round(radio.kpis(r)["5th-percentile throughput (Mbps)"], 2)]
    for name, r in steps.items()}
(results / "task4_twin.json").write_text(json.dumps(out, indent=2))
print(f"saved {results / 'task4_twin.json'}")
