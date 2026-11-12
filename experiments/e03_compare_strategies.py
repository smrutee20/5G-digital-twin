"""
Tasks 3, 4 and 6: baseline vs twin-assisted allocation, Monte Carlo over UE drops.

Strategies (dt/alloc.py):
  B1  nearest site / sector by bearing + fixed equal PRB blocks          (baseline, fixed)
  B2  nearest site / sector by bearing + random PRBs every slot         (baseline, random)
  T1  max-RSRP association from the twin + fixed equal PRB blocks       (isolates association gain)
  T2  twin load-aware association + frequency-selective PF scheduling
  T3  T2 + twin-predicted inter-cell interference coordination (PRB muting)
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from dt.config import load_config, DATA, FIG, TAB
from dt.channel import ChannelSet
from dt.alloc import simulate, STRATEGIES, SHORT
from dt.kpi import summarize
from dt.plotstyle import plt, save, STRAT_COLOR, STRAT_STYLE, SITE_COLOR, CAT, INK2, GRID

cfg = load_config()
E = cfg["experiments"]
ch = ChannelSet.load(DATA / "twin_pool.npz")
uniform = np.where(~np.array(ch.meta["is_hotspot"]))[0]
names = list(STRATEGIES)

rows, per_ue, examples = [], {s: dict(thr=[], sinr=[], interf=[], geo=[]) for s in names}, {}
for d in range(E["num_drops"]):
    idx = np.random.default_rng(1000 + d).choice(uniform, E["num_ues"], replace=False)
    sub = ch.subset(idx)
    for s in names:
        res = simulate(cfg, sub, s, rng=np.random.default_rng(d))
        k = summarize(res)
        k.update(drop=d, strategy=SHORT[s])
        k["not_nearest_site_pct"] = None
        rows.append(k)
        for f, key in [("thr", "thr_mbps"), ("sinr", "sinr_db"), ("interf", "interf_dbm"), ("geo", "geo_sinr_db")]:
            per_ue[s][f].append(res[key])
        if d == 0:
            examples[s] = dict(res=res, idx=idx, sub=sub)
    print(f"drop {d+1}/{E['num_drops']} done")

df = pd.DataFrame(rows)
df.to_csv(TAB / "t6_kpi_per_drop.csv", index=False)
metrics = ["mean_thr_mbps", "p5_thr_mbps", "p50_thr_mbps", "sum_thr_mbps", "mean_sinr_db", "p5_sinr_db",
           "mean_interf_dbm", "mean_cqi", "prb_util_pct", "jain", "outage_pct", "cell_se_bps_hz"]
g = df.groupby("strategy")[metrics]
ci = 1.96 * g.std() / np.sqrt(E["num_drops"])
summ = g.mean().round(3)
summ.to_csv(TAB / "t6_kpi_summary.csv")
(ci.round(3)).to_csv(TAB / "t6_kpi_ci95.csv")
def change(a, b):
    """Relative change for linear KPIs, absolute difference for dB / % / index KPIs."""
    out = {}
    for m in metrics:
        if m.endswith(("_db", "_dbm", "_pct")) or m == "jain":
            out[m + " (abs diff)"] = round(float(summ.loc[a, m] - summ.loc[b, m]), 2)
        elif summ.loc[b, m] > 0:
            out[m + " (% change)"] = round(float((summ.loc[a, m] / summ.loc[b, m] - 1) * 100), 1)
        else:
            out[m + " (abs diff)"] = round(float(summ.loc[a, m] - summ.loc[b, m]), 2)
    return out
print(summ.T.to_string())
json.dump({"T3 vs B1": change("T3", "B1"), "T2 vs B1": change("T2", "B1"), "T1 vs B1": change("T1", "B1")},
          open(TAB / "t6_gains.json", "w"), indent=2)

# ---------------------------------------------------------------- Fig 6: association map (drop 0)
cov = np.load(DATA / "coverage.npz"); hx = cov["hx"]; bld = cov["hmap"] > 0.5
fig, axs = plt.subplots(1, 2, figsize=(13, 6.5))
for ax, s in zip(axs, [names[0], names[4]]):
    ex = examples[s]; sub, res = ex["sub"], ex["res"]
    ax.imshow(np.where(bld, 1, np.nan), origin="lower", cmap="Greys", vmin=0, vmax=3,
              extent=[hx[0], hx[-1], hx[0], hx[-1]])
    for u in range(sub.U):
        rr = res["serving"][u]
        col = SITE_COLOR[sub.ru_names[rr][0]]
        ax.plot([sub.pos[u, 0], sub.ru_pos[rr, 0]], [sub.pos[u, 1], sub.ru_pos[rr, 1]], color=col, lw=1, alpha=0.7)
        ax.scatter(*sub.pos[u, :2], s=30 + 4 * res["thr_mbps"][u] ** 0.8, color=col, edgecolor="white", lw=1, zorder=4)
    for sname, xy in [(x["name"], x["xy"]) for x in cfg["ran"]["sites"]]:
        ax.scatter(*xy, s=120, marker="^", color=SITE_COLOR[sname], edgecolor="black", zorder=5)
    L = cfg["scene"]["half"] + 30
    ax.set_xlim(-L, L); ax.set_ylim(-L, L); ax.set_aspect("equal"); ax.grid(False)
    ax.set_title(f"{SHORT[s]}: {s.split(' ', 1)[1]}\nmean {res['thr_mbps'].mean():.0f} Mbps, "
                 f"5th pct {np.percentile(res['thr_mbps'], 5):.1f} Mbps", loc="left", fontsize=10)
fig.suptitle("Who serves whom (marker size ~ UE throughput, colour = serving site)", x=0.07, ha="left", weight="bold")
save(fig, FIG / "fig06_association_b1_vs_t3.png")

# ---------------------------------------------------------------- Fig 7: CDFs
fig, axs = plt.subplots(1, 3, figsize=(16, 4.6))
for s in names:
    k = SHORT[s]
    for ax, f, xl in [(axs[0], "thr", "UE throughput [Mbps]"), (axs[1], "sinr", "Effective SINR on scheduled PRBs [dB]"),
                      (axs[2], "interf", "Interference on scheduled PRBs [dBm/PRB]")]:
        v = np.sort(np.concatenate(per_ue[s][f])); v = v[np.isfinite(v)]
        ax.plot(v, np.linspace(0, 1, len(v)), STRAT_STYLE[k], color=STRAT_COLOR[k], label=s)
        ax.set_xlabel(xl); ax.set_ylabel("CDF")
axs[0].set_xscale("symlog", linthresh=1); axs[0].set_xlim(0, None)
axs[0].set_title("UE throughput", loc="left"); axs[1].set_title("SINR", loc="left")
axs[2].set_title("Interference (lower is better)", loc="left")
axs[0].axhline(0.05, color=INK2, lw=0.8, ls=":"); axs[0].annotate("cell edge (5%)", (1.1, 0.07), fontsize=8, color=INK2)
handles, labels = axs[0].get_legend_handles_labels()
fig.legend(handles, labels, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.12), fontsize=9)
save(fig, FIG / "fig07_cdfs.png")

# ---------------------------------------------------------------- Fig 8: KPI dot plots with 95% CI
show = [("mean_thr_mbps", "Mean UE throughput [Mbps]"), ("p5_thr_mbps", "Cell-edge (5th pct) throughput [Mbps]"),
        ("mean_sinr_db", "Mean effective SINR [dB]"), ("mean_interf_dbm", "Mean interference [dBm/PRB]"),
        ("prb_util_pct", "PRB utilisation [%]"), ("jain", "Jain fairness index")]
fig, axs = plt.subplots(2, 3, figsize=(15, 6.5))
order = [SHORT[s] for s in names]
for ax, (m, lab) in zip(axs.ravel(), show):
    for i, k in enumerate(order):
        ax.errorbar(summ.loc[k, m], i, xerr=ci.loc[k, m], fmt="o", ms=8, color=STRAT_COLOR[k],
                    ecolor=STRAT_COLOR[k], capsize=3, lw=2)
        ax.annotate(f"{summ.loc[k, m]:.3g}", (summ.loc[k, m], i), xytext=(0, 9), textcoords="offset points",
                    ha="center", fontsize=8, color=INK2)
    ax.set_yticks(range(len(order))); ax.set_yticklabels(order); ax.invert_yaxis()
    ax.set_title(lab, loc="left", fontsize=10); ax.set_ylim(len(order) - 0.4, -0.7)
fig.suptitle(f"Baseline vs twin-assisted allocation: mean over {E['num_drops']} drops of {E['num_ues']} UEs (bars = 95% CI)",
             x=0.07, ha="left", weight="bold")
fig.tight_layout()
save(fig, FIG / "fig08_kpi_comparison.png")

# ---------------------------------------------------------------- Fig 9: resource grid (one slot)
fig, axs = plt.subplots(2, 1, figsize=(13, 5.2), sharex=True)
for ax, s in zip(axs, [names[0], names[4]]):
    A = examples[s]["res"]["last_assign"].astype(float)
    lab = np.full(A.shape, np.nan)
    for r in range(A.shape[0]):           # recolour UEs per cell 0..n-1 so the grid is readable
        us = [u for u in np.unique(A[r]) if u >= 0]
        for j, u in enumerate(us):
            lab[r, A[r] == u] = j % 8
    from matplotlib.colors import ListedColormap
    ax.imshow(np.where(A < 0, np.nan, lab), aspect="auto", cmap=ListedColormap(CAT), vmin=-0.5, vmax=7.5,
              interpolation="nearest")
    ax.imshow(np.where(A < 0, 1, np.nan), aspect="auto", cmap=ListedColormap(["#d8d7d2"]), interpolation="nearest")
    ax.set_yticks(range(len(examples[s]["sub"].ru_names))); ax.set_yticklabels(examples[s]["sub"].ru_names, fontsize=8)
    ax.grid(False)
    muted = 100 * (A < 0).mean()
    ax.set_title(f"{SHORT[s]}: PRB grid in one slot (colour = UE within the cell, grey = PRB not used, {muted:.0f}%)",
                 loc="left", fontsize=10)
axs[1].set_xlabel("PRB index")
save(fig, FIG / "fig09_prb_grid.png")
print("done")
