"""
Task 5: mobility. A UE walks each of the three routes (66 points, 2 m apart; the paths come from data/twin.json).
  1. The routes are ray-traced with the current code: RSRP and line of sight of every sector at every step.
     The full study also writes them into data/twin.json, so the demo (twin.html) uses the same route data.
  2. The serving sector follows the A3 rule of the demo (another sector > 3 dB stronger for 2 steps in a row).
  3. At every step the walking UE's throughput is worked out for B1 and for the Twin, with the UEs of task 2's
     first 10 placements as the other users. The walker is treated like every other UE (a random place in the
     UE list, the same PRB rules), and the results are averaged over the 10 placements.
Run after task 2:  python tasks/task5_mobility.py   (--quick for the quick data)
"""
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from twin import scene as sc
from twin import radio
from twin.allocation import run, nearest_sector, strongest_sector
from twin.twin_data import get_twin, save_routes

RAYS = 200_000 if sc.quick() else sc.RAYS_PER_SECTOR
data, results = sc.folders()
sectors = sc.sector_names()
routes = get_twin()["routes"]


def a3(rsrp):
    """Serving sector at each step, and the steps where a handover happens."""
    serving, candidate, count = int(np.argmax(rsrp[0])), None, 0     # start on the strongest sector
    path, handovers = [serving], []
    for k in range(1, len(rsrp)):
        best = int(np.argmax(rsrp[k]))
        if best != serving and rsrp[k, best] > rsrp[k, serving] + config.A3_OFFSET_DB:
            count = count + 1 if best == candidate else 1             # stronger again: count it
            candidate = best
        else:
            count, candidate = 0, None
        if count >= config.A3_STEPS:                                  # stronger for 2 steps: hand over
            handovers.append((k, sectors[serving], sectors[best]))
            serving, candidate, count = best, None, 0
        path.append(serving)
    return np.array(path), handovers


def describe(handovers):
    return ", ".join(f"{a}->{b} at {k * config.STEP_M:.0f} m" for k, a, b in handovers) or "no handover"


# 1. ray-trace the route points with the current code (once, then kept in data/)
cache = data / "routes.npz"
if not cache.exists() or "los" not in np.load(cache):
    scene = sc.load()
    traced = [sc.trace(scene, np.array(r["points"]), RAYS) for r in routes]      # (path gain, line of sight)
    np.savez(cache, path_gain_db=np.array([t[0] for t in traced]), los=np.array([t[1] for t in traced]))
route_gain_db = np.load(cache)["path_gain_db"]                       # [route, step, sector]
route_los = np.load(cache)["los"]
if not sc.quick():                                                   # the demo uses the full study's routes
    save_routes(radio.rsrp_dbm(route_gain_db), route_los)

# 2. the other users: task 2's placements (drops) 1-10. In each placement the walker gets one random position in
#    the UE list, kept for the whole walk, so it is treated exactly like every other UE by the PRB rules.
PLACEMENTS = 10
T_95 = 2.262                                                         # Student t, 95 %, 10 - 1 degrees of freedom
first, more = np.load(data / "measurements.npz"), np.load(data / "drops.npz")
placements = [(first["ue_xy"], first["path_gain_db"])] + list(zip(more["ue_xy"], more["path_gain_db"]))
placements = placements[:PLACEMENTS]
active = np.ones(len(sectors), bool)

