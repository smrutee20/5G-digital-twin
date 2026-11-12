"""
Build an offline, self-contained HTML viewer for the end-to-end 5G flow.

    python tools/build_e2e_viewer.py            # -> results/<tag>/e2e_viewer.html

Reads results/<tag>/e2e_trace*.json and e2e_kpis*.json (from e09 and e11) and the campus footprints, and
writes ONE html file with the data embedded and no external libraries, fonts or CDNs, so it opens in any
browser without internet. Views: topology with animated messages, per-procedure sequence diagram with
play/pause/step, campus map with the selected UE, and live KPIs (RSRP, SINR, throughput, latency).
URL parameters for direct links / screenshots: ?scenario=mobility&ue=UE28&t=10086&proc=<id>&step=12
"""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from dt.config import load_config, RESULTS

cfg = load_config()
SCEN = [("attach", "Attach, registration and PDU session (30 UEs)", "e2e_trace.json", None),
        ("mobility", "Mobility: walks with Xn handovers", "e2e_trace_mobility.json", "e2e_kpis_mobility.json"),
        ("siteoff", "What-if: site B switched off", "e2e_trace_siteoff.json", "e2e_kpis_siteoff.json")]
UP_EVERY = {"attach": 1, "mobility": 10, "siteoff": 1}     # keep every n-th epoch of user-plane hops
KPI_EVERY = {"attach": 1, "mobility": 5, "siteoff": 1}
DETAIL_SKIP = {"seq", "t_ms", "t_arrive_ms", "src", "dst", "interface", "procedure", "message", "ue"}


def kpis_for(name, every, walkers):
    if name == "attach":
        sys.path.insert(0, str(ROOT))
        from dt.config import DATA
        from dt.e2e import E2ENetwork
        k = E2ENetwork(cfg, DATA).run().kpi_table()          # same deterministic run as e09
    else:
        k = pd.read_json(RESULTS / dict((s[0], s[3]) for s in SCEN)[name], orient="split")
    out = {}
    for ue, g in k.groupby("ue"):
        g = g.sort_values("t_ms")
        if ue not in walkers:
            g = g.iloc[::every]
        out[ue] = [[int(r.t_ms), r.ru, r.x, r.y,
                    None if pd.isna(r.rsrp_dbm) else r.rsrp_dbm, None if pd.isna(r.sinr_db) else r.sinr_db,
                    r.thr_mbps, None if pd.isna(r.latency_ms) else r.latency_ms,
                    None if pd.isna(r.capacity_mbps) else r.capacity_mbps, r.state] for r in g.itertuples()]
    return out


scenarios = {}
for name, label, tf, kf in SCEN:
    path = RESULTS / tf
    if not path.exists():
        print(f"skip {name}: {path} missing (run e09 / e11 first)")
        continue
    tr = json.load(open(path))
    meta, msgs = tr["meta"], tr["messages"]
    # attach Measurement Reports to the handover they triggered (next handover of that UE)
    nxt = {}
    for r in reversed(msgs):
        if r["procedure"].startswith("Handover") and "ho_id" in r and "ue" in r:
            nxt[r["ue"]] = (r["ho_id"], r["procedure"])
        if r["procedure"] == "Measurement Report" and r.get("ue") in nxt:
            r["ho_id"], r["_proc"] = nxt[r["ue"]]
    strings, sidx = [], {}

    def s(x):
        if x not in sidx:
            sidx[x] = len(strings)
            strings.append(x)
        return sidx[x]

    rows, details = [], []
    for r in msgs:
        up = r["procedure"].startswith("User Plane")
        if up and r["procedure"] == "User Plane DL" and r.get("epoch") is not None \
                and r["epoch"] % UP_EVERY[name] and r.get("epoch", 0) > 3:
            continue
        d = {k: v for k, v in r.items() if k not in DETAIL_SKIP and not k.startswith("_")}
        proc = r.get("_proc", r["procedure"])
        inst = f"{r.get('ue', 'network')}|{proc}|{r.get('ho_id', '')}" if not up else ""
        rows.append([round(r["t_ms"], 3), round(r["t_arrive_ms"], 3), s(r["src"]), s(r["dst"]), s(r["interface"]),
                     s(r["procedure"]), s(r["message"]), s(r.get("ue", "")), len(details), s(inst)])
        details.append(json.dumps(d, separators=(",", ":"), default=str))
    walkers = set((meta.get("walkers") or {}).keys())
    scenarios[name] = dict(label=label, meta=dict(duration=meta["duration_ms"], elements=meta["elements"],
                                                  gnbs=meta.get("gnbs"), walkers=meta.get("walkers"),
                                                  site_off=meta.get("site_off"), notes=meta["notes"],
                                                  latency=meta["latency_ms"]),
                           strings=strings, msgs=rows, details=details,
                           kpi=kpis_for(name, KPI_EVERY[name], walkers))
    print(f"{name}: {len(rows)} of {len(msgs)} messages embedded")

fp = json.load(open(ROOT / "scenes" / "iitgn" / "footprints.json"))
sites = [dict(name=s["name"], xy=s["xy"], h=s.get("height_m", cfg["ran"]["height_m"]),
              az=s.get("sector_azimuths_deg", cfg["ran"]["sector_azimuths_deg"])) for s in cfg["ran"]["sites"]]
DATA = dict(scenarios=scenarios, map=dict(buildings=[dict(n=b["name"], h=b["h"], xy=b["xy"]) for b in fp],
                                          sites=sites, half=cfg["scene"]["area_xy"][1] + 50),
            has3d=(RESULTS / "twin_3d.html").exists())
html = Path(__file__).with_name("e2e_viewer_template.html").read_text()
out = RESULTS / "e2e_viewer.html"
out.write_text(html.replace("/*__DATA__*/null", json.dumps(DATA, separators=(",", ":"))))
print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
