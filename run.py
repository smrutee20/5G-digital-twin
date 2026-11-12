"""
One command for everything:   python run.py      then open twin.html (double-click; works offline).

  Step 1  the twin: load data/twin.json (buildings, sectors, RSRP map, 3 routes, all from the study's ray tracing)
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


def simulate(route, sector_names):
    """Step 3: schedule the walk and the events on it, then run the clock."""
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
        # A3 rule: another sector must be 3 dB stronger than the serving one for 2 steps in a row
        serving = a3["serving"]
        better = best != serving and rsrp[best] > rsrp[serving] + C.A3_OFFSET_DB
        if better:
            a3["count"] = a3["count"] + 1 if a3["candidate"] == best else 1
            a3["candidate"] = best
        else:
            a3["count"], a3["candidate"] = 0, None
        note = f"The phone walks to {k * C.STEP_M:.0f} m. Serving sector {serving}: {rsrp[serving]:.0f} dBm"
        if better:
            note += (f". Sector {best} is {rsrp[best] - rsrp[serving]:.1f} dB stronger "
                     f"({a3['count']} of {C.A3_STEPS} steps)")
        net.say(note, kind="step")
        if a3["count"] < C.A3_STEPS:
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


def build_page(twin, logs):
    """Step 4: one file with everything inside (data and 3D library), so it opens offline by double-click."""
    for log in logs.values():                               # the page does not need the message contents
        for e in log:
            e.pop("fields", None)
            e.pop("t_arrive", None)
    tasks_file = ROOT / "data" / "demo_tasks.json"                 # saved by tasks 1, 6 and 7 for the Scenario box and tabs
    tasks = json.loads(tasks_file.read_text()) if tasks_file.exists() else {}
    data = dict(twin=twin, logs=logs, flows=FLOWS, identities=IDENTITIES, default_route=C.DEFAULT_ROUTE,
                step_m=C.STEP_M, tasks=tasks)
    libs = "".join("<script>\n" + (ROOT / "vendor" / f).read_text(encoding="utf-8").replace("</script", "<\\/script") + "\n</script>\n"
                   for f in ("three.min.js", "OrbitControls.js"))
    page = (ROOT / "viewer.html").read_text(encoding="utf-8")
    page = page.replace("<!--LIBRARIES-->", libs).replace("/*DATA*/null", json.dumps(data).replace("</", "<\\/"))
    (ROOT / "twin.html").write_text(page, encoding="utf-8")


def main():
    twin = get_twin()
    print("1. twin: loaded data/twin.json")
    sectors = [s["name"] for s in twin["sectors"]]
    logs = {}
    for route in twin["routes"]:
        net, ue = simulate(route, sectors)
        logs[route["id"]] = net.log
        msgs = [e for e in net.log if e["kind"] == "msg"]
        handovers = [f"{e['fields']['target_cell']}" for e in msgs if e["message"] == "HandoverRequest"]
        print(f"2-3. route {route['id']}: {len(msgs)} messages, {len(handovers)} Xn handovers "
              f"{'(to ' + ', '.join(handovers) + ')' if handovers else ''}")
    build_page(twin, logs)
    print(f"4. wrote twin.html ({(ROOT / 'twin.html').stat().st_size / 1e6:.1f} MB); route {C.DEFAULT_ROUTE} is shown first")


if __name__ == "__main__":
    main()
