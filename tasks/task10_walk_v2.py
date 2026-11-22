"""
Task 10: a person walking along the campus roads, on twin v2 (the demo's Mobility tab). v1's task 5 is not touched.

  1. Walking network: OpenStreetMap highways (footway, path, pedestrian, service, residential, tertiary) from
     data/osm_context.json. Ways are densified to <= 4 m; points of different ways closer than 3 m are joined (OSM
     ways often cross without a shared node), and dangling way ends within 8 m of another way are joined to it.
  2. Three routes: shortest paths through the waypoints in ROUTES, resampled every 2 m, 300-600 m long.
     Checks: no point inside a v2 building (footprint and the scene's ray-cast) or in water (OSM water areas, the
     river drawn 30 m wide); each route crosses at least one sector border on the v2 serving-sector map.
  3. Radio: every route point ray-traced on v2 (1e6 rays, vegetation loss), the A3 rule (3 dB, 2 steps), and the
     walker's B1 and Twin throughput exactly as task 5 (10 placements of the other UEs, from data/study_v2).
  4. Saved: data/study_v2/walk_routes.json (read by run.py for the 5G timeline and the 3D view),
     data/study_v2/walk_traces.npz, walk_serving_map.npz; results/study_v2/task10_walk.png, task10_walk_routes.csv,
     task10_walk_summary.csv, task10_walk_checks.md.

Run after task 9:  python tasks/task10_walk_v2.py        (--routes-only: steps 1-2 and the route plot, no tracing)
"""
import csv
import json
import math
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra, connected_components
from scipy.spatial import cKDTree
from shapely.geometry import shape, Point, Polygon, LineString
from shapely.ops import unary_union
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["TWIN_SCENE"] = "v2"
import config                                            # noqa: E402
from twin import scene as sc, radio, vegetation          # noqa: E402
from twin.allocation import run, nearest_sector, strongest_sector   # noqa: E402

ROUTES_ONLY = "--routes-only" in sys.argv
RAYS = sc.RAYS_PER_SECTOR
GRID_M = 5.0
LAT0, LON0, M_PER_DEG = 23.2107, 72.6872, 111320.0
WALKABLE = {"footway", "path", "pedestrian", "service", "residential", "tertiary"}
# name, waypoints (twin metres; each snapped to the nearest network point), places passed
ROUTES = [
    dict(id=1, name="Hostels → Lal Minar", via=[(-228, 46), (-180, 256), (-311, 284)],
         places="from the hostels' north side (Chimair / Beauki), north to the academic area, "
                "west past Blocks 06 and 07 to Lal Minar"),
    dict(id=2, name="Hostels → Sports complex", via=[(-201, 48), (128, 53)],
         places="from the hostels past the Old Mess and Central Arcade, east to the Indoor Sports Complex"),
    dict(id=3, name="Academic area → Guest house", via=[(-30, 287), (240, 290), (237, 29)],
         places="from Academic Block 13, east along the academic road, then south past the Indoor Sports Complex to the Guest House"),
]
data, results = sc.folders()                              # data/study_v2, results/study_v2
assert data.name == "study_v2", data


# ---------------------------------------------------------------------- 1. the walking network
def to_local(p):
    return ((p["lon"] - LON0) * M_PER_DEG * math.cos(math.radians(LAT0)), (p["lat"] - LAT0) * M_PER_DEG)


def walking_network():
    els = json.loads((ROOT / "data" / "osm_context.json").read_text())["elements"]
    P, way, E, n_ways = [], [], [], 0
    for wi, e in enumerate(els):
        if e["type"] != "way" or e.get("tags", {}).get("highway") not in WALKABLE:
            continue
        n_ways += 1
        pts = np.array([to_local(p) for p in e["geometry"] if p])
        dense = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            n = max(1, int(np.ceil(np.linalg.norm(b - a) / 4)))
            dense += [a + (b - a) * (i / n) for i in range(1, n + 1)]
        k0 = len(P); P += dense; way += [wi] * len(dense)
        E += [(k0 + i, k0 + i + 1) for i in range(len(dense) - 1)]
    xy, way = np.array(P), np.array(way)
    joins = [(i, j) for i, j in cKDTree(xy).query_pairs(3.0)
             if way[i] != way[j] or np.linalg.norm(xy[i] - xy[j]) < 0.05]          # crossings / shared nodes
    E += joins
    deg = np.bincount(np.array(E).ravel(), minlength=len(xy))
    ends = 0
    for i in np.nonzero(deg == 1)[0]:                                            # dangling way ends
        o = np.nonzero(way != way[i])[0]
        d = np.linalg.norm(xy[o] - xy[i], axis=1)
        if d.min() < 8:
            E.append((i, o[d.argmin()])); ends += 1
    a, b = np.array(E).T
    G = coo_matrix((np.linalg.norm(xy[a] - xy[b], axis=1) + 1e-3, (a, b)), shape=(len(xy),) * 2).tocsr()
    G = G + G.T
    n_comp, lab = connected_components(G, directed=False)
    info = dict(ways=n_ways, points=len(xy), crossings_joined=len(joins), ends_joined=ends,
                largest_component_pct=round(float(100 * np.bincount(lab).max() / len(xy)), 1), components=int(n_comp))
    return xy, G, info


