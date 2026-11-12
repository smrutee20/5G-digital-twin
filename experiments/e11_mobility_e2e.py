"""
Mobility and a site outage, end to end (T3 scheduler, 10 Mbps downlink per active UE).

1. Handovers: one UE walks each of the three e05 routes (2 m steps at 1.4 m/s) among 27 static UEs. When
   the A3 condition (neighbour > serving + 3 dB for 2 consecutive steps) holds on the twin's RSRP, the UE
   sends a Measurement Report and the gNB runs an intra-gNB handover (same site) or an Xn handover
   (other site: Xn preparation, data forwarding over Xn-U, Path Switch -> SMF -> PFCP at the UPF, End Marker).
2. What-if "site B off": site B is switched off without warning at t = 1.5 s. Its UEs detect radio link
   failure, select the best remaining cell and come back with a Service Request; the AMF/SMF re-route their
   PDU sessions to the new gNB (new N3 tunnel at the UPF).

Outputs (results/<tag>/):
  e2e_trace_mobility.json, e2e_trace_siteoff.json      every message (as e2e_trace.json)
  e2e_kpis_mobility.json, e2e_kpis_siteoff.json        per UE per 20 ms: RU, RSRP, SINR, capacity, throughput, latency
  tables/t11_handovers.csv, t11_site_off_ues.csv, t11_summary.json
  figures/fig21_handover_timeseries.png, fig22_handover_zoom.png, fig23_site_off.png
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from dt.config import load_config, DATA, RESULTS, FIG, TAB
from dt.e2e import E2ENetwork
from dt.e2e.interfaces import check_link
from dt.e2e.userplane import Batch
from dt.plotstyle import plt, save, CAT, INK2

cfg = load_config()
E = cfg["e2e"]
WIN = 1000.0                                   # throughput window before / after an event [ms]


def rx_of(ue):
    return Batch.concat(ue.rx)


def thr(b, t0, t1):
    sel = (b.t >= t0) & (b.t < t1)
    return float(b.size[sel].sum() * 8 / ((t1 - t0) * 1e3)), float(np.mean((b.t - b.gen)[sel])) if sel.any() else np.nan


def legal(net):
    kinds = {n: x.kind for n, x in net.net.nodes.items()}
    bad = 0
    for r in net.trace.records:
        try:
            check_link(r["interface"], kinds[r["src"]], kinds[r["dst"]])
        except ValueError:
            bad += 1
    return bad == 0


def save_run(net, name):
    net.trace.write(RESULTS / f"e2e_trace_{name}.json", net.meta())
    k = net.kpi_table()
    k.to_json(RESULTS / f"e2e_kpis_{name}.json", orient="split", index=False)
    return k


checks = {}
# ================================================================ 1. handovers along the walks
mob = E2ENetwork(cfg, DATA, "T3", "mobility").run()
kmob = save_run(mob, "mobility")
recs = mob.trace.records
rows = []
for name, walk in mob.walker.items():
    ue = mob.ue_by_name[name]
    b = rx_of(ue)
    cmds = [(t, d) for t, ev, d in ue.events if ev == "handover command"]
    done = {d["ho_id"]: t for t, ev, d in ue.events if ev == "handover complete"}
    for t_cmd, d in cmds:
        hid = d["ho_id"]
        t_done = done.get(hid)
        before = b.t[b.t < t_cmd]
        after = b.t[b.t >= t_cmd]
        ps = [r["t_arrive_ms"] for r in recs if r.get("ho_id") == hid and r["message"] == "PathSwitchRequestAcknowledge"]
        em = [r["t_arrive_ms"] for r in recs if r.get("ho_id") == hid and r["message"] == "EndMarker"
              and r["interface"] == "Xn-U"]
        fwd = int(((b.comp["xn"] > 0) & (b.t >= t_cmd - 1) & (b.t < t_cmd + 500)).sum())
        tb, lb = thr(b, t_cmd - WIN, t_cmd)
        ta, la = thr(b, (t_done or t_cmd) + 100, (t_done or t_cmd) + 100 + WIN)
        k = kmob[kmob.ue == name]
        cap_b = k[(k.t_ms >= t_cmd - WIN) & (k.t_ms < t_cmd)].capacity_mbps.mean()
        cap_a = k[(k.t_ms >= t_done + 100) & (k.t_ms < t_done + 100 + WIN)].capacity_mbps.mean() if t_done else np.nan
        rsrp_b = k[(k.t_ms >= t_cmd - WIN) & (k.t_ms < t_cmd)].rsrp_dbm.mean()
        rsrp_a = k[(k.t_ms >= t_done + 100) & (k.t_ms < t_done + 100 + WIN)].rsrp_dbm.mean() if t_done else np.nan
        rows.append(dict(
            ho_id=hid, ue=name, walk=walk, type=d["type"], source=d["source"], target=d["target"],
            t_command_ms=round(t_cmd, 1), t_complete_ms=round(t_done, 1) if t_done else None,
            ue_interruption_ms=round(t_done - t_cmd, 2) if t_done else None,
            dl_gap_ms=round(float(after[0] - before[-1]), 2) if len(before) and len(after) else None,
            path_switch_ack_after_ms=round(ps[0] - t_cmd, 1) if ps else None,
            end_marker_after_ms=round(em[0] - t_cmd, 1) if em else None, packets_forwarded_xn=fwd,
            max_latency_around_ho_ms=round(float(np.max((b.t - b.gen)[(b.t >= t_cmd) & (b.t < t_cmd + 300)])), 1)
            if ((b.t >= t_cmd) & (b.t < t_cmd + 300)).any() else None,
            rsrp_before_dbm=round(rsrp_b, 1), rsrp_after_dbm=round(rsrp_a, 1),
            capacity_before_mbps=round(cap_b, 1), capacity_after_mbps=round(cap_a, 1),
            thr_before_mbps=round(tb, 2), thr_after_mbps=round(ta, 2),
            latency_before_ms=round(lb, 2), latency_after_ms=round(la, 2)))
ho = pd.DataFrame(rows)
ho.to_csv(TAB / "t11_handovers.csv", index=False)
print(ho[["ho_id", "ue", "type", "source", "target", "ue_interruption_ms", "dl_gap_ms", "path_switch_ack_after_ms",
          "packets_forwarded_xn", "capacity_before_mbps", "capacity_after_mbps", "thr_before_mbps", "thr_after_mbps"]]
      .to_string(index=False))

xn = ho[ho.type == "Handover (Xn)"]
checks["mobility: every message uses a legal interface"] = legal(mob)
checks["mobility: every handover command was followed by a completed RACH on the target"] = bool(
    len(ho) and ho.t_complete_ms.notna().all())
checks["mobility: every Xn handover got a Path Switch Ack and an End Marker"] = bool(
    xn.path_switch_ack_after_ms.notna().all() and xn.end_marker_after_ms.notna().all())
end = mob.n_epochs * mob.epoch_ms
lost, overflow = 0, 0
for name in mob.walker:
    ue = mob.ue_by_name[name]
    gen = np.concatenate(mob.dn.sent_gen.get(name, [np.array([])]))
    missing = gen[(gen <= end - E["pdb_ms"]) & ~np.isin(gen, rx_of(ue).gen)]
    dropped = np.concatenate([np.array(du.dropped_gen.get(name, [])) for du in mob.dus.values()])
    overflow += len(dropped)
    lost += int(np.sum(~np.isin(missing, dropped)))        # missing for any reason other than a full buffer
checks[f"mobility: no packet lost by a handover ({lost} lost; {overflow} tail-dropped earlier when the "
       f"walker's capacity was below its demand)"] = lost == 0 and mob.net.lost_bytes == 0

# ================================================================ 2. what-if: site B switched off
off = E2ENetwork(cfg, DATA, "T3", "site_off").run()
koff = save_run(off, "siteoff")
t_off = off.off["t_ms"]
rows = []
for ue in off.ues:
    b = rx_of(ue)
    ev = {e: t for t, e, d in ue.events}
    hit = "radio link failure" in ev
    before = b.t[b.t < t_off]
    after = b.t[b.t >= t_off]
    first_after = after[0] if len(after) else None
    tb, lb = thr(b, t_off - WIN, t_off)
    t_end = off.n_epochs * off.epoch_ms
    ta, la = thr(b, t_end - WIN, t_end)
    k = koff[koff.ue == ue.name]
    rows.append(dict(
        ue=ue.name, affected=hit,
        ru_before=k[k.t_ms < t_off].ru.iloc[-1], ru_after=k.ru.iloc[-1],
        t_rlf_ms=ev.get("radio link failure"), t_service_resumed_ms=ev.get("service resumed"),
        t_first_dl_after_ms=round(float(first_after), 1) if first_after is not None else None,
        dl_interruption_ms=round(float(first_after - before[-1]), 1) if (len(before) and first_after is not None) else None,
        capacity_before_mbps=round(k[(k.t_ms >= t_off - WIN) & (k.t_ms < t_off)].capacity_mbps.mean(), 1),
        capacity_after_mbps=round(k[k.t_ms >= t_end - WIN].capacity_mbps.mean(), 1),
        thr_before_mbps=round(tb, 2), thr_after_mbps=round(ta, 2),
        latency_before_ms=round(lb, 2), latency_after_ms=round(la, 2)))
so = pd.DataFrame(rows)
so.to_csv(TAB / "t11_site_off_ues.csv", index=False)
aff = so[so.affected]
print("\nsite B off at", t_off, "ms:", len(aff), "UEs affected")
print(aff[["ue", "ru_before", "ru_after", "dl_interruption_ms", "capacity_before_mbps", "capacity_after_mbps",
           "thr_before_mbps", "thr_after_mbps"]].to_string(index=False))
sr_n4 = {r["ue"] for r in off.trace.records if r["procedure"] == "Service Request"
         and r["message"] == "PFCPSessionModificationRequest"}
checks["site off: every message uses a legal interface"] = legal(off)
checks["site off: every affected UE resumed its session through another site"] = bool(
    len(aff) and aff.t_service_resumed_ms.notna().all() and not aff.ru_after.str.startswith("RU-B").any())
checks["site off: the SMF re-routed every affected session at the UPF (N4 modification)"] = set(aff.ue) <= sr_n4
checks["site off: every affected UE receives data again"] = bool(aff.t_first_dl_after_ms.notna().all()
                                                                 and (aff.thr_after_mbps > 0).all())

summary = dict(
    handovers=dict(count=len(ho), by_type=ho.type.value_counts().to_dict(),
                   ue_interruption_ms_mean=round(float(ho.ue_interruption_ms.mean()), 2),
                   dl_gap_ms_mean=round(float(ho.dl_gap_ms.mean()), 2), dl_gap_ms_max=round(float(ho.dl_gap_ms.max()), 2),
                   path_switch_ack_after_ms_mean=round(float(xn.path_switch_ack_after_ms.mean()), 2) if len(xn) else None,
                   packets_lost_by_handover=lost, packets_tail_dropped_capacity_below_demand=overflow),
    site_off=dict(site=off.off["site"], t_ms=t_off, rlf_ms=E["site_off"]["rlf_ms"], affected_ues=len(aff),
                  dl_interruption_ms_mean=round(float(aff.dl_interruption_ms.mean()), 1),
                  dl_interruption_ms_max=round(float(aff.dl_interruption_ms.max()), 1),
                  bytes_lost_towards_site=int(off.net.lost_bytes), bytes_lost_in_du=int(off.lost_in_du),
                  affected_capacity_mbps_before_after=[round(float(aff.capacity_before_mbps.mean()), 1),
                                                        round(float(aff.capacity_after_mbps.mean()), 1)],
                  others_capacity_mbps_before_after=[round(float(so[~so.affected].capacity_before_mbps.mean()), 1),
                                                      round(float(so[~so.affected].capacity_after_mbps.mean()), 1)]),
    checks={k: bool(v) for k, v in checks.items()})
json.dump(summary, open(TAB / "t11_summary.json", "w"), indent=2)
print(json.dumps({k: v for k, v in summary.items() if k != "checks"}, indent=2))

# ================================================================ figures
# Fig 21: throughput and serving RSRP along the walks that hand over
walkers = [n for n in mob.walker if (ho.ue == n).any()] or list(mob.walker)
fig, axs = plt.subplots(2, len(walkers), figsize=(6.5 * len(walkers), 6.5), squeeze=False, sharex=True)
for c, name in enumerate(walkers):
    k = kmob[kmob.ue == name].sort_values("t_ms")
    t = k.t_ms / 1e3
    sm = k.thr_mbps.rolling(10, min_periods=1).mean()
    axs[0, c].plot(t, k.capacity_mbps, color=CAT[0], lw=1.5, label="Air capacity from the twin (T3)")
    axs[0, c].plot(t, sm, color=CAT[2], lw=2, label="Delivered (200 ms average)")
    axs[1, c].plot(t, k.rsrp_dbm, color=CAT[0], lw=1.5)
    for i, (_, h) in enumerate(ho[ho.ue == name].iterrows()):
        for ax in axs[:, c]:
            ax.axvline(h.t_command_ms / 1e3, color=INK2, lw=0.8, ls=":")
        axs[1, c].annotate(f"{h.source[3:]}→{h.target[3:]}", (h.t_command_ms / 1e3, axs[1, c].get_ylim()[1]),
                           xytext=(2, -12 - 12 * (i % 2)), textcoords="offset points", fontsize=8, color=INK2)
    axs[0, c].set_title(f"{name}, walk {mob.walker[name]}: throughput", loc="left")
    axs[1, c].set_title("Serving-cell RSRP (handovers dotted)", loc="left")
    axs[0, c].set_ylabel("Mbps"); axs[1, c].set_ylabel("RSRP [dBm]"); axs[1, c].set_xlabel("Time [s]")
    axs[0, c].legend(loc="upper right", fontsize=8)
save(fig, FIG / "fig21_handover_timeseries.png")

# Fig 22: zoom on one Xn handover: per-packet latency vs arrival time
h = (xn if len(xn) else ho).sort_values("latency_before_ms").iloc[0]     # clearest case: not backlogged
b = rx_of(mob.ue_by_name[h.ue])
sel = (b.t >= h.t_command_ms - 60) & (b.t < h.t_command_ms + 120)
fig, ax = plt.subplots(figsize=(9, 4.2))
fw = b.comp["xn"][sel] > 0
ax.scatter(b.t[sel][~fw] - h.t_command_ms, (b.t - b.gen)[sel][~fw], s=10, color=CAT[0], label="direct path")
ax.scatter(b.t[sel][fw] - h.t_command_ms, (b.t - b.gen)[sel][fw], s=14, color=CAT[1], label="forwarded over Xn-U")
for i, (x, lab) in enumerate([(0, "HO command"), (h.t_complete_ms - h.t_command_ms, "RACH done at target"),
                              (h.end_marker_after_ms, "End Marker at target"),
                              (h.path_switch_ack_after_ms, "Path Switch Ack")]):
    if pd.notna(x):
        ax.axvline(x, color=INK2, lw=0.8, ls=":")
        ax.annotate(lab, (x, ax.get_ylim()[0]), xytext=(3, 5 + 13 * i), textcoords="offset points", fontsize=8,
                    color=INK2)
ax.set_xlabel("Packet arrival at the UE, relative to the handover command [ms]")
ax.set_ylabel("End-to-end latency [ms]")
ax.set_title(f"{h.ue}: {h.type} {h.source} → {h.target}, DL gap {h.dl_gap_ms:.0f} ms", loc="left")
ax.legend(loc="center right")
save(fig, FIG / "fig22_handover_zoom.png")

# Fig 23: site B off: affected vs other UEs over time, and per-UE before/after
fig, axs = plt.subplots(1, 2, figsize=(13, 4.4), gridspec_kw=dict(width_ratios=[1.4, 1]))
ka = koff.assign(group=np.where(koff.ue.isin(aff.ue), "affected", "others"))
for g, col in [("others", CAT[0]), ("affected", CAT[2])]:
    s = ka[ka.group == g].groupby("t_ms").thr_mbps.mean().rolling(5, min_periods=1).mean()
    axs[0].plot(s.index / 1e3, s.values, color=col, lw=2, label=f"{'UEs on site B' if g == 'affected' else 'other UEs'}")
for i, (x, lab) in enumerate([(t_off, "site B off"), (t_off + E["site_off"]["rlf_ms"], "RLF detected"),
                              (aff.t_service_resumed_ms.max(), "service resumed")]):
    axs[0].axvline(x / 1e3, color=INK2, lw=0.8, ls=":")
    axs[0].annotate(lab, (x / 1e3, 12.4), xytext=(3, -12 * i), textcoords="offset points", fontsize=8, color=INK2)
axs[0].set_xlabel("Time [s]"); axs[0].set_ylabel("Mean delivered throughput [Mbps]")
axs[0].set_ylim(0, 12.6)
axs[0].set_title("Site B switched off: throughput", loc="left"); axs[0].legend(loc="center right")
x = np.arange(len(aff)); w = 0.4
axs[1].bar(x - w / 2, aff.capacity_before_mbps, w - 0.04, color=CAT[0], label="before (site B)")
axs[1].bar(x + w / 2, aff.capacity_after_mbps, w - 0.04, color=CAT[2], label="after (new site)")
axs[1].axhline(E["traffic"]["rate_mbps"], color=INK2, lw=0.8, ls=":")
axs[1].annotate("demand", (len(aff) - 0.5, E["traffic"]["rate_mbps"]), xytext=(-30, 3), textcoords="offset points",
                fontsize=8, color=INK2)
axs[1].set_xticks(x); axs[1].set_xticklabels(aff.ue, rotation=45, fontsize=8)
axs[1].set_yscale("log"); axs[1].set_ylabel("Air capacity from the twin [Mbps]")
axs[1].set_title(f"Its {len(aff)} UEs: capacity before / after", loc="left"); axs[1].legend(fontsize=8)
save(fig, FIG / "fig23_site_off.png")

print("\nChecks:")
for k, v in checks.items():
    print(f"  [{'PASS' if v else 'FAIL'}] {k}")
if not all(checks.values()):
    sys.exit(1)
