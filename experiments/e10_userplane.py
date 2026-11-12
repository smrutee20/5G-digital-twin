"""
User-plane traffic end to end: DN server -> UPF -> GTP-U (N3) -> CU-UP -> F1-U -> DU scheduler -> RU -> UE,
for the baseline B1 and the twin-assisted T3 on the SAME UEs with the SAME packet streams.

Air-interface throughput and delay come from the radio twin: every 20 ms epoch the DU's scheduler
(dt.alloc.simulate, unchanged) gives each UE a capacity from its per-PRB SINR -> CQI on the PRBs it was
allocated; the DU serves its RLC queue at that rate slot by slot, plus HARQ retransmissions.

Outputs (results/<tag>/):
  tables/t10_userplane_kpis.csv     per strategy: latency percentiles, PDB compliance, throughput, loss
  tables/t10_latency_budget.csv     per hop, per strategy: mean / p50 / p95 delay contribution
  tables/t10_per_ue.csv             per UE and strategy: radio (SINR, PRBs, CQI, capacity), throughput, latency
  tables/t10_load_sweep.csv         the same KPIs for 5 / 10 / 20 / 40 Mbps per UE
  tables/t10_checks.json
  figures/fig18_e2e_latency_cdf.png, fig19_latency_budget.png, fig20_latency_vs_load.png
"""
import sys, copy, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from dt.config import load_config, DATA, FIG, TAB
from dt.e2e import E2ENetwork
from dt.e2e.userplane import Batch, COMPONENTS, GROUP
from dt.plotstyle import plt, save, STRAT_COLOR, STRAT_STYLE, INK2

cfg0 = load_config()
E = cfg0["e2e"]
PDB = float(E["pdb_ms"])
STRATS = ["B1", "T3"]
LOADS = [5, 10, 20, 40]


def run(strategy, rate):
    cfg = copy.deepcopy(cfg0)
    cfg["e2e"]["traffic"]["rate_mbps"] = rate
    return E2ENetwork(cfg, DATA, strategy).run()


def all_packet_latency(net, ue, cutoff):
    """Latency of every packet the DN generated before `cutoff`; inf if it had not arrived by the end."""
    gen = np.concatenate(net.dn.sent_gen.get(ue.name, [np.array([])]))
    gen = gen[gen <= cutoff]
    b = Batch.concat(ue.rx)
    lat, ran = np.full(len(gen), np.inf), np.full(len(gen), np.inf)
    if len(b) and len(gen):
        pos = {g: i for i, g in enumerate(b.gen)}
        for i, g in enumerate(gen):
            j = pos.get(g)
            if j is not None:
                lat[i] = b.t[j] - b.gen[j]
                ran[i] = lat[i] - b.comp["n6"][j]
    return lat, ran


def kpis(net, rate):
    rx = Batch.concat([b for u in net.ues for b in u.rx])
    sent_pkts = sum(net.dn.sent.values()) / int(E["traffic"]["packet_bytes"])
    dropped = sum(du.dropped for du in net.dus.values())
    end = net.n_epochs * net.epoch_ms
    cutoff = end - PDB                 # packets generated later may legitimately still be on their way
    rows, rl, L, RAN = [], pd.DataFrame(net.radio_log), [], []
    for u in net.ues:
        b = Batch.concat(u.rx)
        f = net.dn.flows.get(u.name)
        start = f["start"] if f else end
        dur_s = (end - start) / 1e3
        r = rl[(rl.ue == u.name) & (rl.epoch * net.epoch_ms > start)]
        l, ran = all_packet_latency(net, u, cutoff)
        L.append(l); RAN.append(ran)
        rows.append(dict(ue=u.name, serving_ru=r.serving_ru.iloc[0] if len(r) else None,
                         sinr_db=r.sinr_db.mean(), prbs_per_slot=r.prbs_per_slot.mean(), cqi=r.cqi.mean(),
                         capacity_mbps=r.capacity_mbps.mean(),
                         offered_mbps=net.dn.sent.get(u.name, 0) * 8 / dur_s / 1e6 if dur_s > 0 else 0,
                         delivered_mbps=b.bytes * 8 / dur_s / 1e6 if dur_s > 0 else 0,
                         lat_p50_ms=np.percentile(l, 50, method="nearest") if len(l) else np.nan,
                         lat_p95_ms=np.percentile(l, 95, method="nearest") if len(l) else np.nan,
                         within_pdb_pct=100 * np.mean(ran <= PDB) if len(ran) else 0.0,
                         undelivered_pct=100 * np.mean(~np.isfinite(l)) if len(l) else 0.0))
    lat, ran_core = np.concatenate(L), np.concatenate(RAN)
    ue = pd.DataFrame(rows)
    ue["meets_demand"] = (ue.delivered_mbps >= 0.95 * ue.offered_mbps) & (ue.within_pdb_pct >= 99)
    summ = dict(
        offered_mbps_per_ue=rate, packets_sent=int(sent_pkts), packets_delivered=len(rx),
        delivered_pct=100 * len(rx) / sent_pkts, dropped_bytes=int(dropped),
        lat_p50_ms=float(np.percentile(lat, 50, method="nearest")), lat_p95_ms=float(np.percentile(lat, 95, method="nearest")),
        lat_p99_ms=float(np.percentile(lat, 99, method="nearest")), packets_counted=len(lat),
        packets_not_delivered_pct=float(100 * np.mean(~np.isfinite(lat))),
        within_pdb_pct=float(100 * np.mean(ran_core <= PDB)),
        mean_delivered_mbps=float(ue.delivered_mbps.mean()), p5_delivered_mbps=float(ue.delivered_mbps.quantile(0.05)),
        mean_capacity_mbps=float(ue.capacity_mbps.mean()), ues_meeting_demand_pct=float(100 * ue.meets_demand.mean()),
        ues_capacity_below_demand=int((ue.capacity_mbps < ue.offered_mbps).sum()))
    budget = pd.DataFrame([dict(component=GROUP[c], key=c, mean_ms=rx.comp[c].mean(),
                                p50_ms=np.median(rx.comp[c]), p95_ms=np.percentile(rx.comp[c], 95))
                           for c in COMPONENTS])
    return summ, ue, budget, rx, lat


