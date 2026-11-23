"""
One command for everything:   python run.py      then open twin.html (double-click; works offline).

  Step 1  the twin: load data/twin.json (buildings, sectors, RSRP map, 3 routes, all from the study's ray tracing).
          If tasks/task10_walk_v2.py has run, the demo walks its 3 routes instead (campus roads, ray-traced on twin v2:
          data/study_v2/walk_routes.json); data/twin.json and v1's task 5 results are not changed.
  Step 2  for each route: build the network (the phone, one gNB per site, the 5G core: net/ran.py, net/core.py)
  Step 3  walk the phone step by step; the twin's A3 rule picks the serving sector; flows 1-6 run
  Step 4  put the twin, every message and the 3D library (vendor/) into viewer.html, save it as twin.html
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import config as C
from twin.twin_data import get_twin
from net.sim import Network, FLOWS, IDENTITIES
from net.ids import supi, suci_null_scheme, imeisv
from net.ran import UE, GNB
from net.core import AMF, AUSF, UDM, SIDF, NSSF, SMF, UPF, Internet

STEP_MS = C.STEP_M / C.SPEED_MPS * 1000          # one 2 m step at 1.4 m/s = 1429 ms


def build_network():
    """Step 2: create every element. They find each other by name ("AMF", "gNB-B", ...)."""
    net = Network()
    the_supi = supi(C.MCC, C.MNC, C.MSIN)                                   # imsi-001019876500001
    ue = net.add(UE(net, the_supi, suci_null_scheme(the_supi, C.MCC, C.MNC), imeisv(**C.IMEISV)))
    gnbs = [net.add(GNB(net, site, i)) for i, site in enumerate(C.SITES)]
    net.add(AMF(net, {g.name: C.TAC for g in gnbs}))                       # all sites in tracking area 1
    net.add(AUSF("AUSF", net))
    net.add(UDM(net, subscribers={the_supi}))
    net.add(SIDF("SIDF", net))
    net.add(NSSF("NSSF", net))
    net.add(SMF(net))
    net.add(UPF(net))
    internet = net.add(Internet("Internet", net))
    return net, ue, internet


def simulate(route, sector_names, offset_db=C.A3_OFFSET_DB, ttt_steps=C.A3_STEPS):
    """Step 3: schedule the walk and the events on it, then run the clock. The handover rule (A3 offset in dB and
    time-to-trigger in steps) defaults to the study's 3 dB / 2 steps; the server's /timeline can use another one."""
    net, ue, internet = build_network()
    steps = len(route["points"])
    a3 = dict(serving=None, candidate=None, count=0)        # the twin's handover rule (event A3)

    def walk_step(k):
        net.step = k
        rsrp = dict(zip(sector_names, route["rsrp"][k]))     # ray-traced RSRP of every sector here
        best = max(rsrp, key=rsrp.get)
        if k == 0:                                          # switch on: use the strongest sector
            a3["serving"] = best
            net.flow = 1
            net.say(f"The phone switches on and hears every sector. The strongest is {best} "
                    f"({rsrp[best]:.0f} dBm) on gNB-{best[0]}", kind="step")
            ue.power_on(best)
            return
        # A3 rule: another sector must be offset_db (3 dB) stronger than the serving one for ttt_steps (2) steps in a row
        serving = a3["serving"]
        better = best != serving and rsrp[best] > rsrp[serving] + offset_db
        if better:
            a3["count"] = a3["count"] + 1 if a3["candidate"] == best else 1
            a3["candidate"] = best
        else:
            a3["count"], a3["candidate"] = 0, None
        note = f"The phone walks to {k * C.STEP_M:.0f} m. Serving sector {serving}: {rsrp[serving]:.0f} dBm"
        if better:
            note += (f". Sector {best} is {rsrp[best] - rsrp[serving]:.1f} dB stronger "
                     f"({a3['count']} of {ttt_steps} steps)")
        net.say(note, kind="step")
        if a3["count"] < ttt_steps:
            return
        a3.update(serving=best, candidate=None, count=0)    # the twin's serving sector changes
        if not ue.connected:                                # idle: just listen to the new sector
            ue.move_to(best)
            net.say(f"The idle phone now listens to sector {best} (same tracking area, so no messages)")
        elif best[0] == ue.cell[0]:                         # another sector of the same site: same gNB
            ue.move_to(best)
            net.say(f"Sector {best} is on the same gNB: the gNB switches sector itself (no core messages)")
        else:                                               # another site: Xn handover (flow 5)
            net.flow = 5
            ue.measurement_report(best, rsrp[serving], rsrp[best])

    def send_data(k):                                       # flow 4
        net.step, net.flow = k, 4
        if ue.connected:
            ue.send_request()

    def walk_ends():
        net.flow = 6
        net.say("The walk has ended. The phone stays here; no more data, so the gNB's inactivity timer runs")

    def chat_message():                                     # flow 6: data for the idle phone
        net.flow = 6
        internet.push(f"{C.UPF_PUBLIC_IP}:50001")

    last_data = 0
    for k in range(steps):
        net.at(k * STEP_MS, walk_step, k)
        if k % C.DATA_EVERY_STEPS == 2:                     # steps 2, 7, 12, ...
            last_data = k * STEP_MS + STEP_MS / 2
            net.at(last_data, send_data, k)
    net.at((steps - 1) * STEP_MS + 1, walk_ends)
    chat_at = last_data + (C.INACTIVITY_S + C.CHAT_AFTER_IDLE_S) * 1000     # the phone is idle by then
    net.at(chat_at, chat_message)
    net.run(until_ms=chat_at + 1000)
    return net, ue


def page_log(log):
    """The log as the page uses it (arrival times dropped; the message fields are kept for the packet view)."""
    for e in log:
        e.pop("t_arrive", None)
    return log


LABEL_OVERRIDES = ROOT / "data" / "label_overrides.json"
FOOTPRINTS_V2 = ROOT / "scenes" / "iitgn_v2" / "footprints.geojson"


def label_building(name, x, y, feats):
    """Building id under a campus label: the v2 footprint that contains the label point and whose OSM name
    contains the label text (labels are shortened OSM names; one point can sit inside two footprints)."""
    from shapely.geometry import Point
    p = Point(x, y)
    inside = [(bid, nm) for bid, nm, poly in feats if poly.distance(p) < 1.0]
    for bid, nm in inside:
        if name.lower() in nm.lower():
            return bid
    return inside[0][0] if len(inside) == 1 else None


def apply_label_overrides(context):
    """Rename / hide 3D campus labels by building id (data/label_overrides.json). Page only: buildings.csv,
    the scene and every radio result keep the OSM names and geometry."""
    if not (LABEL_OVERRIDES.exists() and FOOTPRINTS_V2.exists() and context.get("labels")):
        return
    from shapely.geometry import shape
    ov = json.loads(LABEL_OVERRIDES.read_text())
    rename, hide = ov.get("rename", {}), set(ov.get("hide", []))
    feats = [(f["properties"]["id"], f["properties"]["name"] or "", shape(f["geometry"]))
             for f in json.loads(FOOTPRINTS_V2.read_text())["features"]]
    out, done = [], []
    for name, x, y, *rest in context["labels"]:
        bid = label_building(name, x, y, feats)
        if bid in hide:
            done.append(f"hid {name!r} ({bid})"); continue
        if bid in rename:
            done.append(f"{name!r} -> {rename[bid]!r} ({bid})"); name = rename[bid]
        out.append([name, x, y, *rest])
    context["labels"] = out
    missing = (set(rename) | hide) - {d.rsplit("(", 1)[1].rstrip(")") for d in done}
    print("4. labels:", "; ".join(done) + (f"; not found: {sorted(missing)}" if missing else ""))


def build_page(twin, logs, default_route=C.DEFAULT_ROUTE):
    """Step 4: one file with everything inside (data and 3D library), so it opens offline by double-click."""
    for log in logs.values():                               # the page does not need the message contents
        page_log(log)
    tasks_file = ROOT / "data" / "demo_tasks.json"                 # saved by tasks 1, 6 and 7 for the Scenario box and tabs
    tasks = json.loads(tasks_file.read_text()) if tasks_file.exists() else {}
    data = dict(twin=twin, logs=logs, flows=FLOWS, identities=IDENTITIES, default_route=default_route,
                step_m=C.STEP_M, tasks=tasks)
    # optional: the corrected twin v2 (tasks/task9_scene_v2.py) and the campus layers (tools/campus_context.py)
    # pcap: one masked example frame per message type from the class captures (tools/extract_pcap.py)
    for key, name in (("v2", "scene_v2.json"), ("context", "campus_context.json"), ("pcap", "pcap_examples.json")):
        f = ROOT / "data" / name
        if f.exists():
            data[key] = json.loads(f.read_text())
    if "context" in data:
        apply_label_overrides(data["context"])
    libs ="".join("<script>\n" + (ROOT / "vendor" / f).read_text(encoding="utf-8").replace("</script", "<\\/script") + "\n</script>\n"
                   for f in ("three.min.js", "OrbitControls.js"))
    page = (ROOT / "viewer.html").read_text(encoding="utf-8")
    page = page.replace("<!--LIBRARIES-->", libs).replace("/*DATA*/null", json.dumps(data).replace("</", "<\\/"))
    (ROOT / "twin.html").write_text(page, encoding="utf-8")


WALK_V2 = ROOT / "data" / "study_v2" / "walk_routes.json"      # task 10: walking routes on twin v2
DEFAULT_WALK_ROUTE = 1                                         # "Hostels -> Lal Minar": one clean Xn handover


def main():
    twin = get_twin()
    print("1. twin: loaded data/twin.json")
    default_route = C.DEFAULT_ROUTE
    if WALK_V2.exists():                                     # the demo walks task 10's v2 routes (twin.json unchanged)
        walk = json.loads(WALK_V2.read_text())
        twin = dict(twin, routes=walk["routes"], walk_scene="v2")
        print(f"   walking routes: {WALK_V2.relative_to(ROOT)} (twin v2, campus roads)")
    sectors = [s["name"] for s in twin["sectors"]]
    logs, xn_count = {}, {}
    for route in twin["routes"]:
        net, ue = simulate(route, sectors)
        logs[route["id"]] = net.log
        msgs = [e for e in net.log if e["kind"] == "msg"]
        ho = [e for e in msgs if e["message"] == "HandoverRequest"]
        xn_count[route["id"]] = len(ho)
        print(f"2-3. route {route['id']} {route.get('name', '')}: {len(msgs)} messages, {len(ho)} Xn handovers "
              + (f"(to {', '.join(e['fields']['target_cell'] for e in ho)} at steps {[e['step'] for e in ho]})" if ho else ""))
        if "a3_handovers" in route:                          # the Xn handovers must be exactly task 10's site changes
            want = [h["step"] for h in route["a3_handovers"] if h["xn"]]
            got = [e["step"] for e in ho]
            assert got == want, f"route {route['id']}: Xn at steps {got}, task 10's site changes at {want}"
            print(f"     matches task 10: site changes at steps {want}")
    if WALK_V2.exists():
        default_route = DEFAULT_WALK_ROUTE
    build_page(twin, logs, default_route)
    print(f"4. wrote twin.html ({(ROOT / 'twin.html').stat().st_size / 1e6:.1f} MB); route {default_route} is shown first")


if __name__ == "__main__":
    main()
