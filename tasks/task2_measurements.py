"""
Task 2: the measurements. Ray-trace N random outdoor UE locations; for every UE and sector compute RSRP, SINR,
line of sight and path loss, and save them to data/. Then trace 19 more random placements of N UEs ("drops"),
used by tasks 5 and 6 to average over where the UEs happen to be (traced once, then kept in data/).
Run:  python tasks/task2_measurements.py   (--quick: 30 UEs and fewer rays)
"""
import csv
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from twin import scene as sc
from twin import radio

N_UES = 30 if sc.quick() else 100
RAYS = 200_000 if sc.quick() else sc.RAYS_PER_SECTOR
data, results = sc.folders()
sectors = sc.sector_names()

# 1. place N UEs outdoors at random, then ray-trace every sector -> every UE
scene = sc.load()
ue_xy = sc.random_ue_positions(scene, N_UES, np.random.default_rng(1))
start = time.time()
path_gain_db, los = sc.trace(scene, ue_xy, RAYS)
print(f"ray-traced {N_UES} UEs x {len(sectors)} sectors in {time.time() - start:.1f} s")

# 2. per UE and sector: RSRP, path loss, and the SINR the UE would have if that sector served it
rsrp = radio.rsrp_dbm(path_gain_db)
path_loss = -path_gain_db                     # includes the antenna gains (often called coupling loss)
rx = radio.prb_power_mw(path_gain_db)          # power per PRB from each sector
sinr = radio.to_db(rx / (rx.sum(1, keepdims=True) - rx + radio.noise_mw()))      # every other sector interferes

# 3. save: the raw ray tracing for the next tasks, and a readable table
np.savez(data / "measurements.npz", ue_xy=ue_xy, path_gain_db=path_gain_db, los=los, sectors=sectors)
with open(results / "task2_measurements.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ue", "x_m", "y_m", "sector", "rsrp_dbm", "sinr_db", "line_of_sight", "path_loss_db"])
    for u in range(N_UES):
        for s, name in enumerate(sectors):
            w.writerow([u, round(ue_xy[u, 0], 1), round(ue_xy[u, 1], 1), name, round(rsrp[u, s], 1),
                        round(sinr[u, s], 1), bool(los[u, s]), round(path_loss[u, s], 1)])

# 4. a short summary
best = rsrp.argmax(1)
u = np.arange(N_UES)
print(f"links with line of sight: {100 * los.mean():.0f} %  (to the strongest sector: {100 * los[u, best].mean():.0f} %)")
print(f"RSRP of the strongest sector: median {np.median(rsrp[u, best]):.1f} dBm, "
      f"range {rsrp[u, best].min():.1f} to {rsrp[u, best].max():.1f} dBm")
print(f"SINR at the strongest sector (all sectors on): median {np.median(sinr[u, best]):.1f} dB")
print(f"saved {data / 'measurements.npz'} and {results / 'task2_measurements.csv'}")

# 5. 19 more placements of the same number of UEs (drops 2-20), for tasks 5 and 6
DROPS = 20
cache = data / "drops.npz"
if not cache.exists():
    start = time.time()
    xy, gains = [], []
    for d in range(2, DROPS + 1):
        positions = sc.random_ue_positions(scene, N_UES, np.random.default_rng(100 + d))
        xy.append(positions)
        gains.append(sc.trace(scene, positions, RAYS)[0])
    np.savez(cache, ue_xy=np.array(xy), path_gain_db=np.array(gains))
    print(f"ray-traced drops 2-{DROPS} ({DROPS - 1} x {N_UES} UEs) in {time.time() - start:.0f} s")
print(f"saved {cache}")