# ---------------------------------------------------------------- 1. B1 vs T3 at the configured load
rate0 = E["traffic"]["rate_mbps"]
nets, res = {}, {}
for s in STRATS:
    nets[s] = run(s, rate0)
    res[s] = kpis(nets[s], rate0)
    print(f"{s}: p50 {res[s][0]['lat_p50_ms']:.1f} ms, p95 {res[s][0]['lat_p95_ms']:.1f} ms, "
          f"within PDB {res[s][0]['within_pdb_pct']:.1f} %, UEs meeting demand {res[s][0]['ues_meeting_demand_pct']:.0f} %")

pd.DataFrame([dict(strategy=s, **res[s][0]) for s in STRATS]).round(3).to_csv(TAB / "t10_userplane_kpis.csv", index=False)
pd.concat([res[s][2].assign(strategy=s) for s in STRATS]).round(4).to_csv(TAB / "t10_latency_budget.csv", index=False)
pd.concat([res[s][1].assign(strategy=s) for s in STRATS]).round(3).to_csv(TAB / "t10_per_ue.csv", index=False)

# ---------------------------------------------------------------- 2. load sweep
sweep = []
for rate in LOADS:
    for s in STRATS:
        r = res[s][0] if rate == rate0 else kpis(run(s, rate), rate)[0]
        sweep.append(dict(strategy=s, **r))
        print(f"  load {rate:>2} Mbps/UE  {s}: p95 {r['lat_p95_ms']:8.1f} ms, within PDB {r['within_pdb_pct']:5.1f} %, "
              f"UEs meeting demand {r['ues_meeting_demand_pct']:5.1f} %")
sweep = pd.DataFrame(sweep)
sweep.round(3).to_csv(TAB / "t10_load_sweep.csv", index=False)

# ---------------------------------------------------------------- checks
checks = {}
a, b = nets["B1"], nets["T3"]
checks["B1 and T3 use the same UEs (same twin positions)"] = bool(np.array_equal(a.radio.pool_idx, b.radio.pool_idx))
checks["B1 and T3 see the same packet streams (same seeds and start epochs)"] = all(
    a.dn.flows[u]["start"] == b.dn.flows[u]["start"] for u in a.dn.flows) and set(a.dn.flows) == set(b.dn.flows)
for s, n in nets.items():
    ue = res[s][1]
    expect = np.minimum(ue.offered_mbps, ue.capacity_mbps)
    ok = np.abs(ue.delivered_mbps - expect) <= np.maximum(0.10 * expect, 0.5)
    checks[f"{s}: each UE's delivered throughput = min(offered, twin capacity) within 10 % ({ok.sum()}/{len(ok)} UEs)"] = \
        bool(ok.mean() >= 0.9)
    rx = res[s][3]
    checks[f"{s}: delay components add up to each packet's end-to-end latency"] = bool(
        np.allclose(sum(rx.comp[c] for c in COMPONENTS), rx.t - rx.gen, atol=1e-6))
    _, r = n.radio.schedule(np.arange(E["num_ues"]), cfg0["experiments"]["num_slots"], np.random.default_rng(E["drop"]))
    t6 = pd.read_csv(TAB / "t6_kpi_per_drop.csv")
    ref = float(t6[(t6["drop"] == E["drop"]) & (t6.strategy == s)].mean_thr_mbps.iloc[0])
    checks[f"{s}: radio layer reproduces e03 drop {E['drop']} ({ref:.2f} Mbps mean)"] = bool(
        abs(r["thr_mbps"].mean() - ref) < 1e-6 * max(ref, 1))
