"""
Full-buffer downlink end to end, so the e2e throughput can be compared with the radio-only T3/B1 results (e03).

e09/e10 offer 10 Mbps Poisson per UE: the e2e "mean DL per UE" there is the offered load that got through, not
what the radio can carry. Here the DN server sends every UE back-to-back packets at a line rate (500 Mbps)
above any UE's air capacity, so each DU's RLC queue never empties and a UE's delivered rate is its scheduler
capacity. Throughput is measured in the steady state only: from one epoch after the last UE's downlink stream
started (all 30 UEs then share the PRBs, as in e03) to the end of the run. Latency is not meaningful here
(it is the time to drain a full 4 MB buffer), so only throughput is reported.

Outputs (results/<tag>/):
  tables/t12_full_buffer.csv          per strategy: e2e delivered vs scheduler capacity vs e03, mean / p5 / median
  tables/t12_full_buffer_per_ue.csv   per UE and strategy
  tables/t12_checks.json
  figures/fig24_full_buffer.png
"""
import sys, copy, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from dt.config import load_config, DATA, FIG, TAB
from dt.e2e import E2ENetwork
from dt.e2e.userplane import Batch
from dt.plotstyle import plt, save, STRAT_COLOR, INK2

cfg0 = load_config()
E = cfg0["e2e"]
STRATS = ["B1", "T3"]
LINE_RATE = 500.0                                   # Mbps per UE, above the largest T3/B1 capacity (~320 Mbps)
DURATION = 1500                                     # ms: ~0.4 s of attach + PDU session, then ~1 s steady state

rows, per_ue, checks = [], [], {}
for s in STRATS:
    cfg = copy.deepcopy(cfg0)
    cfg["e2e"]["traffic"].update(model="full_buffer", full_buffer_line_rate_mbps=LINE_RATE)
    cfg["e2e"]["duration_ms"] = DURATION
    net = E2ENetwork(cfg, DATA, s).run()
    ep, end = net.epoch_ms, net.n_epochs * net.epoch_ms
    t_ss = (np.ceil(max(f["start"] for f in net.dn.flows.values()) / ep) + 1) * ep
    dur_s = (end - t_ss) / 1e3
    rl = pd.DataFrame(net.radio_log)
    rl = rl[(rl.epoch - 1) * ep >= t_ss]            # epochs that start inside the window

    # e03 reference: the same strategy on the same UEs, radio twin only
    _, ref = net.radio.schedule(np.arange(E["num_ues"]), cfg0["experiments"]["num_slots"],
                                np.random.default_rng(E["drop"]))
    t6 = pd.read_csv(TAB / "t6_kpi_per_drop.csv")
    e03_mean = float(t6[(t6["drop"] == E["drop"]) & (t6.strategy == s)].mean_thr_mbps.iloc[0])

    for i, u in enumerate(net.ues):
        b = Batch.concat(u.rx)
        sel = (b.t >= t_ss) & (b.t < end)
        per_ue.append(dict(strategy=s, ue=u.name,
                           e2e_delivered_mbps=float(b.size[sel].sum() * 8 / dur_s / 1e6),
                           scheduler_capacity_mbps=float(rl[rl.ue == u.name].capacity_mbps.mean()),
                           e03_thr_mbps=float(ref["thr_mbps"][i])))
    d = pd.DataFrame([r for r in per_ue if r["strategy"] == s])
    rows.append(dict(strategy=s, window_ms=f"{t_ss:.0f}-{end:.0f}", line_rate_mbps=LINE_RATE,
                     e2e_mean_mbps=d.e2e_delivered_mbps.mean(), capacity_mean_mbps=d.scheduler_capacity_mbps.mean(),
                     e03_mean_mbps=e03_mean,
                     e2e_p5_mbps=d.e2e_delivered_mbps.quantile(0.05), e03_p5_mbps=d.e03_thr_mbps.quantile(0.05),
                     e2e_median_mbps=d.e2e_delivered_mbps.median(), e03_median_mbps=d.e03_thr_mbps.median(),
                     e2e_cell_sum_mbps=d.e2e_delivered_mbps.sum(),
                     du_dropped_mb=sum(du.dropped for du in net.dus.values()) / 1e6))
    # The e2e layer must deliver exactly what its scheduler granted. The scheduler itself is e03's strategy on the
    # same UEs and cells, but run once per 20 ms epoch with its own random draws (T3 uses its rng; B1 does not),
    # so per-UE capacity can differ from e03's single run by a few %; the mean must agree closely.
    rel_s = np.abs(d.e2e_delivered_mbps - d.scheduler_capacity_mbps) / np.maximum(d.scheduler_capacity_mbps, 1e-9)
    rel_e = np.abs(d.e2e_delivered_mbps - d.e03_thr_mbps) / np.maximum(d.e03_thr_mbps, 1e-9)
    checks[f"{s}: every UE's DU queue stays backlogged (line rate > max capacity {d.scheduler_capacity_mbps.max():.0f} Mbps)"] = \
        bool(d.scheduler_capacity_mbps.max() < LINE_RATE)
    checks[f"{s}: e2e delivered = scheduler capacity per UE within 1 % (worst {100 * rel_s.max():.2f} %)"] = \
        bool(rel_s.max() <= 0.01)
    checks[f"{s}: mean e2e throughput = e03 mean within 1 % ({d.e2e_delivered_mbps.mean():.2f} vs {e03_mean:.2f} Mbps)"] = \
        bool(abs(d.e2e_delivered_mbps.mean() / e03_mean - 1) <= 0.01)
    checks[f"{s}: e2e = e03 per UE within 5 % (worst {100 * rel_e.max():.2f} %; scheduler random draws per epoch)"] = \
        bool(rel_e.max() <= 0.05)
    print(f"{s}: e2e full-buffer mean {rows[-1]['e2e_mean_mbps']:.2f} Mbps/UE "
          f"(scheduler {rows[-1]['capacity_mean_mbps']:.2f}, e03 {e03_mean:.2f}), window {rows[-1]['window_ms']} ms")

