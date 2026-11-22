"""
Task 9: the corrected twin (scenes/iitgn_v2: buildings fixed from the IITGN drawings + trees) against the study's twin
(scenes/iitgn, v1). Before/after on the SAME UEs.

  1. re-trace task 2's 20 drops x 100 UEs (same positions) on v2, at the study's ray count, with vegetation loss
     -> data/study_v2/measurements.npz, drops.npz (the format task 6 reads)
  2. task 6 on v2 (B1 / B2 / Twin)                -> results/study_v2/task6_comparison.csv
  3. coverage maps of v1 and v2 (Sionna radio map, 1e6 rays, 5 m)
  4. the before/after table                       -> results/study_v2/before_after.csv and .md
  5. for the 3D view: v2 buildings, trees and RSRP map picture -> data/scene_v2.json

Run after task 2 and task 6 (v1):  python tasks/task9_scene_v2.py      (about 15 minutes on an M4)
Vegetation: per path in 1 (exact "option C", twin/vegetation.py); the coverage map cannot give per-path geometry, so
there each sector's map is reduced by the crown length on the straight line from the antenna to the cell (approximation).
All vegetation numbers depend on the TO-BE-CALIBRATED parameters in twin/vegetation.py.
"""
import base64
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["TWIN_SCENE"] = "v2"
import config                                            # noqa: E402
from twin import scene as sc, radio, vegetation          # noqa: E402

RAYS = sc.RAYS_PER_SECTOR
GRID_M = 5.0
THRESHOLD_DBM = -110.0
data_v1, data_v2 = ROOT / "data" / "study", ROOT / "data" / "study_v2"
res_v2 = ROOT / "results" / "study_v2"
data_v2.mkdir(parents=True, exist_ok=True); res_v2.mkdir(parents=True, exist_ok=True)

first = np.load(data_v1 / "measurements.npz"); more = np.load(data_v1 / "drops.npz")
drops_xy = [first["ue_xy"]] + list(more["ue_xy"])
gains_v1 = [first["path_gain_db"]] + list(more["path_gain_db"])
scenes = {k: sc.load(sc.SCENES[k]) for k in ("v1", "v2")}
trees = vegetation.load_trees(sc.SCENES["v2"])
ant = np.array([s["pos"] for s in config.sectors()], float)


def line_of_sight(scene, xy):
    import mitsuba as mi
    pts = np.c_[xy, np.full(len(xy), sc.UE_HEIGHT_M)]
    U, S = len(pts), len(ant)
    start = np.repeat(ant[None], U, 0).reshape(-1, 3).astype(np.float32)
    d = (np.repeat(pts[:, None], S, 1).reshape(-1, 3) - start).astype(np.float32)
    dist = np.linalg.norm(d, axis=1)
    ray = mi.Ray3f(mi.Point3f(*start.T), mi.Vector3f(*(d / dist[:, None]).T)); ray.maxt = mi.Float((dist - 0.2).astype(np.float32))
    return ~np.array(scene.mi_scene.ray_test(ray)).reshape(U, S)


def tree_free(xy):
    pts = np.c_[xy, np.full(len(xy), sc.UE_HEIGHT_M)]
    a = np.repeat(ant[None], len(pts), 0).reshape(-1, 3); b = np.repeat(pts[:, None], len(ant), 1).reshape(-1, 3)
    return (vegetation.length_in_crowns(a, b, trees) == 0).reshape(len(pts), len(ant))


# ---- 1. re-trace the drops on v2
cache = data_v2 / "drops.npz"
if cache.exists() and (data_v2 / "measurements.npz").exists():
    print("1. v2 traces: using the saved ones in data/study_v2 (delete them to re-trace)")
    m2 = np.load(data_v2 / "measurements.npz"); d2 = np.load(cache)
    gains_v2 = [m2["path_gain_db"]] + list(d2["path_gain_db"])