json.dump({k: bool(v) for k, v in checks.items()}, open(TAB / "t10_checks.json", "w"), indent=2)

# ---------------------------------------------------------------- figures
# Fig 18: per-packet E2E latency CDF at the configured load
fig, ax = plt.subplots(figsize=(8, 4.6))
def fmt(x):
    return f"{x:.0f} ms" if np.isfinite(x) else "not delivered"


for s in STRATS:
    lat = res[s][4]                      # all packets, undelivered = inf: the CDF tops out below 1
    v = np.sort(lat[np.isfinite(lat)])
    ax.plot(v, np.arange(1, len(v) + 1) / len(lat), color=STRAT_COLOR[s], ls=STRAT_STYLE[s],
            label=f"{s}: p50 {fmt(np.percentile(lat, 50, method="nearest"))}, p95 {fmt(np.percentile(lat, 95, method="nearest"))}, "
                  f"{100 * np.mean(~np.isfinite(lat)):.1f} % not delivered")
ax.axvline(PDB, color=INK2, lw=1, ls=":")
ax.annotate(f"5QI {cfg0['e2e']['default_qos']['five_qi']} PDB {PDB:.0f} ms", (PDB, 1.0), xytext=(4, -10),
            textcoords="offset points", fontsize=8, color=INK2)
ax.set_xscale("log"); ax.set_xlabel("End-to-end latency, server -> UE [ms]")
ax.set_ylabel("Share of packets delivered within x"); ax.set_ylim(0, 1.02)
ax.set_title(f"Downlink packet latency, same {E['num_ues']} UEs, {rate0} Mbps each", loc="left")
ax.legend(loc="upper left", bbox_to_anchor=(0.17, 0.93))
save(fig, FIG / "fig18_e2e_latency_cdf.png")

# Fig 19: latency budget per hop (mean per delivered packet), grouped bars on a log axis
bud = {s: res[s][2].set_index("key") for s in STRATS}
fig, ax = plt.subplots(figsize=(8, 4.8))
y = np.arange(len(COMPONENTS))
h = 0.38
for i, s in enumerate(STRATS):
    vals = [bud[s].loc[c, "mean_ms"] for c in COMPONENTS]
    ax.barh(y + (i - 0.5) * (h + 0.02), vals, height=h, color=STRAT_COLOR[s], label=s)
ax.set_yticks(y); ax.set_yticklabels([GROUP[c] for c in COMPONENTS]); ax.invert_yaxis()
ax.set_xscale("log"); ax.set_xlabel("Mean delay per delivered packet [ms] (log scale)")
tot = {s: sum(bud[s].loc[c, "mean_ms"] for c in COMPONENTS) for s in STRATS}
nd = {s: res[s][0]["packets_not_delivered_pct"] for s in STRATS}
ax.set_title("Latency budget per hop, delivered packets: " + ", ".join(f"{s} {tot[s]:.1f} ms" for s in STRATS)
             + "\n" + "Not delivered (excluded from the bars): " + ", ".join(f"{s} {nd[s]:.0f} %" for s in STRATS),
             loc="left")
ax.legend(loc="lower right")
save(fig, FIG / "fig19_latency_budget.png")

# Fig 20: p95 latency and PDB compliance vs offered load (two panels, one measure each)
fig, axs = plt.subplots(1, 2, figsize=(12, 4.3))
for s in STRATS:
    d = sweep[sweep.strategy == s]
    axs[0].plot(d.offered_mbps_per_ue, d.within_pdb_pct, color=STRAT_COLOR[s], ls=STRAT_STYLE[s], marker="o", ms=8,
                label=s)
    axs[1].plot(d.offered_mbps_per_ue, d.ues_meeting_demand_pct, color=STRAT_COLOR[s], ls=STRAT_STYLE[s],
                marker="o", ms=8, label=s)
axs[0].set_ylabel(f"Packets within the {PDB:.0f} ms PDB [%]"); axs[0].set_ylim(0, 105)
axs[1].set_ylabel("UEs meeting demand and PDB [%]"); axs[1].set_ylim(0, 105)
for ax in axs:
    ax.set_xlabel("Offered downlink load per UE [Mbps]"); ax.set_xticks(LOADS); ax.legend()
axs[0].set_title("Packets within the 5QI 9 delay budget", loc="left")
axs[1].set_title("UEs getting their rate within the budget", loc="left")
save(fig, FIG / "fig20_latency_vs_load.png")

print("\nChecks:")
for k, v in checks.items():
    print(f"  [{'PASS' if v else 'FAIL'}] {k}")
if not all(checks.values()):
    sys.exit(1)
