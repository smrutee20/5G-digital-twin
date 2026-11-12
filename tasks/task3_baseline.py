"""
Task 3: the baselines, which do not use the twin.
  B1 = nearest site (sector pointing at the UE) + fixed PRBs (a block of 12 per UE, counted from PRB 0 in every
       sector, so neighbouring sectors always use the same PRBs)
  B2 = nearest site + random PRBs (12 per UE)
Run after task 2:  python tasks/task3_baseline.py   (--quick for the quick data)
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from twin import scene as sc
from twin import radio
from twin.allocation import run

data, results = sc.folders()

# 1. the ray-traced measurements of task 2: power per PRB from each sector at each UE
m = np.load(data / "measurements.npz")
rx = radio.prb_power_mw(m["path_gain_db"])

# 2. run both baselines and print their KPIs
out = {}
for name in ["B1", "B2"]:
    result = run(name, rx, m["ue_xy"], rng=np.random.default_rng(0))
    out[name] = radio.kpis(result)
    print(f"{name}: " + ", ".join(f"{k} {v:.1f}" for k, v in out[name].items()))

# 3. save for the report
(results / "task3_baselines.json").write_text(json.dumps(out, indent=2))
print(f"saved {results / 'task3_baselines.json'}")
