"""
Task 7: what-if analysis -- predict network KPIs with the twin BEFORE applying a change,
then 'apply' the same configuration to the physical-network stand-in and measure how
good the prediction was.

  Twin prediction : decisions + KPIs on the twin at the GPS-noisy UE positions it knows,
                    synchronised with UE measurement reports (top-8 SS-RSRP, 1 dB, ~2 dB error)
  Uncalibrated    : same decisions, KPIs predicted by the twin without measurement sync
  Actual          : the twin's decisions applied to the physical network
                    (deeper ray tracing + diffuse scattering + shadowing + fading + true positions)
  Statistical     : same decisions, KPIs predicted with a non-site-specific 3GPP 38.901 model
                    (what you would get without a digital twin)
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from dt.config import load_config, DATA, FIG, TAB
from dt.channel import ChannelSet, statistical_channel, calibrate_with_measurements
from dt.alloc import simulate, STRATEGIES, rx_power, assoc_twin_lb, assoc_nearest
from dt.kpi import summarize
from dt.plotstyle import plt, save, CAT, INK2, STRAT_COLOR

cfg = load_config()
fc = cfg["carrier"]["frequency_hz"]
twin_true = ChannelSet.load(DATA / "twin_pool.npz")
twin_raw = ChannelSet.load(DATA / "twin_est_pool.npz")
phys = ChannelSet.load(DATA / "physical_pool.npz")
twin = calibrate_with_measurements(twin_raw, phys, np.random.default_rng(3))
stat = statistical_channel(twin, fc)
hot = np.array(twin.meta["is_hotspot"])
uniform, hotspot = np.where(~hot)[0], np.where(hot)[0]
B1, T3 = list(STRATEGIES)[0], list(STRATEGIES)[4]
R = len(twin.ru_names)
DROPS = 10
NPRB_40 = 106                       # 40 MHz @ 30 kHz (TS 38.101-1)
siteB = twin.ru_site == 1

SCEN = [
    dict(id="S0", name="Current: 30 UEs, 9 RUs, 100 MHz", n=30),
    dict(id="S1", name="UE density x2 (60 UEs)", n=60),
    dict(id="S2", name="UE density x3.3 (100 UEs)", n=100),
    dict(id="S3", name="Event hotspot: +40 UEs in a 45 m radius", n=30, hot=40),
    dict(id="S4", name="Carrier reduced to 40 MHz", n=30, prb=NPRB_40),
    dict(id="S5", name="Energy saving: site B switched off", n=30, off=siteB),
    dict(id="S6", name="Roll back to baseline scheduler (B1)", n=30, strat=B1),
]
METRICS = [("mean_thr_mbps", "Mean UE throughput [Mbps]"), ("p5_thr_mbps", "5th-pct UE throughput [Mbps]"),
           ("mean_sinr_db", "Mean SINR [dB]"), ("prb_util_pct", "PRB utilisation [%]"),
           ("outage_pct", "Outage (<1 Mbps) [%]")]


def run(sc, d):
    rng = np.random.default_rng(5000 + d)
    idx = rng.choice(uniform, sc["n"], replace=False)
    if sc.get("hot"):
        idx = np.r_[idx, rng.choice(hotspot, sc["hot"], replace=False)]
    sets = {k: c.subset(idx) for k, c in [("twin", twin), ("phys", phys), ("stat", stat), ("raw", twin_raw)]}
    if sc.get("prb"):
        sets = {k: c.with_prbs(sc["prb"]) for k, c in sets.items()}
    active = ~sc["off"] if sc.get("off") is not None else np.ones(R, bool)
    strat = sc.get("strat", T3)
    # the configuration decided by the twin (association is part of what gets applied)
    S, N, _ = rx_power(sets["twin"], cfg, active)
    serv = assoc_nearest(sets["twin"], active) if STRATEGIES[strat]["assoc"] == "nearest" \
        else assoc_twin_lb(sets["twin"], active, S, N)
    out = {}
    for k, ev in [("pred_twin", "twin"), ("pred_uncal", "raw"), ("pred_stat", "stat"), ("actual", "phys")]:
        res = simulate(cfg, sets[ev], strat, ch_decide=sets["twin"], active_rus=active,
                       forced_serving=serv, rng=np.random.default_rng(d))
        out[k] = res
    return out


rows, per_ue = [], {}
for sc in SCEN:
    for d in range(DROPS):
        out = run(sc, d)
        for k, res in out.items():
            s = summarize(res); s.update(scenario=sc["id"], kind=k, drop=d)
            rows.append(s)
        if sc["id"] == "S0":
            per_ue.setdefault("pred", []).append(out["pred_twin"]["thr_mbps"])
            per_ue.setdefault("stat", []).append(out["pred_stat"]["thr_mbps"])
            per_ue.setdefault("uncal", []).append(out["pred_uncal"]["thr_mbps"])
            per_ue.setdefault("act", []).append(out["actual"]["thr_mbps"])
    print("scenario", sc["id"], "done")

df = pd.DataFrame(rows)
df.to_csv(TAB / "t7_whatif_per_drop.csv", index=False)
mean = df.groupby(["scenario", "kind"])[[m for m, _ in METRICS]].mean()
tab = []
for sc in SCEN:
    for m, lab in METRICS:
        a = mean.loc[(sc["id"], "actual"), m]
        pt = mean.loc[(sc["id"], "pred_twin"), m]
        ps = mean.loc[(sc["id"], "pred_stat"), m]
        pu = mean.loc[(sc["id"], "pred_uncal"), m]
        tab.append(dict(scenario=sc["id"], description=sc["name"], metric=lab, predicted_twin=round(pt, 2),
                        predicted_twin_uncal=round(pu, 2), predicted_38901=round(ps, 2), actual=round(a, 2),
                        abs_err_twin=round(abs(pt - a), 2), abs_err_twin_uncal=round(abs(pu - a), 2),
                        abs_err_38901=round(abs(ps - a), 2)))
tab = pd.DataFrame(tab)
tab.to_csv(TAB / "t7_whatif_summary.csv", index=False)

# change relative to the current configuration: does the twin predict the DIRECTION and size correctly?
delta = []
for sc in SCEN[1:]:
    for m, lab in METRICS[:2]:
        base_p, base_a = mean.loc[("S0", "pred_twin"), m], mean.loc[("S0", "actual"), m]
        base_s = mean.loc[("S0", "pred_stat"), m]
        dp = 100 * (mean.loc[(sc["id"], "pred_twin"), m] / base_p - 1)
        da = 100 * (mean.loc[(sc["id"], "actual"), m] / base_a - 1)
        ds = 100 * (mean.loc[(sc["id"], "pred_stat"), m] / base_s - 1)
        du = 100 * (mean.loc[(sc["id"], "pred_uncal"), m] / mean.loc[("S0", "pred_uncal"), m] - 1)
        delta.append(dict(scenario=sc["id"], description=sc["name"], metric=lab,
                          predicted_change_twin_pct=round(dp, 1), predicted_change_twin_uncal_pct=round(du, 1),
                          predicted_change_38901_pct=round(ds, 1), actual_change_pct=round(da, 1)))
delta = pd.DataFrame(delta)
delta.to_csv(TAB / "t7_whatif_deltas.csv", index=False)
print(tab.to_string()); print(delta.to_string())

# ---------------------------------------------------------------- Fig 12: predicted vs actual per scenario
fig, axs = plt.subplots(1, 3, figsize=(16, 5.2))
ids = [s["id"] for s in SCEN]
for ax, (m, lab) in zip(axs, [METRICS[0], METRICS[1], METRICS[2]]):
    for j, (k, col, mk, name) in enumerate([("actual", "#0b0b0b", "o", "Actual (physical network)"),
                                            ("pred_twin", CAT[0], "D", "Twin + measurement sync"),
                                            ("pred_uncal", CAT[2], "v", "Twin, no sync"),
                                            ("pred_stat", CAT[1], "s", "38.901 statistical")]):
        v = [mean.loc[(i, k), m] for i in ids]
        ax.scatter(v, np.arange(len(ids)) + (j - 1.5) * 0.17, marker=mk, s=40, color=col, label=name, zorder=3)
    ax.set_yticks(range(len(ids))); ax.set_yticklabels([f"{s['id']} {s['name']}" if ax is axs[0] else s["id"] for s in SCEN], fontsize=8)
    ax.invert_yaxis(); ax.set_title(lab, loc="left", fontsize=10)
axs[0].legend(loc="lower center", bbox_to_anchor=(1.6, -0.28), ncol=4, fontsize=9)
fig.suptitle("What-if: KPIs predicted before applying each change vs what the network then delivers",
             x=0.02, ha="left", weight="bold")
save(fig, FIG / "fig12_whatif_pred_vs_actual.png")

# ---------------------------------------------------------------- Fig 13: prediction error
fig, axs = plt.subplots(1, 3, figsize=(16, 4.4))
for ax, (m, lab) in zip(axs, METRICS[:3]):
    t = tab[tab.metric == lab]
    x = np.arange(len(t))
    for j, (col, c, name) in enumerate([("abs_err_twin", CAT[0], "Twin + measurement sync"),
                                        ("abs_err_twin_uncal", CAT[2], "Twin, no sync"),
                                        ("abs_err_38901", CAT[1], "38.901 statistical")]):
        ax.bar(x + (j - 1) * 0.27, t[col], 0.25, color=c, label=name)
    ax.set_xticks(x); ax.set_xticklabels(t.scenario)
    ax.set_ylabel("|predicted - actual|"); ax.set_title(lab, loc="left", fontsize=10)
axs[0].legend(fontsize=8)
fig.suptitle("Absolute prediction error vs the physical network, per what-if scenario (lower is better)",
             x=0.02, ha="left", weight="bold")
save(fig, FIG / "fig13_whatif_error.png")

# ---------------------------------------------------------------- Fig 14: per-UE accuracy
a = np.concatenate(per_ue["act"]); p = np.concatenate(per_ue["pred"]); s = np.concatenate(per_ue["stat"])
uc = np.concatenate(per_ue["uncal"])
fig, axs = plt.subplots(1, 3, figsize=(16, 5.2), sharey=True)
lim = [0.05, max(a.max(), p.max(), s.max(), uc.max()) * 1.3]
for ax, v, col, name in [(axs[0], p, CAT[0], "Twin + measurement sync"), (axs[1], uc, CAT[2], "Twin, no sync"),
                         (axs[2], s, CAT[1], "38.901 statistical")]:
    ax.scatter(np.maximum(v, 0.05), np.maximum(a, 0.05), s=10, color=col, alpha=0.6)
    ax.plot(lim, lim, color=INK2, lw=1)
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(lim); ax.set_ylim(lim)
    r = np.corrcoef(np.log(np.maximum(v, .05)), np.log(np.maximum(a, .05)))[0, 1]
    ax.set_title(f"{name} prediction (log-corr {r:.2f})", loc="left", fontsize=10)
    ax.set_xlabel("Predicted UE throughput [Mbps]")
axs[0].set_ylabel("Actual UE throughput [Mbps]")
fig.suptitle("Per-UE throughput: predicted before deployment vs measured after (S0, 10 drops)",
             x=0.02, ha="left", weight="bold")
save(fig, FIG / "fig14_whatif_per_ue.png")
lc = lambda v: float(np.corrcoef(np.log(np.maximum(v, .05)), np.log(np.maximum(a, .05)))[0, 1])
dl = delta[delta.metric.str.startswith("Mean")]
json.dump(dict(per_ue_logcorr_twin_sync=lc(p), per_ue_logcorr_twin_nosync=lc(uc), per_ue_logcorr_38901=lc(s),
               mean_thr_mae_twin_sync=float(tab[tab.metric.str.startswith("Mean UE")].abs_err_twin.mean()),
               mean_thr_mae_twin_nosync=float(tab[tab.metric.str.startswith("Mean UE")].abs_err_twin_uncal.mean()),
               mean_thr_mae_38901=float(tab[tab.metric.str.startswith("Mean UE")].abs_err_38901.mean()),
               change_mae_pp_twin_sync=float((dl.predicted_change_twin_pct - dl.actual_change_pct).abs().mean()),
               change_mae_pp_twin_nosync=float((dl.predicted_change_twin_uncal_pct - dl.actual_change_pct).abs().mean()),
               change_mae_pp_38901=float((dl.predicted_change_38901_pct - dl.actual_change_pct).abs().mean())),
          open(TAB / "t7_accuracy.json", "w"), indent=2)
print("done")