else:
    gains_v2 = []
    for i, xy in enumerate(drops_xy):
        gains_v2.append(sc.trace(scenes["v2"], xy, RAYS)[0])
        print(f"1. v2: traced drop {i + 1} of {len(drops_xy)}", flush=True)
    los0 = line_of_sight(scenes["v2"], drops_xy[0])
    np.savez(data_v2 / "measurements.npz", ue_xy=drops_xy[0], path_gain_db=gains_v2[0], los=los0, sectors=first["sectors"])
    np.savez(cache, ue_xy=np.array(drops_xy[1:]), path_gain_db=np.array(gains_v2[1:]))

# ---- 2. task 6 on v2
print("2. task 6 on v2:")
subprocess.run([sys.executable, str(ROOT / "tasks" / "task6_compare.py")], check=True, env={**os.environ, "TWIN_SCENE": "v2"})


# ---- 3. coverage maps (radio map, outdoor cells of each scene)
def coverage(key, bounds, rays=RAYS):
    import mitsuba as mi
    from sionna.rt import RadioMapSolver
    s = scenes[key]
    x0, x1, y0, y1 = bounds
    nx, ny = int(round((x1 - x0) / GRID_M)), int(round((y1 - y0) / GRID_M))
    rm = RadioMapSolver()(s, center=[(x0 + x1) / 2, (y0 + y1) / 2, sc.UE_HEIGHT_M], orientation=[0.0, 0.0, 0.0],
                          size=[nx * GRID_M, ny * GRID_M], cell_size=[GRID_M, GRID_M], samples_per_tx=int(rays),
                          max_depth=sc.MAX_BOUNCES, diffraction=sc.DIFFRACTION, edge_diffraction=sc.DIFFRACTION,
                          diffuse_reflection=False, refraction=False, seed=sc.SEED)
    pg = np.array(rm.path_gain)                                                     # [sector, ny, nx]
    X, Y = np.meshgrid(x0 + GRID_M * (np.arange(nx) + 0.5), y0 + GRID_M * (np.arange(ny) + 0.5))
    if key == "v2":                                                                 # straight-line crown loss
        cells = np.c_[X.ravel(), Y.ravel(), np.full(X.size, sc.UE_HEIGHT_M)]
        for t in range(len(ant)):
            L = vegetation.length_in_crowns(np.repeat(ant[t][None], len(cells), 0), cells, trees)
            pg[t] *= 10 ** (-vegetation.loss_db(L).reshape(ny, nx) / 10)
    rsrp = radio.rsrp_dbm(10 * np.log10(pg + 1e-30))
    outdoor = sc.outdoor(s, np.c_[X.ravel(), Y.ravel()]).reshape(ny, nx)
    return rsrp.max(0), outdoor


study_area = (*sc.AREA_X, *sc.AREA_Y)
cov = {k: coverage(k, study_area) for k in ("v1", "v2")}
print("3. coverage maps done")

# ---- 4. the table
def t6(path):
    rows = {r["metric"]: r for r in csv.DictReader(open(path))}
    return {k: {n: float(rows[k][f"{n} mean"]) for n in ("B1", "B2", "Twin")} for k in rows}


k6 = {"v1": t6(ROOT / "results" / "study" / "task6_comparison.csv"), "v2": t6(res_v2 / "task6_comparison.csv")}
all_xy = np.concatenate(drops_xy)
G = {"v1": np.concatenate(gains_v1), "v2": np.concatenate(gains_v2)}
los = {k: line_of_sight(scenes[k], all_xy) for k in ("v1", "v2")}
clear_v2 = los["v2"] & tree_free(all_xy)
inside_v2 = sc.height_below(scenes["v2"], all_xy) > 0.5
rows = []


def add(metric, v1, v2, note=""):
    rows.append(dict(metric=metric, v1=v1, v2=v2, note=note))


best = {k: radio.rsrp_dbm(G[k]).max(1) for k in G}
serving = {k: G[k].argmax(1) for k in G}
u = np.arange(len(all_xy))
add("UEs (20 drops x 100, same positions)", len(all_xy), len(all_xy),
    f"{int(inside_v2.sum())} of them are inside a v2 building (kept, so the comparison stays paired)")