rows, summary = [], []
fig, axes = plt.subplots(3, 2, figsize=(14, 10), sharex=True)
for r, route in enumerate(routes):
    rsrp = radio.rsrp_dbm(route_gain_db[r])                          # [step, sector], dBm
    twin_serving, handovers = a3(rsrp)
    print(f"route {route['id']}: {describe(handovers)}")

    # 3. the walker's throughput at every step, for B1 and the Twin, in every placement
    thr = {"B1": np.zeros((PLACEMENTS, len(rsrp))), "Twin": np.zeros((PLACEMENTS, len(rsrp)))}
    for p, (others_xy, others_gain) in enumerate(placements):
        others_rx = radio.prb_power_mw(others_gain)
        others_twin = strongest_sector(others_rx, active)            # whom the twin serves the others from
        w = np.random.default_rng(p).integers(0, len(others_xy) + 1)  # the walker's place in the UE list
        for k, point in enumerate(route["points"]):
            rx = np.insert(others_rx, w, radio.prb_power_mw(route_gain_db[r, k]), axis=0)
            xy = np.insert(others_xy, w, point, axis=0)
            thr["B1"][p, k] = run("B1", rx, xy)["throughput_mbps"][w]                      # nearest site, fixed PRBs
            serving = np.insert(others_twin, w, twin_serving[k])                         # walker: the A3 sector
            thr["Twin"][p, k] = run("Twin", rx, xy, serving=serving)["throughput_mbps"][w]

    # 4. the result per route: mean over steps and placements (± 95 % interval over placements), and 0 Mbps steps
    line = [route["id"]]
    for name in ["B1", "Twin"]:
        per_placement = thr[name].mean(axis=1)                       # each placement's mean along the route
        mean, ci = per_placement.mean(), T_95 * per_placement.std(ddof=1) / np.sqrt(PLACEMENTS)
        zero = 100 * (thr[name] == 0).mean()
        line += [round(mean, 2), round(ci, 2), round(zero, 1)]
        print(f"         {name:4s}: walker {mean:5.1f} ± {ci:.1f} Mbps along the route, at 0 Mbps on {zero:4.1f} % of steps")
    summary.append(line)
    for k in range(len(rsrp)):
        rows.append([route["id"], k, k * config.STEP_M, sectors[nearest_sector(np.array([route["points"][k]]), active)[0]],
                     sectors[twin_serving[k]], round(thr["B1"][:, k].mean(), 2), round(thr["Twin"][:, k].mean(), 2)])

    # 5. plots: left, RSRP of each sector (thick = serving); right, the walker's throughput (mean of placements)
    distance = np.arange(len(rsrp)) * config.STEP_M
    left, right = axes[r]
    for s, name in enumerate(sectors):
        line_, = left.plot(distance, rsrp[:, s], lw=0.8, alpha=0.6, label=name)
        left.plot(distance, np.where(twin_serving == s, rsrp[:, s], np.nan), lw=3, color=line_.get_color())
    right.plot(distance, thr["B1"].mean(axis=0), color="#9ca3af", lw=2, label="B1")
    right.plot(distance, thr["Twin"].mean(axis=0), color="#2563eb", lw=2, label="Twin")
    for k, a, b in handovers:
        for ax in (left, right):
            ax.axvline(k * config.STEP_M, color="k", ls=":")
        left.text(k * config.STEP_M, -62, f" {a}→{b}", fontsize=8, va="top")
    left.set_ylim(-150, -60)
    left.set_ylabel("RSRP (dBm)")
    left.set_title(f"Route {route['id']}: RSRP, thick = serving sector, dotted = handover", loc="left", fontsize=10)
    right.set_ylabel("walking UE (Mbps)")
    right.set_title(f"Route {route['id']}: walker's throughput, mean of {PLACEMENTS} placements of the other UEs",
                    loc="left", fontsize=10)
axes[0, 0].legend(ncol=9, fontsize=7, loc="lower left")
axes[0, 1].legend()
for ax in axes[-1]:
    ax.set_xlabel("distance walked (m)")
fig.tight_layout()
fig.savefig(results / "task5_routes.png", dpi=130)
with open(results / "task5_routes.csv", "w", newline="") as f:
    csv.writer(f).writerows([["route", "step", "distance_m", "b1_sector", "twin_sector", "b1_mbps_mean", "twin_mbps_mean"]] + rows)
with open(results / "task5_summary.csv", "w", newline="") as f:
    csv.writer(f).writerows([["route", "b1_mean_mbps", "b1_ci95", "b1_zero_pct", "twin_mean_mbps", "twin_ci95", "twin_zero_pct"]]
                            + summary)
print(f"saved task5_routes.png, task5_routes.csv and task5_summary.csv in {results}")