def shortest(xy, G, via):
    idx = [int(np.argmin(np.linalg.norm(xy - np.array(p), axis=1))) for p in via]
    seq = [idx[0]]
    for s, t in zip(idx, idx[1:]):
        _, pred = dijkstra(G, indices=s, return_predecessors=True)
        part = [t]
        while part[-1] != s:
            if part[-1] < 0:
                raise SystemExit(f"no walking path from {xy[s]} to {xy[t]}")
            part.append(pred[part[-1]])
        seq += part[::-1][1:]
    return xy[seq]


def resample(line, step=config.STEP_M):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
    s = np.arange(0, d[-1] + 1e-6, step)
    return np.c_[np.interp(s, d, line[:, 0]), np.interp(s, d, line[:, 1])], d[-1]


xy_net, G, net_info = walking_network()
print(f"1. walking network: {net_info}")
routes = []
for r in ROUTES:
    pts, length = resample(shortest(xy_net, G, r["via"]))
    routes.append(dict(r, points=np.round(pts, 2), length_m=round(float(length), 1)))
    print(f"   route {r['id']} {r['name']}: {length:.0f} m, {len(pts)} points")

# ---------------------------------------------------------------------- 2. checks
foot = [shape(f["geometry"]) for f in json.loads((ROOT / "scenes" / "iitgn_v2" / "footprints.geojson").read_text())["features"]]
buildings = prep(unary_union(foot))
ctx = json.loads((ROOT / "data" / "campus_context.json").read_text())
water_parts = [Polygon(a["pts"]["outer"] if isinstance(a["pts"], dict) else a["pts"]).buffer(0)
               for a in ctx["areas"] if a["kind"] == "water"]
water_parts += [LineString(l).buffer(15) for l in ctx["river_lines"] if len(l) > 1]
water = prep(unary_union(water_parts))
scene = sc.load()
checks = []
for r in routes:
    p = r["points"]
    in_fp = np.array([buildings.contains(Point(x, y)) for x, y in p])
    in_mesh = sc.height_below(scene, p) > 0.5
    in_water = np.array([water.contains(Point(x, y)) for x, y in p])
    gap = min(unary_union(foot).distance(Point(x, y)) for x, y in p)
    checks.append(dict(route=r["id"], name=r["name"], length_m=r["length_m"], points=len(p),
                       inside_building_footprint=int(in_fp.sum()), inside_building_raycast=int(in_mesh.sum()),
                       in_water=int(in_water.sum()), closest_to_a_building_m=round(float(gap), 1)))
    r["check_ok"] = not (in_fp.any() or in_mesh.any() or in_water.any()) and 300 <= r["length_m"] <= 600
    print(f"2. route {r['id']}: {checks[-1]}  -> {'OK' if r['check_ok'] else 'FAIL'}")

# the v2 serving-sector map (Sionna radio map, 5 m, straight-line crown loss as in task 9) around the routes
ant = np.array([s["pos"] for s in config.sectors()], float)
names = sc.sector_names()
allp = np.concatenate([r["points"] for r in routes])
x0, y0 = (float(v) for v in np.floor(allp.min(0) / GRID_M - 8) * GRID_M)
x1, y1 = (float(v) for v in np.ceil(allp.max(0) / GRID_M + 8) * GRID_M)
map_file = data / "walk_serving_map.npz"
if map_file.exists() and np.allclose(np.load(map_file)["bounds"], [x0, x1, y0, y1]):
    best_map, serv_map = np.load(map_file)["best_dbm"], np.load(map_file)["serving"]
