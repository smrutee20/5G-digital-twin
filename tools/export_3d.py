"""
Export the digital twin of a scenario to one self-contained interactive 3D web page.

    python tools/export_3d.py                                    # IITGN -> results/iitgn/twin_3d.html
    DT_CONFIG=config/<name>.yaml python tools/export_3d.py       # other scene -> results/<tag>/twin_3d.html

Run it after run_all.py (it reads the ray-traced channels and the result tables).
Open the HTML file in any browser (needs internet once to load the 3D library).

What goes into the page:
  * the scene's building meshes and the RU sites with their sector directions
  * best-server RSRP and SINR maps draped on the ground
  * one drop of users, coloured by throughput, under the baseline (B1) and the twin (T3)
  * the strongest ray-traced paths from each user's serving RU (LOS / reflection / diffraction)
  * the mobility walks (Task 5) with the serving RU at every 2 m step
  * headline KPIs and what-if results
"""
import sys, io, json, base64
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dt.config import load_config, DATA, TAB, RESULTS
from dt.twin import DigitalTwin
from dt.channel import ChannelSet
from dt.alloc import simulate, STRATEGIES
from sionna.rt import Receiver, PathSolver

cfg = load_config()
E = cfg["experiments"]
twin = DigitalTwin(cfg)
ch = ChannelSet.load(DATA / "twin_pool.npz")
cov = np.load(DATA / "coverage.npz")
p_re = cfg["ran"]["tx_power_dbm"] - 10 * np.log10(cfg["carrier"]["num_prb"] * 12) + cfg["ran"]["bf_gain_db"]
b64 = lambda a: base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()

# ------------------------------------------------------------------ meshes (z-up, metres)
MAT_COLOR = {"marble": "#9d9e9a", "metal": "#6f7a84", "brick": "#8e5c47", "concrete": "#8c8983",
             "wood": "#8a6a4a", "glass": "#6f8c99", "building": "#8f8b84"}
meshes = []
for s in twin.scene.mi_scene.shapes():
    name = s.id()
    if "ground" in name.lower():
        continue
    v = np.array(s.vertex_positions_buffer(), np.float32).reshape(-1, 3)
    f = np.array(s.faces_buffer(), np.uint32).reshape(-1, 3)
    if not len(f):
        continue
    mat = next((m for m in MAT_COLOR if m in name.lower()), None)
    if mat is None:
        try:
            mat = s.bsdf().id().replace("mat_", "")
        except Exception:
            mat = "concrete"
    meshes.append(dict(name=name, color=MAT_COLOR.get(mat, "#8f8b84"), pos=b64(v), idx=b64(f), n=int(len(f))))

# ------------------------------------------------------------------ coverage images on the ground
pg, cc = cov["pg"], cov["centers"]
best = pg.max(0)
inside = twin.ground_height(cc[..., :2].reshape(-1, 2)).reshape(best.shape) > 0.5
ok = (best > 0) & ~inside
rsrp = p_re + 10 * np.log10(np.maximum(best, 1e-30))
noise_re = 10 ** (cfg["carrier"]["noise_prb_dbm"] / 10) / 12
sinr = 10 * np.log10(best * 10 ** (p_re / 10) / ((pg.sum(0) - best) * 10 ** (p_re / 10) + noise_re + 1e-30) + 1e-30)


def png(grid, vmin, vmax, cmap):
    rgba = plt.get_cmap(cmap)((np.clip(grid, vmin, vmax) - vmin) / (vmax - vmin))
    rgba[..., 3] = np.where(ok, 0.9, 0.0)
    buf = io.BytesIO()
    plt.imsave(buf, np.flipud(rgba), format="png")          # row 0 = north
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def bar(cmap):
    buf = io.BytesIO()
    plt.imsave(buf, plt.get_cmap(cmap)(np.linspace(0, 1, 256))[None].repeat(8, 0), format="png")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


dx, dy = cc[0, 1, 0] - cc[0, 0, 0], cc[1, 0, 1] - cc[0, 0, 1]
extent = [float(cc[..., 0].min() - dx / 2), float(cc[..., 0].max() + dx / 2),
          float(cc[..., 1].min() - dy / 2), float(cc[..., 1].max() + dy / 2)]
coverage = dict(extent=extent,
                rsrp=dict(img=png(rsrp, -125, -65, "Blues_r"), bar=bar("Blues_r"), vmin=-125, vmax=-65, unit="dBm",
                          label="SS-RSRP, best server"),
                sinr=dict(img=png(sinr, -10, 30, "BuGn_r"), bar=bar("BuGn_r"), vmin=-10, vmax=30, unit="dB",
                          label="Geometry SINR, full load"))

# ------------------------------------------------------------------ one drop under B1 and T3 (same as drop 0 in e03)
uniform = np.where(~np.array(ch.meta["is_hotspot"]))[0]
idx = np.random.default_rng(1000).choice(uniform, E["num_ues"], replace=False)
sub = ch.subset(idx)
names = list(STRATEGIES)
res = {k: simulate(cfg, sub, names[i], rng=np.random.default_rng(0)) for k, i in [("B1", 0), ("T3", 4)]}
users = dict(pos=sub.pos.round(2).tolist(), los=sub.los.tolist(),
             **{k: dict(serv=r["serving"].tolist(), thr=np.round(r["thr_mbps"], 2).tolist(),
                        sinr=np.round(r["sinr_db"], 1).tolist()) for k, r in res.items()})

