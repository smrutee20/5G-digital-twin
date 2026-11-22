"""
Checks for the Configure feature (ray traces, so it takes about a minute):   .venv/bin/python server/test_configure.py

  1. the default settings reproduce today's RSRP (data/twin.json routes, traced by task 5 at 1e6 rays), and the
     SINR formula equals twin/radio.py's for 1x1 arrays
  2. an 8x8 array with the SSB codebook gives a higher best-beam RSRP at boresight than 1x1
  3. the total transmit power is the same for every array size (unit-norm beams, P/N per element)
  4. the coverage map and the per-UE trace agree at the same points
  5. a repeated configuration is served from the cache
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import engine, beams                      # noqa: E402
from server.app import SimulateRequest, Sector, _simulate, _state   # noqa: E402
from twin import radio                                 # noqa: E402

failures = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        failures.append(name)


tw = engine.Twin()
_state["twins"] = {"v1": tw}                           # the app's cached-simulate path uses the same scene
S = engine.default_sectors()
UE = engine.UE_DEFAULT
twin = json.loads((engine.ROOT / "data" / "twin.json").read_text())
xy = np.concatenate([np.array(r["points"]) for r in twin["routes"]])
ref = np.concatenate([np.array(r["rsrp"]) for r in twin["routes"]])

# ---- 1. defaults reproduce today's values
# Traced route by route, one batch each, at the study's 1e6 rays, exactly as task 5 did. Sionna's path search is
# not bit-for-bit repeatable: running the original twin.scene.trace three times on these routes gave a max
# difference of 0.02 dB in one run and 8.5 dB on the same 9 of 1782 links in the other two. "Within ray-tracing
# noise" therefore means: >= 99 % of links within 0.1 dB and the same serving sector at every point.
parts = [tw.trace_ues(S, UE, np.array(r["points"]), rays=engine.sc.RAYS_PER_SECTOR, batch=100) for r in twin["routes"]]
out = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
d = np.abs(out["rsrp_dbm"] - ref)
check("1a default config reproduces today's RSRP at 1e6 rays (every link of the 3 routes)",
      (d <= 0.1).mean() >= 0.99 and (out["rsrp_dbm"].argmax(1) == ref.argmax(1)).all(),
      f"{d.size} links: {100 * (d <= 0.1).mean():.1f} % within 0.1 dB (median {np.median(d):.3f}, max {d.max():.2f}), "
      f"same serving sector at all {len(xy)} points")
quick = tw.trace_ues(S, UE, xy, rays=engine.INTERACTIVE_RAYS)
dq = np.abs(quick["rsrp_dbm"] - ref)
strong = ref > -80
check("1b at 2e5 rays (interactive) strong links stay within ray noise",
      np.median(dq[strong]) <= 0.5,
      f"links > -80 dBm: median |diff| {np.median(dq[strong]):.2f} dB; all links: median {np.median(dq):.2f} dB, "
      f"same serving {100 * (quick['rsrp_dbm'].argmax(1) == ref.argmax(1)).mean():.0f} % (information only)")
serving, sinr = engine.serving_and_sinr(out["rsrp_dbm"], out["avg_beam_dbm"], UE["noise_figure_db"])
gain_db = out["rsrp_dbm"] - (engine.sc.TX_POWER_DBM - 10 * np.log10(engine.RE_PER_CARRIER))
old = radio.sinr_all_on_db(radio.prb_power_mw(gain_db), serving, np.ones(len(S), bool))
check("1c 1x1 SINR equals twin/radio.sinr_all_on_db", np.allclose(sinr, old, atol=1e-6),
      f"max |diff| {np.abs(sinr - old).max():.2e} dB")

# ---- 2. 8x8 + codebook beats 1x1 at boresight
site = config_site = engine.sector_xy("A60")
az = np.deg2rad(60.0)
cand = np.array([[site[0] + r * np.cos(az), site[1] + r * np.sin(az)] for r in np.arange(120, 320, 10)])
cand = cand[tw.outdoor(cand)]
los = tw.line_of_sight(S, np.c_[cand, np.full(len(cand), UE["height_m"])])[:, 0]
point = cand[los][:1] if los.any() else cand[:1]
r1 = tw.trace_ues(S, UE, point)["rsrp_dbm"][0, 0]
S8 = [dict(s, array="8x8") for s in S]
r8 = tw.trace_ues(S8, UE, point)["rsrp_dbm"][0, 0]
check("2  8x8 best-beam RSRP at A60 boresight > 1x1", r8 > r1 + 10,
      f"UE at ({point[0, 0]:.0f}, {point[0, 1]:.0f}) {'LOS' if los.any() else 'NLOS'}: 1x1 {r1:.1f} dBm, "
      f"8x8 {r8:.1f} dBm (+{r8 - r1:.1f} dB; ideal array gain 18.1 dB less the loss between beams)")

# ---- 3. total power is the same for every array size
ok, rows = True, []
for arr in ("1x1", "4x4", "8x8", "16x16"):
    for pol in ("V", "cross"):
        cfg = dict(S[0], array=arr, polarization=pol)
        tw._place([cfg])
        a = tw.scene.tx_array
        for nb in (1, 8, 16):
            W = beams.codebook(a, nb)
            ok &= np.allclose((np.abs(W) ** 2).sum(1), 1.0)                     # unit norm -> total = P
        tx = tw.scene.get(cfg["name"])
        per_element_dbm = cfg["power_dbm"] - 10 * np.log10(a.num_ant)
        total_dbm = 10 * np.log10(a.num_ant * 10 ** (per_element_dbm / 10))
        ok &= abs(float(tx.power_dbm[0]) - cfg["power_dbm"]) < 1e-4 and abs(total_dbm - cfg["power_dbm"]) < 1e-9
        rows.append(f"{arr} {pol}: {a.num_ant} el x {per_element_dbm:.1f} dBm = {total_dbm:.1f} dBm")
check("3  total transmit power is the same across array sizes", bool(ok), "; ".join(rows[::2]))

# ---- 4. coverage map vs per-UE trace
best, _ = tw.coverage(S, UE["height_m"], rays=engine.sc.RAYS_PER_SECTOR)
g, out_cells = tw.grid, tw.outdoor_cells()
rng = np.random.default_rng(3)
iy, ix = np.nonzero(out_cells & (best > -100))
pick = rng.choice(len(iy), 60, replace=False)
pts = np.c_[g["x0"] + engine.GRID_M * (ix[pick] + 0.5), g["y0"] + engine.GRID_M * (iy[pick] + 0.5)]
pu = tw.trace_ues(S, UE, pts, rays=engine.sc.RAYS_PER_SECTOR)["rsrp_dbm"].max(1)
dm = np.abs(pu - best[iy[pick], ix[pick]])
check("4  coverage map agrees with the per-UE trace (60 outdoor cells > -100 dBm, 1e6 rays)", np.median(dm) <= 3.0,
      f"median |diff| {np.median(dm):.2f} dB, 90th pct {np.percentile(dm, 90):.2f} dB "
      f"(a map cell averages 5 x 5 m; the UE is one point)")

# ---- 5. cache
req = SimulateRequest(sectors=[Sector(**s) for s in S], ues=[dict(id="a", x=float(point[0, 0]), y=float(point[0, 1]))])
_state["version"] = "test"
t = time.time(); a = _simulate(req); t1 = time.time() - t
t = time.time(); b = _simulate(req); t2 = time.time() - t
check("5  a repeated configuration is served from the cache", b["cache"] == "hit" and a["ues"] == b["ues"] and t2 < 0.5,
      f"first {t1:.2f} s ({a['cache']}), repeat {t2:.3f} s ({b['cache']}); {a['coverage']['label']}")

print("\nall passed" if not failures else f"\n{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
