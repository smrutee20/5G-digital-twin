"""
End-to-end flow: UE attach, registration, PDU session and downlink data through
RAN (RU, DU, CU-CP, CU-UP) and core (AMF, SMF, UPF, AUSF, UDM, NRF, PCF) to a data-network server.

Outputs (results/<tag>/):
  e2e_trace.json                 every message: time, source, destination, interface, procedure, message
  tables/t9_e2e_ue_summary.csv   per-UE milestones, latencies and delivered throughput
  tables/t9_e2e_summary.json     message counts per interface / procedure, latency statistics, checks
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from dt.config import load_config, DATA, RESULTS, TAB
from dt.e2e import E2ENetwork
from dt.e2e.interfaces import check_link
from dt.e2e.trace import REQUIRED

cfg = load_config()
E = cfg["e2e"]
e2e = E2ENetwork(cfg, DATA).run()
recs = e2e.trace.records
meta = e2e.meta()
e2e.trace.write(RESULTS / "e2e_trace.json", meta)
print(f"{len(recs)} messages -> {RESULTS / 'e2e_trace.json'}")

# ---------------------------------------------------------------- per-UE summary
end_ms = e2e.net.sim.now - 50.0
rows = []
for ue in e2e.ues:
    t = ue.t
    first = t.get("first_dl_byte")
    rows.append(dict(
        ue=ue.name, serving_ru=ue.ru, du=e2e.net.cell_owner[ue.ru][0],
        t_power_on_ms=round(t["power_on"], 3), t_rrc_connected_ms=round(t["rrc_connected"], 3),
        t_registered_ms=round(t["registered"], 3), t_session_active_ms=round(t["session_active"], 3),
        t_first_dl_byte_ms=round(first, 3) if first else None,
        rrc_setup_ms=round(t["rrc_connected"] - t["power_on"], 3),
        registration_ms=round(t["registered"] - t["power_on"], 3),
        pdu_session_ms=round(t["session_active"] - t["registered"], 3),
        power_on_to_first_byte_ms=round(first - t["power_on"], 3) if first else None,
        dl_bytes=ue.rx_bytes,
        dl_mbps_after_first_byte=round(ue.rx_bytes * 8 / (end_ms - first) / 1e3, 2) if first else 0.0))
ues = pd.DataFrame(rows)
ues.to_csv(TAB / "t9_e2e_ue_summary.csv", index=False)

# ---------------------------------------------------------------- checks
kinds = meta["elements"]
checks = {}
checks["every message has time, source, destination, interface, procedure, message"] = all(
    all(r.get(k) not in (None, "") for k in REQUIRED) for r in recs)
bad = 0
for r in recs:
    try:
        check_link(r["interface"], kinds[r["src"]], kinds[r["dst"]])
    except ValueError:
        bad += 1
checks["every message uses a legal interface between the right element types"] = bad == 0
checks["every UE is registered (UE and AMF) with an active PDU session"] = all(
    u.mm_state == "REGISTERED" and u.session == "ACTIVE" and e2e.net.nodes["AMF"].ctx[u.name]["state"] == "REGISTERED"
    for u in e2e.ues)

# byte conservation along DU -> RU -> UE, and the DU never exceeds the scheduler's capacity
uu = pd.DataFrame([r for r in recs if r["interface"] == "Uu" and r["message"] == "PDSCH"])
dlog = pd.DataFrame([x for du in e2e.dus.values() for x in du.delivered_log])
per_ue_trace = uu.groupby("ue")["bytes"].sum() if len(uu) else pd.Series(dtype=float)
checks["UE received bytes == PDSCH bytes in the trace == DU delivered == CU-UP delivery status"] = all(
    u.rx_bytes == per_ue_trace.get(u.name, 0) == dlog[dlog.ue == u.name].delivered_bytes.sum()
    == sum(up.dl_delivered.get(u.name, 0) for up in e2e.cu_ups.values()) for u in e2e.ues)
checks["DU never serves more than the scheduler's per-UE capacity in an epoch"] = bool(
    (dlog.served_bytes <= dlog.capacity_bytes + 1).all())
queued = {u: du.qbytes.get(u, 0) for du in e2e.dus.values() for u in du.qbytes}
dropped = sum(du.dropped for du in e2e.dus.values())
checks["bytes sent by the DN == received by UEs + dropped at DUs + still queued"] = (
    sum(e2e.dn.sent.values()) == sum(u.rx_bytes for u in e2e.ues) + dropped + sum(queued.values()))
from dt.e2e.userplane import Batch, COMPONENTS
rx = Batch.concat([b for u in e2e.ues for b in u.rx])
checks["every packet's delay components add up to its end-to-end latency"] = bool(
    len(rx) and np.allclose(sum(rx.comp[c] for c in COMPONENTS), rx.t - rx.gen, atol=1e-6))

# the radio layer is the unchanged T3: all 30 UEs, e03's seed for this drop -> e03's T3 result
bits, res = e2e.radio.schedule(np.arange(E["num_ues"]), cfg["experiments"]["num_slots"],
                               np.random.default_rng(E["drop"]))
t6 = pd.read_csv(TAB / "t6_kpi_per_drop.csv")
ref = float(t6[(t6["drop"] == E["drop"]) & (t6.strategy == "T3")].mean_thr_mbps.iloc[0])
checks[f"radio layer reproduces e03 T3, drop {E['drop']} ({ref:.3f} Mbps mean)"] = bool(
    abs(res["thr_mbps"].mean() - ref) < 1e-6 * max(ref, 1))

# ---------------------------------------------------------------- summary
df = pd.DataFrame(recs)
cp = df[~df.procedure.str.startswith("User Plane")]
summary = dict(
    messages_total=len(df), control_plane_messages=len(cp), user_plane_messages=len(df) - len(cp),
    messages_per_interface=df.interface.value_counts().to_dict(),
    messages_per_procedure=df.procedure.value_counts().to_dict(),
    control_messages_per_ue_attach=round(len(cp[cp.ue.notna()]) / len(e2e.ues), 1),
    latency_ms={c: dict(median=round(float(ues[c].median()), 2), p95=round(float(ues[c].quantile(0.95)), 2),
                        max=round(float(ues[c].max()), 2))
                for c in ["rrc_setup_ms", "registration_ms", "pdu_session_ms", "power_on_to_first_byte_ms"]},
    dl_mbps_mean=round(float(ues.dl_mbps_after_first_byte.mean()), 2),
    e2e_latency_ms=dict(packets=len(rx), p50=round(float(np.median(rx.t - rx.gen)), 2),
                        p95=round(float(np.percentile(rx.t - rx.gen, 95)), 2)),
    mean_capacity_mbps=round(float(pd.DataFrame(e2e.radio_log).capacity_mbps.mean()), 2),
    pdu_sessions_per_upf=pd.Series([r["dst"] for r in recs if r["message"] == "PFCPSessionEstablishmentRequest"])
                         .value_counts().to_dict(),
    du_dropped_bytes=int(dropped), du_queued_bytes_at_end=int(sum(queued.values())),
    checks={k: bool(v) for k, v in checks.items()})
json.dump(summary, open(TAB / "t9_e2e_summary.json", "w"), indent=2)

print(json.dumps({k: v for k, v in summary.items() if k != "checks"}, indent=2))
print("\nChecks:")
for k, v in checks.items():
    print(f"  [{'PASS' if v else 'FAIL'}] {k}")
if not all(checks.values()):
    sys.exit(1)