# ------------------------------------------------------------------ strongest ray paths from each user's T3 serving RU
for n in list(twin.scene.receivers):
    twin.scene.remove(n)
for j, p in enumerate(sub.pos):
    twin.scene.add(Receiver(f"ue{j}", position=[float(v) for v in p]))
rt = cfg["raytracing"]["twin"]
paths = PathSolver()(twin.scene, max_depth=rt["max_depth"], samples_per_src=int(rt["samples_per_src"]),
                     diffraction=rt["diffraction"], edge_diffraction=rt["edge_diffraction"], refraction=False,
                     seed=cfg["scene"]["seed"])
V = np.array(paths.vertices)                    # [depth, rx, tx, path, 3]
I = np.array(paths.interactions)                # [depth, rx, tx, path]
VAL = np.array(paths.valid)                     # [rx, tx, path]
ar, ai = paths.a
P = (np.array(ar) ** 2 + np.array(ai) ** 2)[:, 0, :, 0, :]   # [rx, tx, path]
rays = []
for u in range(sub.U):
    r = int(res["T3"]["serving"][u])
    pw = np.where(VAL[u, r], P[u, r], 0)
    for k in np.argsort(-pw)[:4]:
        if pw[k] <= 0:
            continue
        pts = [twin.ru_pos[r].tolist()]
        kinds = []
        for d in range(V.shape[0]):
            if I[d, u, r, k] == 0:
                break
            pts.append(V[d, u, r, k].tolist())
            kinds.append(int(I[d, u, r, k]))
        pts.append(sub.pos[u].tolist())
        kind = "los" if not kinds else ("diffraction" if 8 in kinds else "reflection")
        rays.append(dict(u=u, ru=r, pts=np.round(pts, 2).tolist(), kind=kind,
                         db=round(float(10 * np.log10(pw[k])), 1), bounces=len(kinds)))
for n in list(twin.scene.receivers):
    twin.scene.remove(n)

# ------------------------------------------------------------------ mobility walks, KPIs, what-if
mobility = []
f5 = TAB / "t5_mobility_steps.csv"
if f5.exists():
    m = pd.read_csv(f5)
    for t, d in m.groupby("trajectory"):
        mobility.append(dict(id=int(t), x=d.x.round(2).tolist(), y=d.y.round(2).tolist(),
                             dist=d.distance_m.tolist(), serv_t3=d.serv_t3.tolist(), serv_b1=d.serv_b1.tolist(),
                             thr_t3=d.thr_t3.round(1).tolist(), thr_b1=d.thr_b1.round(1).tolist()))
kpi = {}
f6 = TAB / "t6_kpi_summary.csv"
if f6.exists():
    s = pd.read_csv(f6).set_index("strategy")
    for k in s.index:
        kpi[k] = {c: round(float(s.loc[k, c]), 2) for c in
                  ["mean_thr_mbps", "p5_thr_mbps", "mean_sinr_db", "outage_pct", "jain", "prb_util_pct"]}
whatif = []
f7 = TAB / "t7_whatif_summary.csv"
if f7.exists():
    w = pd.read_csv(f7)
    w = w[w.metric.str.startswith("Mean UE")]
    whatif = [dict(id=r.scenario, name=r.description, pred=r.predicted_twin, stat=r.predicted_38901, actual=r.actual)
              for r in w.itertuples()]

data = dict(
    title=cfg["scene"].get("title") or {"iitgn": "IIT Gandhinagar campus"}.get(
        cfg["scene"]["name"], cfg["scene"]["name"]),
    scenario=cfg["scene"]["name"], half=cfg["scene"]["half"],
    carrier=dict(f_ghz=cfg["carrier"]["frequency_hz"] / 1e9, bw_mhz=cfg["carrier"]["bandwidth_hz"] / 1e6,
                 prb=cfg["carrier"]["num_prb"]),
    rus=[dict(name=n, site=n.rstrip("0123456789"), pos=twin.ru_pos[i].round(2).tolist(),
              az=float(twin.ru_az[i]), tilt=float(twin.ru_tilt[i])) for i, n in enumerate(twin.ru_names)],
    sites=[dict(name=s["name"], xy=s["xy"], h=float(s.get("height_m", cfg["ran"]["height_m"]))) for s in cfg["ran"]["sites"]],
    meshes=meshes, coverage=coverage, users=users, rays=rays, mobility=mobility, kpi=kpi, whatif=whatif,
    stats=dict(num_buildings_faces=int(sum(m["n"] for m in meshes)), los_pct=round(100 * float(ch.los.mean()), 1),
               users_in_pool=int(ch.U)))

tpl = (ROOT / "tools" / "viewer_template.html").read_text()
out = RESULTS / "twin_3d.html"
page = tpl.replace("/*__TWIN_DATA__*/null", json.dumps(data, separators=(",", ":")))
page = page.replace("<title>RAN Twin 3D Viewer</title>", f"<title>{data['title'].title()} Twin</title>", 1)
# wrap as a complete document so it opens correctly straight from disk
doc = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>'
       + page + "</body></html>")
out.write_text(doc, encoding="utf-8")
(RESULTS / "twin_3d_fragment.html").write_text(page, encoding="utf-8")   # same page without the wrapper
print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB): {len(meshes)} meshes, {len(rays)} rays, "
      f"{len(mobility)} walks")