add("LOS to serving sector (%)", round(100 * los["v1"][u, serving["v1"]].mean(), 1), round(100 * los["v2"][u, serving["v2"]].mean(), 1),
    "buildings only")
add("LOS to serving sector, clear of tree crowns (%)", "–", round(100 * clear_v2[u, serving["v2"]].mean(), 1),
    "v2 only: straight line also misses every crown")
add("LOS to at least one sector (%)", round(100 * los["v1"].any(1).mean(), 1), round(100 * los["v2"].any(1).mean(), 1), "buildings only")
for k in ("v1", "v2"):
    best_cell, out = cov[k]
    cov[k] = dict(pct=100 * (best_cell[out] > THRESHOLD_DBM).mean(), med=float(np.median(best_cell[out])), n=int(out.sum()))
add(f"coverage, RSRP > {THRESHOLD_DBM:g} dBm (% of outdoor 5 m cells)", round(cov["v1"]["pct"], 1), round(cov["v2"]["pct"], 1),
    f"radio map, 1e6 rays; {cov['v1']['n']} / {cov['v2']['n']} outdoor cells; v2 trees: straight-line approximation")
add("median best-sector RSRP, outdoor cells (dBm)", round(cov["v1"]["med"], 1), round(cov["v2"]["med"], 1), "radio map")
add("median best-sector RSRP, UEs (dBm)", round(float(np.median(best["v1"])), 1), round(float(np.median(best["v2"])), 1),
    "path traces; v2 with per-path vegetation loss")
add("UEs whose serving sector changed (%)", "–", round(100 * (serving["v1"] != serving["v2"]).mean(), 1), "")
for metric in ("mean throughput (Mbps)", "5th-percentile throughput (Mbps)", "mean SINR (dB)"):
    for n in ("B1", "B2", "Twin"):
        add(f"{n}: {metric}", round(k6["v1"][metric][n], 2), round(k6["v2"][metric][n], 2), "task 6, mean of 20 drops")

# the same, only for UEs near a change (within NEAR_M of a building whose outline changed, or of a tree):
# campus-wide averages dilute the effect of 9 changed buildings and the hostel trees
from shapely.geometry import shape, Point                                         # noqa: E402
from shapely.ops import unary_union                                                # noqa: E402
NEAR_M = 30.0
fp2 = json.loads((ROOT / "scenes" / "iitgn_v2" / "footprints.geojson").read_text())["features"]
changed = unary_union([shape(f["geometry"]) for f in fp2
                       if f["properties"]["source"].startswith("drawing") or f["properties"]["name"] == "Lal Minar"])
changed = unary_union([changed] + [Point(x, y).buffer(d / 2) for x, y, d in zip(trees["xy"][:, 0], trees["xy"][:, 1], 2 * trees["r"])])
near = np.array([changed.distance(Point(x, y)) <= NEAR_M for x, y in all_xy])
add(f"UEs near a change (within {NEAR_M:g} m of an outline from the drawings, Lal Minar or a tree)", int(near.sum()), int(near.sum()),
    "rows below: these UEs only (every v2 building also has a new height: G+3 = 14 m, kiosks 3.5 m)")
add("  near: LOS to serving sector (%)", round(100 * los["v1"][u, serving["v1"]][near].mean(), 1),
    round(100 * los["v2"][u, serving["v2"]][near].mean(), 1), "buildings only")
add("  near: LOS to serving sector, clear of tree crowns (%)", "–", round(100 * clear_v2[u, serving["v2"]][near].mean(), 1), "")
add("  near: median best-sector RSRP (dBm)", round(float(np.median(best["v1"][near])), 1), round(float(np.median(best["v2"][near])), 1),
    f"median change per UE {np.median(best['v2'][near] - best['v1'][near]):+.1f} dB")
