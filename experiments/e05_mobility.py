"""
Task 5: move UEs through the scene and watch how the physical environment changes the
channel (LOS <-> NLOS transitions), the twin's serving-RU choice and the throughput.

Three walking trajectories are picked automatically from the twin's own radio map
(the ones with the most best-server changes), traced every 2 m, and simulated together
with 29 static background UEs. The twin applies an A3-like 3 dB hysteresis when it
re-associates the moving UE; the baseline keeps the nearest site.
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from dt.config import load_config, DATA, FIG, TAB
from dt.twin import DigitalTwin
from dt.channel import ChannelSet
from dt.alloc import simulate, STRATEGIES, rx_power, assoc_twin_lb, assoc_nearest
from dt.plotstyle import plt, save, STRAT_COLOR, SITE_COLOR, CAT, INK2, SEQ

cfg = load_config()
twin = DigitalTwin(cfg)
pool = ChannelSet.load(DATA / "twin_pool.npz")
cov = np.load(DATA / "coverage.npz")
pg, cc = cov["pg"], cov["centers"]
rng = np.random.default_rng(5)
STEP = 2.0
HALF = cfg["scene"]["half"]

# ---------------------------------------------------------------- choose trajectories from the radio map
def lookup_best(xy):
    i = np.clip(np.round((xy[:, 1] - cc[0, 0, 1]) / (cc[1, 0, 1] - cc[0, 0, 1])).astype(int), 0, pg.shape[1] - 1)
    j = np.clip(np.round((xy[:, 0] - cc[0, 0, 0]) / (cc[0, 1, 0] - cc[0, 0, 0])).astype(int), 0, pg.shape[2] - 1)
    v = pg[:, i, j]
    return np.argmax(v, 0), 10 * np.log10(v.max(0) + 1e-30)

cands = []
for _ in range(12000):
    a = rng.uniform(-(HALF - 40), HALF - 40, 2)
    th = rng.uniform(0, 2 * np.pi)
    b = a + 130 * np.array([np.cos(th), np.sin(th)])
    if np.abs(b).max() > HALF - 20:
        continue
    pts = a + np.outer(np.arange(0, 130 + 1e-6, STEP) / 130, b - a)
    if not twin.is_outdoor(pts[::3], clearance=1.0).all() or not twin.is_outdoor(pts, clearance=0.5).all():
        continue
    best, lvl = lookup_best(pts)
    if (lvl < -160).any():
        continue
    changes = int((np.diff(best) != 0).sum())
    cands.append((changes + np.ptp(lvl) / 20, pts))
cands.sort(key=lambda c: -c[0])
trajs = []
for score, pts in cands:
    if all(np.min(np.linalg.norm(pts[:, None] - t[None], axis=-1)) > 40 for t in trajs):
        trajs.append(pts)
    if len(trajs) == 3:
        break
print("trajectories:", len(trajs), [len(t) for t in trajs])

h = cfg["ue"]["height_m"]
allpts = np.vstack([np.c_[t, np.full(len(t), h)] for t in trajs])
cache = DATA / "_raw_mobility.npz"
if cache.exists() and len(ChannelSet.load(cache).pos) == len(allpts) and np.allclose(ChannelSet.load(cache).pos, allpts):
    mv = ChannelSet.load(cache)
else:
    mv = twin.trace(allpts, "twin", label="mobility"); mv.save(cache)
fill = cfg["raytracing"].get("fill", {})
mv.fill_unresolved(cfg["carrier"]["frequency_hz"], pool.meta["fill_calib_db"],
                   weak_db=fill.get("weak_db", 18.0), shadow_db=fill.get("shadow_db", 6.0))
mv.save(DATA / "mobility_traces.npz")

# ---------------------------------------------------------------- simulate along each trajectory
uniform = np.where(~np.array(pool.meta["is_hotspot"]))[0]
bg_idx = np.random.default_rng(1000).choice(uniform, cfg["experiments"]["num_ues"] - 1, replace=False)
bg = pool.subset(bg_idx)
active = np.ones(len(pool.ru_names), bool)
B1, T3 = list(STRATEGIES)[0], list(STRATEGIES)[4]
rows, events = [], []
off = 0
for ti, t in enumerate(trajs):
    prev_twin = None
    prev_b1 = None
    ttt, cand = 0, None
    for s in range(len(t)):
        step = mv.subset([off + s])
        net = ChannelSet.concat([bg, step])
        S, N, _ = rx_power(net, cfg, active)
        serv_t = assoc_twin_lb(net, active, S, N)
        u = net.U - 1
        if prev_twin is not None:
            # A3-like event for the moving UE: neighbour must be 3 dB better than the
            # serving RU for 2 consecutive steps (4 m, ~3 s time-to-trigger at walking speed)
            best = int(np.argmax(net.pg_db[u]))
            if best != prev_twin and net.pg_db[u, best] > net.pg_db[u, prev_twin] + 3.0:
                ttt = ttt + 1 if cand == best else 1
                cand = best
            else:
                ttt, cand = 0, None
            serv_t[u] = best if ttt >= 2 else prev_twin
            if ttt >= 2:
                ttt, cand = 0, None
        r_t = simulate(cfg, net, T3, forced_serving=serv_t, num_slots=12, rng=np.random.default_rng(s))
        r_b = simulate(cfg, net, B1, num_slots=12, rng=np.random.default_rng(s))
        if prev_twin is not None and serv_t[u] != prev_twin:
            events.append(dict(trajectory=ti + 1, distance_m=s * STEP, strategy="T3 twin",
                               from_ru=net.ru_names[prev_twin], to_ru=net.ru_names[serv_t[u]],
                               los_to_old=bool(net.los[u, prev_twin]), los_to_new=bool(net.los[u, serv_t[u]]),
                               rsrp_gain_db=round(float(net.pg_db[u, serv_t[u]] - net.pg_db[u, prev_twin]), 1)))
        if prev_b1 is not None and r_b["serving"][u] != prev_b1:
            events.append(dict(trajectory=ti + 1, distance_m=s * STEP, strategy="B1 nearest",
                               from_ru=net.ru_names[prev_b1], to_ru=net.ru_names[r_b["serving"][u]],
                               los_to_old=bool(net.los[u, prev_b1]), los_to_new=bool(net.los[u, r_b["serving"][u]]),
                               rsrp_gain_db=round(float(net.pg_db[u, r_b["serving"][u]] - net.pg_db[u, prev_b1]), 1)))
        prev_twin, prev_b1 = serv_t[u], r_b["serving"][u]
        row = dict(trajectory=ti + 1, step=s, distance_m=s * STEP, x=t[s, 0], y=t[s, 1],
                   serv_t3=net.ru_names[serv_t[u]], serv_b1=net.ru_names[r_b["serving"][u]],
                   thr_t3=r_t["thr_mbps"][u], thr_b1=r_b["thr_mbps"][u],
                   sinr_t3=r_t["sinr_db"][u], sinr_b1=r_b["sinr_db"][u],
                   bg_mean_thr_t3=r_t["thr_mbps"][:u].mean(), bg_mean_thr_b1=r_b["thr_mbps"][:u].mean())
        for r, name in enumerate(net.ru_names):
            row[f"rsrp_{name}"] = net.pg_db[u, r]
            row[f"los_{name}"] = bool(net.los[u, r])
        rows.append(row)
    off += len(t)
    print(f"trajectory {ti+1} simulated")

df = pd.DataFrame(rows)
p_re = cfg["ran"]["tx_power_dbm"] - 10 * np.log10(cfg["carrier"]["num_prb"] * 12)
for name in pool.ru_names:
    df[f"rsrp_{name}"] += p_re
df.to_csv(TAB / "t5_mobility_steps.csv", index=False)
ev = pd.DataFrame(events); ev.to_csv(TAB / "t5_reassignment_events.csv", index=False)
summ = df.groupby("trajectory")[["thr_t3", "thr_b1", "sinr_t3", "sinr_b1"]].mean().round(2)
summ["p10_thr_t3"] = df.groupby("trajectory").thr_t3.quantile(0.1).round(2)
summ["p10_thr_b1"] = df.groupby("trajectory").thr_b1.quantile(0.1).round(2)
summ["handovers_t3"] = ev[ev.strategy == "T3 twin"].groupby("trajectory").size().reindex(summ.index, fill_value=0) if len(ev) else 0
summ["handovers_b1"] = ev[ev.strategy == "B1 nearest"].groupby("trajectory").size().reindex(summ.index, fill_value=0) if len(ev) else 0
summ.to_csv(TAB / "t5_mobility_summary.csv")
print(summ.to_string())

# ---------------------------------------------------------------- figures
ext = [cc[..., 0].min(), cc[..., 0].max(), cc[..., 1].min(), cc[..., 1].max()]
hx = cov["hx"]; bld = cov["hmap"] > 0.5
fig, ax = plt.subplots(figsize=(7, 7))
rsrp_map = p_re + 10 * np.log10(pg.max(0) + 1e-30)
ax.imshow(np.where(pg.max(0) > 0, rsrp_map, np.nan), origin="lower", extent=ext, cmap=SEQ, vmin=-125, vmax=-65)
ax.imshow(np.where(bld, 1, np.nan), origin="lower", cmap="Greys", vmin=0, vmax=2, extent=[hx[0], hx[-1], hx[0], hx[-1]])
for ti, t in enumerate(trajs):
    ax.plot(*t.T, color=CAT[[1, 4, 6][ti]], lw=3)
    ax.annotate(f"Trajectory {ti+1}", t[0], xytext=(-10, 8), textcoords="offset points", weight="bold", fontsize=9)
    ax.scatter(*t[-1], marker=">", s=60, color=CAT[[1, 4, 6][ti]], zorder=5)
for s in cfg["ran"]["sites"]:
    ax.scatter(*s["xy"], s=110, marker="^", color=SITE_COLOR[s["name"]], edgecolor="black", zorder=6)
ax.set_xlim(-HALF - 30, HALF + 30); ax.set_ylim(-HALF - 30, HALF + 30); ax.set_aspect("equal"); ax.grid(False)
ax.set_title("UE trajectories over the twin's best-server RSRP map", loc="left")
save(fig, FIG / "fig10_trajectories.png")

fig, axs = plt.subplots(len(trajs), 2, figsize=(15, 3.6 * len(trajs)), squeeze=False)
for ti in range(len(trajs)):
    d = df[df.trajectory == ti + 1]
    top = d[[f"rsrp_{n}" for n in pool.ru_names]].max().sort_values(ascending=False).index[:4]
    ax = axs[ti, 0]
    for j, col in enumerate(top):
        name = col[5:]
        ax.plot(d.distance_m, d[col], color=CAT[j], label=f"RSRP from {name}")
        nl = ~d[f"los_{name}"].values
        ax.fill_between(d.distance_m, -150, -140, where=~nl, color=CAT[j], alpha=0.35, step="mid", lw=0)
    ax.set_ylim(-150, -55); ax.set_ylabel("RSRP [dBm]")
    ax.set_title(f"Trajectory {ti+1}: RSRP from the 4 strongest RUs (shaded band at bottom = LOS to that RU)", loc="left", fontsize=10)
    ax.legend(fontsize=8, ncol=2, loc="upper right")
    ax = axs[ti, 1]
    ax.plot(d.distance_m, d.thr_b1, "--", color=STRAT_COLOR["B1"], label="B1 baseline (nearest site)")
    ax.plot(d.distance_m, d.thr_t3, color=STRAT_COLOR["T3"], label="T3 twin-assisted")
    top = max(d.thr_t3.max(), d.thr_b1.max()) * 1.18
    for _, e in ev[(ev.trajectory == ti + 1) & (ev.strategy == "T3 twin")].iterrows():
        ax.axvline(e.distance_m, color=STRAT_COLOR["T3"], lw=0.8, ls=":")
        ax.annotate(f"{e.from_ru}->{e.to_ru}", (e.distance_m, top), fontsize=7, rotation=90, va="top",
                    ha="right", color=INK2)
    ax.set_ylim(0, top * 1.02)
    ax.set_ylabel("Moving UE throughput [Mbps]")
    ax.set_title("Moving UE throughput (dotted lines = twin re-association)", loc="left", fontsize=10)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.22) if ti == len(trajs) - 1 else (0.5, 1.0),
              ncol=2) if ti == len(trajs) - 1 else None
for ax in axs[-1]:
    ax.set_xlabel("Distance along trajectory [m]")
fig.tight_layout()
save(fig, FIG / "fig11_mobility_timeseries.png")
print("done")