summ = pd.DataFrame(rows)
per_ue = pd.DataFrame(per_ue)
summ.round(3).to_csv(TAB / "t12_full_buffer.csv", index=False)
per_ue.round(3).to_csv(TAB / "t12_full_buffer_per_ue.csv", index=False)
json.dump(checks, open(TAB / "t12_checks.json", "w"), indent=2)

# Fig 24: per-UE e2e full-buffer throughput vs the radio-only e03 throughput
fig, ax = plt.subplots(figsize=(6.4, 5.4))
hi = max(per_ue.e03_thr_mbps.max(), per_ue.e2e_delivered_mbps.max()) * 1.4
ax.plot([0.1, hi], [0.1, hi], color=INK2, lw=1, ls=":", label="e2e = e03")
for s in STRATS:
    d = per_ue[per_ue.strategy == s]
    m = summ.set_index("strategy").loc[s]
    ax.scatter(d.e03_thr_mbps, d.e2e_delivered_mbps, s=36, color=STRAT_COLOR[s],
               label=f"{s}: mean e2e {m.e2e_mean_mbps:.1f} vs e03 {m.e03_mean_mbps:.1f} Mbps")
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(0.5, hi); ax.set_ylim(0.5, hi)
ax.set_xlabel("e03 radio-only throughput per UE [Mbps]")
ax.set_ylabel("End-to-end full-buffer throughput per UE [Mbps]")
ax.set_title(f"Full-buffer downlink, same {E['num_ues']} UEs (drop {E['drop']})", loc="left")
ax.legend(loc="upper left")
save(fig, FIG / "fig24_full_buffer.png")

print("\n" + summ.round(2).to_string(index=False))
print("\nChecks:")
for k, v in checks.items():
    print(f"  [{'PASS' if v else 'FAIL'}] {k}")
if not all(checks.values()):
    sys.exit(1)