else:
    from sionna.rt import RadioMapSolver
    nx, ny = int(round((x1 - x0) / GRID_M)), int(round((y1 - y0) / GRID_M))
    rm = RadioMapSolver()(scene, center=[(x0 + x1) / 2, (y0 + y1) / 2, sc.UE_HEIGHT_M], orientation=[0.0, 0.0, 0.0],
                          size=[nx * GRID_M, ny * GRID_M], cell_size=[GRID_M, GRID_M], samples_per_tx=int(RAYS),
                          max_depth=sc.MAX_BOUNCES, diffraction=sc.DIFFRACTION, edge_diffraction=sc.DIFFRACTION,
                          diffuse_reflection=False, refraction=False, seed=sc.SEED)
    pg = np.array(rm.path_gain)                                                 # [sector, ny, nx]
    X, Y = np.meshgrid(x0 + GRID_M * (np.arange(nx) + 0.5), y0 + GRID_M * (np.arange(ny) + 0.5))
    trees = vegetation.load_trees(scene.twin_xml)
    cells = np.c_[X.ravel(), Y.ravel(), np.full(X.size, sc.UE_HEIGHT_M)]
    for t in range(len(ant)):
        L = vegetation.length_in_crowns(np.repeat(ant[t][None], len(cells), 0), cells, trees)
        pg[t] *= 10 ** (-vegetation.loss_db(L).reshape(ny, nx) / 10)
    rsrp_map = radio.rsrp_dbm(10 * np.log10(pg + 1e-30))
    best_map, serv_map = rsrp_map.max(0), rsrp_map.argmax(0)
    np.savez(map_file, best_dbm=best_map, serving=serv_map, bounds=[x0, x1, y0, y1], grid_m=GRID_M)
