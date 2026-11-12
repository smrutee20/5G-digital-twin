"""
Task 6: compare B1, B2 and the Twin on SINR, throughput (mean and 5th percentile), interference and PRB
utilisation, over 20 random UE placements ("drops"), reported as mean ± 95 % confidence interval.
Drop 1 is task 2's UEs; drops 2-20 were ray-traced by task 2 too.
Run after task 2:  python tasks/task6_compare.py   (--quick: 20 drops of 30 UEs, fewer rays)
"""
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from twin import scene as sc
from twin import radio
from twin.allocation import run
from twin.twin_data import save_demo_part

DROPS = 20
T_95 = 2.093                                    # Student t for 95 % with 20 - 1 = 19 degrees of freedom
COLOURS = {"B1": "#9ca3af", "B2": "#d97706", "Twin": "#2563eb"}
data, results = sc.folders()

# 1. the 20 drops of task 2: its first placement, and the 19 more it traced
first = np.load(data / "measurements.npz")
more = np.load(data / "drops.npz")
drops = [(first["ue_xy"], first["path_gain_db"])] + list(zip(more["ue_xy"], more["path_gain_db"]))

# 2. run the three strategies on every drop; keep each drop's KPIs and every UE's throughput and SINR
kpis = {name: [] for name in COLOURS}
every_ue = {name: {"throughput_mbps": [], "sinr_db": []} for name in COLOURS}
for d, (xy, gain_db) in enumerate(drops):
    rx = radio.prb_power_mw(gain_db)
    for name in COLOURS:
        result = run(name, rx, xy, rng=np.random.default_rng(d))
        kpis[name].append(radio.kpis(result))
        for key in every_ue[name]:
            every_ue[name][key].append(result[key])

# 3. mean and 95 % confidence interval over the drops
metrics = list(kpis["B1"][0])
summary = {}
for name in COLOURS:
    for k in metrics:
        values = np.array([drop[k] for drop in kpis[name]])
        summary[name, k] = (values.mean(), T_95 * values.std(ddof=1) / np.sqrt(DROPS))

# 4. the table: printed, and saved as CSV
print(f"{len(drops)} drops of {len(first['ue_xy'])} UEs, mean ± 95 % confidence interval")
print(f"{'':34s}" + "".join(f"{n:>16s}" for n in COLOURS))
for k in metrics:
    print(f"{k:34s}" + "".join(f"{summary[n, k][0]:9.2f} ±{summary[n, k][1]:5.2f}" for n in COLOURS))
with open(results / "task6_comparison.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["metric"] + [f"{n} {part}" for n in COLOURS for part in ("mean", "ci95")])
    for k in metrics:
        w.writerow([k] + [round(v, 3) for n in COLOURS for v in summary[n, k]])


# 5. plots 1 and 2: throughput and SINR of every UE in every drop (CDF: share of UEs below a value)
def cdf_plot(key, label, filename, log=False):
    fig, ax = plt.subplots(figsize=(6, 4))
    for name in COLOURS:
        values = np.concatenate(every_ue[name][key])
        values = np.sort(values[~np.isnan(values)])           # a UE that got no PRB has no SINR
        if log:
            values = np.maximum(values, 0.01)                 # 0 Mbps is drawn at 0.01 on the log axis
        share = np.arange(1, len(values) + 1) / len(values)
        ax.plot(values, share, label=name, color=COLOURS[name], lw=2)
    if log:
        ax.set_xscale("log")
    ax.set_xlabel(label)
    ax.set_ylabel("share of UEs below")
    ax.set_title(f"all UEs of {len(drops)} drops", fontsize=9)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(results / filename, dpi=130)
    plt.close(fig)


cdf_plot("throughput_mbps", "UE throughput (Mbps)", "task6_throughput_cdf.png", log=True)
cdf_plot("sinr_db", "UE SINR (dB)", "task6_sinr_cdf.png")

# 6. plot 3: mean and 5th-percentile throughput with their 95 % confidence intervals
fig, ax = plt.subplots(figsize=(6, 4))
x = np.arange(len(COLOURS))
for offset, k, alpha, label in [(-0.2, "mean throughput (Mbps)", 1.0, "mean"),
                                (0.2, "5th-percentile throughput (Mbps)", 0.5, "5th percentile")]:
    ax.bar(x + offset, [summary[n, k][0] for n in COLOURS], 0.4, yerr=[summary[n, k][1] for n in COLOURS],
           capsize=4, color=list(COLOURS.values()), alpha=alpha, label=label)
ax.set_xticks(x, list(COLOURS))
ax.set_ylabel("throughput (Mbps)")
ax.set_title(f"mean of {len(drops)} drops, bars = 95 % confidence interval", fontsize=9)
ax.legend()
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(results / "task6_throughput_bars.png", dpi=130)
print(f"saved task6_comparison.csv and 3 plots in {results}")

# 7. for the demo's Strategies tab (full study only): 30 UEs of drop 1, what each strategy does with them,
#    what each UE measures from every sector, and the table above
if not sc.quick():
    n = 30
    xy, gain_db = drops[0][0][:n], drops[0][1][:n]
    rx = radio.prb_power_mw(gain_db)
    no_nan = lambda a: [None if np.isnan(v) else round(float(v), 1) for v in a]     # JavaScript has no NaN in JSON
    strategies = {}
    for name in COLOURS:
        r = run(name, rx, xy, rng=np.random.default_rng(0))
        strategies[name] = {"serving": r["serving"].tolist(), "prb_plan": r["prb_plan"].tolist(),
                            "throughput_mbps": np.round(r["throughput_mbps"], 2).tolist(), "sinr_db": no_nan(r["sinr_db"])}
    sinr_each = radio.to_db(rx / (rx.sum(1, keepdims=True) - rx + radio.noise_mw()))  # if that sector served it
    save_demo_part("strategies", {
        "ue_xy": np.round(xy, 1).tolist(), "rsrp_dbm": np.round(radio.rsrp_dbm(gain_db), 1).tolist(),
        "sinr_db": np.round(sinr_each, 1).tolist(), "los": first["los"][:n].tolist(), "strategies": strategies,
        "kpis": {name: {k: [round(m, 2), round(c, 2)] for (s, k), (m, c) in summary.items() if s == name} for name in COLOURS},
        "drops": len(drops), "ues_per_drop": len(first["ue_xy"])})
    print("saved the Strategies tab's data in data/demo_tasks.json")
