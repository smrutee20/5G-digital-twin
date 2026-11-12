"""
Task 6 (extension): how accurate does the twin have to be for twin-assisted allocation
to pay off on the physical network?

Decisions are made on progressively less perfect twins and always scored on the
physical network. 'Oracle' = the twin is the physical network.
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from dt.config import load_config, DATA, FIG, TAB
from dt.channel import ChannelSet, calibrate_with_measurements
from dt.alloc import simulate, STRATEGIES
from dt.kpi import summarize
from dt.plotstyle import plt, save, STRAT_COLOR, INK2

cfg = load_config()
twin = ChannelSet.load(DATA / "twin_pool.npz")
est = ChannelSet.load(DATA / "twin_est_pool.npz")
phys = ChannelSet.load(DATA / "physical_pool.npz")
cal = calibrate_with_measurements(est, phys, np.random.default_rng(3))
uni = np.where(~np.array(twin.meta["is_hotspot"]))[0]
B1, T3 = list(STRATEGIES)[0], list(STRATEGIES)[4]
DROPS = 15

LADDER = [
    ("Oracle twin (= physical network)", phys),
    ("Twin + measurement sync (noisy positions)", cal),
    ("Twin at true UE positions", twin),
    ("Twin at GPS positions (5 m error)", est),
]
agree = {}
rows = []
for name, dec in LADDER:
    agree[name] = float((np.argmax(dec.pg_db[uni], 1) == np.argmax(phys.pg_db[uni], 1)).mean())
    for st in [B1, T3]:
        for d in range(DROPS):
            idx = np.random.default_rng(7000 + d).choice(uni, cfg["experiments"]["num_ues"], replace=False)
            k = summarize(simulate(cfg, phys.subset(idx), st, ch_decide=dec.subset(idx), rng=np.random.default_rng(d)))
            rows.append(dict(twin=name, strategy=st.split()[0], drop=d, **k))
    print(name, "done")
df = pd.DataFrame(rows)
summ = df.groupby(["twin", "strategy"])[["mean_thr_mbps", "p5_thr_mbps", "mean_sinr_db", "outage_pct"]].mean().round(2)
summ = summ.reindex([n for n, _ in LADDER], level=0)
summ["best_server_agreement"] = [agree[i[0]] for i in summ.index]
summ.to_csv(TAB / "t6_twin_fidelity.csv")
print(summ.to_string())

names = [n for n, _ in LADDER]
fig, axs = plt.subplots(1, 3, figsize=(16, 4.2), sharey=True)
for ax, (m, lab) in zip(axs, [("mean_thr_mbps", "Mean UE throughput [Mbps]"),
                              ("p5_thr_mbps", "Cell-edge (5th pct) throughput [Mbps]"),
                              ("outage_pct", "Outage, UEs < 1 Mbps [%]")]):
    for i, n in enumerate(names):
        b, t = summ.loc[(n, "B1"), m], summ.loc[(n, "T3"), m]
        ax.plot([b, t], [i, i], color="#d8d7d2", lw=3, zorder=1)
        ax.scatter(b, i, s=70, color=STRAT_COLOR["B1"], zorder=3, label="B1 baseline" if i == 0 else None)
        ax.scatter(t, i, s=70, color=STRAT_COLOR["T3"], zorder=3, label="T3 twin-assisted" if i == 0 else None)
        ax.annotate(f"{t:.1f}", (t, i), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8, color=INK2)
    ax.set_title(lab, loc="left", fontsize=10)
axs[0].set_yticks(range(len(names)))
axs[0].set_yticklabels([f"{n}\n(best-server match {agree[n]:.0%})" for n in names], fontsize=8)
axs[0].invert_yaxis()
axs[0].legend(loc="lower right", fontsize=8)
fig.suptitle("Value of the twin depends on its fidelity: decisions from each twin, KPIs measured on the physical network",
             x=0.02, ha="left", weight="bold")
fig.tight_layout()
save(fig, FIG / "fig16_twin_fidelity.png")