for r, c in zip(routes, checks):
    ix = np.clip(((r["points"][:, 0] - x0) // GRID_M).astype(int), 0, serv_map.shape[1] - 1)
    iy = np.clip(((r["points"][:, 1] - y0) // GRID_M).astype(int), 0, serv_map.shape[0] - 1)
    s = serv_map[iy, ix]
    # a border = the map's best sector changes and stays changed for 8 points (16 m), so single noisy cells don't count
    runs, k = [s[0]], 0
    for k2 in range(1, len(s)):
        if s[k2] != runs[-1] and (s[k2:k2 + 8] == s[k2]).all():
            runs.append(s[k2])
    c["map_sectors_along_route"] = " → ".join(names[i] for i in runs)
    c["map_sector_borders"] = len(runs) - 1
    c["map_site_borders"] = sum(names[a][0] != names[b][0] for a, b in zip(runs, runs[1:]))
    r["check_ok"] &= c["map_sector_borders"] >= 1
    print(f"   route {r['id']} on the v2 serving map: {c['map_sectors_along_route']}")


def plot_routes(path):
    fig, ax = plt.subplots(figsize=(11, 11))
    cmap = plt.get_cmap("tab10")
    ax.imshow(np.where(best_map > -140, serv_map, np.nan), origin="lower", extent=[x0, x1, y0, y1], cmap=cmap,
              vmin=0, vmax=9, alpha=0.35, interpolation="nearest")
    for g in foot:
        for p in getattr(g, "geoms", [g]):
            ax.fill(*p.exterior.xy, color="#888", lw=0)
    for wp in water_parts:
        for p in getattr(wp, "geoms", [wp]):
            ax.fill(*p.exterior.xy, color="#5aa9e6", alpha=0.6, lw=0)
    for r in routes:
        ax.plot(*r["points"].T, lw=2.5, label=f"{r['id']}: {r['name']} ({r['length_m']:.0f} m)")
        ax.plot(*r["points"][0], "ko", ms=5)
    for i, s in enumerate(config.sectors()):
        if i % 3 == 0:
            ax.plot(*s["pos"][:2], "k^", ms=12); ax.text(s["pos"][0] + 6, s["pos"][1] + 6, s["site"], fontsize=14)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal"); ax.legend(loc="lower left", fontsize=9)
    ax.set_title("Walking routes on the OSM network; background = v2 best sector (one colour per sector), "
                 "grey = v2 buildings, blue = water", fontsize=9)
    fig.savefig(path, dpi=110, bbox_inches="tight"); plt.close(fig)


plot_routes(results / "task10_walk_routes_map.png")
if ROUTES_ONLY:
    sys.exit()
if not all(r["check_ok"] for r in routes):
    raise SystemExit("a route failed its checks (see above); change ROUTES")


# ---------------------------------------------------------------------- 3. radio: trace, A3, throughput
def a3(rsrp):
    """The same rule as task 5 and the demo: another sector > 3 dB stronger for 2 steps in a row."""
    serving, candidate, count = int(np.argmax(rsrp[0])), None, 0
    path, handovers = [serving], []
    for k in range(1, len(rsrp)):
        best = int(np.argmax(rsrp[k]))
        if best != serving and rsrp[k, best] > rsrp[k, serving] + config.A3_OFFSET_DB:
            count = count + 1 if best == candidate else 1
            candidate = best
        else:
            count, candidate = 0, None
        if count >= config.A3_STEPS:
            handovers.append((k, names[serving], names[best]))
            serving, candidate, count = best, None, 0
        path.append(serving)
    return np.array(path), handovers


trace_file = data / "walk_traces.npz"
key = np.concatenate([r["points"] for r in routes])
if trace_file.exists() and np.array_equal(np.load(trace_file)["points"], key):
    t = np.load(trace_file); gain_all, los_all, clear_all = t["path_gain_db"], t["los"], t["los_clear"]
    print("3. traces: using data/study_v2/walk_traces.npz")
else:
    print(f"3. tracing {len(key)} route points x 9 sectors on v2 at {RAYS:.0e} rays ...")
    gain_all, los_all = sc.trace(scene, key, RAYS)
    trees = vegetation.load_trees(scene.twin_xml)
    pts3 = np.c_[key, np.full(len(key), sc.UE_HEIGHT_M)]
    crown = np.stack([vegetation.length_in_crowns(np.repeat(a[None], len(pts3), 0), pts3, trees) for a in ant], 1)
    clear_all = los_all & (crown == 0)
    np.savez(trace_file, points=key, path_gain_db=gain_all, los=los_all, los_clear=clear_all)

PLACEMENTS, T_95 = 10, 2.262
first, more = np.load(data / "measurements.npz"), np.load(data / "drops.npz")
placements = ([(first["ue_xy"], first["path_gain_db"])] + list(zip(more["ue_xy"], more["path_gain_db"])))[:PLACEMENTS]
active = np.ones(len(names), bool)
rows, summary, out_routes = [], [], []
fig, axes = plt.subplots(3, 2, figsize=(14, 10))
start = 0
for r, route in enumerate(routes):
    n = len(route["points"])
    gain, los, clear = gain_all[start:start + n], los_all[start:start + n], clear_all[start:start + n]
    start += n
    rsrp = radio.rsrp_dbm(gain)
    serving, handovers = a3(rsrp)
    xn = [h for h in handovers if h[1][0] != h[2][0]]
    print(f"   route {route['id']} {route['name']}: " + (", ".join(f"{a}->{b} at {k * config.STEP_M:.0f} m"
          for k, a, b in handovers) or "no handover") + f"  ({len(xn)} between sites = Xn)")
    thr = {"B1": np.zeros((PLACEMENTS, n)), "Twin": np.zeros((PLACEMENTS, n))}
    for p, (others_xy, others_gain) in enumerate(placements):
        others_rx = radio.prb_power_mw(others_gain)
        others_twin = strongest_sector(others_rx, active)
        w = np.random.default_rng(p).integers(0, len(others_xy) + 1)
        for k, point in enumerate(route["points"]):
            rx = np.insert(others_rx, w, radio.prb_power_mw(gain[k]), axis=0)
            xy = np.insert(others_xy, w, point, axis=0)
            thr["B1"][p, k] = run("B1", rx, xy)["throughput_mbps"][w]
            thr["Twin"][p, k] = run("Twin", rx, xy, serving=np.insert(others_twin, w, serving[k]))["throughput_mbps"][w]
    line = [route["id"], route["name"], route["length_m"], n, len(handovers), len(xn)]
    for nm in ["B1", "Twin"]:
        per = thr[nm].mean(axis=1)
        mean, ci, zero = per.mean(), T_95 * per.std(ddof=1) / np.sqrt(PLACEMENTS), 100 * (thr[nm] == 0).mean()
        line += [round(mean, 2), round(ci, 2), round(zero, 1)]
        print(f"         {nm:4s}: walker {mean:5.1f} ± {ci:.1f} Mbps, 0 Mbps on {zero:4.1f} % of steps")
    line += [round(100 * los[np.arange(n), serving].mean(), 1), round(100 * clear[np.arange(n), serving].mean(), 1)]
    summary.append(line)
    b1 = nearest_sector(route["points"], active)
    for k in range(n):
        rows.append([route["id"], k, k * config.STEP_M, *route["points"][k], names[b1[k]], names[serving[k]],
                     round(float(rsrp[k, serving[k]]), 1), bool(los[k, serving[k]]),
                     round(thr["B1"][:, k].mean(), 2), round(thr["Twin"][:, k].mean(), 2)])
    out_routes.append(dict(id=route["id"], name=route["name"], places=route["places"], length_m=route["length_m"],
                           points=route["points"].tolist(), rsrp=[[float(v) for v in s] for s in rsrp],
                           los=los.tolist(), los_clear=clear.tolist(), traced=[[True] * len(names)] * n,
                           a3_handovers=[dict(step=k, src=a, dst=b, xn=a[0] != b[0]) for k, a, b in handovers],
                           b1_mbps=[round(v, 2) for v in thr["B1"].mean(0)], twin_mbps=[round(v, 2) for v in thr["Twin"].mean(0)]))
    dist = np.arange(n) * config.STEP_M
    left, right = axes[r]
    for s, nm in enumerate(names):
        l_, = left.plot(dist, rsrp[:, s], lw=0.8, alpha=0.6, label=nm)
        left.plot(dist, np.where(serving == s, rsrp[:, s], np.nan), lw=3, color=l_.get_color())
    right.plot(dist, thr["B1"].mean(0), color="#9ca3af", lw=2, label="B1")
    right.plot(dist, thr["Twin"].mean(0), color="#2563eb", lw=2, label="Twin")
    for k, a, b in handovers:
        for ax in (left, right):
            ax.axvline(k * config.STEP_M, color="k", ls=":")
        left.text(k * config.STEP_M, -62, f" {a}→{b}", fontsize=8, va="top")
    left.set_ylim(-150, -60); left.set_ylabel("RSRP (dBm)")
    left.set_title(f"{route['name']} (v2): RSRP, thick = serving, dotted = handover", loc="left", fontsize=10)
    right.set_ylabel("walker (Mbps)")
    right.set_title(f"{route['name']}: walker's throughput, mean of {PLACEMENTS} placements", loc="left", fontsize=10)
axes[0, 0].legend(ncol=9, fontsize=7, loc="lower left"); axes[0, 1].legend()
for ax in axes[-1]:
    ax.set_xlabel("distance walked (m)")
fig.tight_layout(); fig.savefig(results / "task10_walk.png", dpi=130)

# ---------------------------------------------------------------------- 4. save
with open(results / "task10_walk_routes.csv", "w", newline="") as f:
    csv.writer(f).writerows([["route", "step", "distance_m", "x_m", "y_m", "b1_sector", "twin_sector", "serving_rsrp_dbm",
                              "serving_los", "b1_mbps_mean", "twin_mbps_mean"]] + rows)
with open(results / "task10_walk_summary.csv", "w", newline="") as f:
    csv.writer(f).writerows([["route", "name", "length_m", "points", "handovers", "xn_handovers", "b1_mean_mbps",
                              "b1_ci95", "b1_zero_pct", "twin_mean_mbps", "twin_ci95", "twin_zero_pct",
                              "los_serving_pct", "los_serving_clear_of_trees_pct"]] + summary)
md = ["# Task 10: walking routes on twin v2: checks", "",
      f"Walking network (OSM highway = {', '.join(sorted(WALKABLE))}): {net_info}", "",
      "| route | length (m) | points | in a building (footprint / ray-cast) | in water | closest to a building (m) | v2 map: best sector along the route | sector borders (site borders) |",
      "|---|---|---|---|---|---|---|---|"]
md += [f"| {c['route']} {c['name']} | {c['length_m']:.0f} | {c['points']} | {c['inside_building_footprint']} / "
       f"{c['inside_building_raycast']} | {c['in_water']} | {c['closest_to_a_building_m']} | {c['map_sectors_along_route']} | "
       f"{c['map_sector_borders']} ({c['map_site_borders']}) |" for c in checks]
md += ["", "Water = OSM water areas and the river drawn 30 m wide. Ray-cast = the v2 Sionna scene's surface height under "
       "the point > 0.5 m. Map = Sionna radio map on v2, 1e6 rays, 5 m cells; a border counts when the new best sector "
       "holds for 16 m.", ""]
(results / "task10_walk_checks.md").write_text("\n".join(md))
(data / "walk_routes.json").write_text(json.dumps(dict(
    scene="v2", rays=RAYS, step_m=config.STEP_M, network=net_info, checks=checks, routes=out_routes,
    note="tasks/task10_walk_v2.py: OSM walking network, v2 ray tracing with vegetation loss, A3 3 dB / 2 steps"),
    separators=(",", ":")))
print(f"4. saved walk_routes.json, walk_traces.npz in {data}; task10_* in {results}")