add("  near: UEs whose serving sector changed (%)", "–", round(100 * (serving["v1"] != serving["v2"])[near].mean(), 1),
    f"far from these: {100 * (serving['v1'] != serving['v2'])[~near].mean():.1f} % (mostly the new G+3 heights, which "
    f"change every building; ray-tracing noise alone was about 3 %)")

with open(res_v2 / "before_after.csv", "w", newline="") as f:
    w = csv.DictWriter(f, ["metric", "v1", "v2", "note"]); w.writeheader(); w.writerows(rows)
md = ["| metric | v1 (study) | v2 (drawings + trees) | note |", "|---|---|---|---|"] + \
     [f"| {r['metric']} | {r['v1']} | {r['v2']} | {r['note']} |" for r in rows]
md += ["", f"Vegetation: {vegetation.VEG_DB_PER_M} dB/m, cap {vegetation.VEG_CAP_DB} dB, crown from "
       f"{vegetation.CROWN_BASE_M} m up to the tree height: TO BE CALIBRATED (twin/vegetation.py)."]
(res_v2 / "before_after.md").write_text("\n".join(md) + "\n")
print("4. before/after (results/study_v2/before_after.md):\n" + "\n".join(md))

# ---- 5. data for the 3D view: v2 buildings mesh, trees, RSRP map picture (same extent and colours as v1's)
from PIL import Image                                    # noqa: E402
twin = json.loads((ROOT / "data" / "twin.json").read_text())
ext, (lo, hi), colours = twin["rsrp_map"]["extent"], twin["rsrp_map"]["dbm"], twin["rsrp_map"]["colors"]
best_cell, out = coverage("v2", tuple(ext))
rgb = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in colours], float)
f = np.clip((best_cell - lo) / (hi - lo), 0, 1) * (len(rgb) - 1)
i0 = np.minimum(f.astype(int), len(rgb) - 2); t = (f - i0)[..., None]
img = (rgb[i0] * (1 - t) + rgb[i0 + 1] * t).astype(np.uint8)
alpha = np.where(out & (best_cell > -300), 230, 0).astype(np.uint8)
pic = Image.fromarray(np.dstack([img, alpha])[::-1], "RGBA")                      # row 0 = north
buf = io.BytesIO(); pic.save(buf, "PNG")
raw = (ROOT / "scenes" / "iitgn_v2" / "meshes" / "buildings.ply").read_bytes()
h = raw.index(b"end_header\n") + 11
head = raw[:h].decode()
nv, nf = int(head.split("element vertex ")[1].split()[0]), int(head.split("element face ")[1].split()[0])
V = np.frombuffer(raw[h:h + nv * 12], np.float32)
F = np.frombuffer(raw[h + nv * 12:], dtype=np.dtype([("n", "u1"), ("i", "<i4", 3)]), count=nf)["i"].astype(np.uint32)
tree_rows = list(csv.DictReader(open(ROOT / "scenes" / "iitgn_v2" / "trees.csv")))
(ROOT / "data" / "scene_v2.json").write_text(json.dumps(dict(
    buildings=dict(points=base64.b64encode(V.tobytes()).decode(), triangles=base64.b64encode(F.tobytes()).decode(), count=nf),
    rsrp_map=dict(png="data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), extent=ext, dbm=[lo, hi], colors=colours,
                  note="v2: Sionna radio map, 1e6 rays, 5 m, best sector, vegetation by straight-line approximation"),
    trees=[[round(float(r["x_m"]), 1), round(float(r["y_m"]), 1), float(r["crown_d_m"]), float(r["height_m"])] for r in tree_rows],
    before_after=rows, vegetation=dict(db_per_m=vegetation.VEG_DB_PER_M, cap_db=vegetation.VEG_CAP_DB,
                                       crown_base_m=vegetation.CROWN_BASE_M, status="to be calibrated")),
    separators=(",", ":")))
print("5. wrote data/scene_v2.json for the 3D view")
