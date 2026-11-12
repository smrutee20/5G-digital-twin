"""
Builds the end-to-end network on top of the radio twin and runs it.

Topology: one gNB per site (CU-CP + CU-UP + DU, 3 RUs each), gNBs connected by Xn, all on N2/N3 to the
core (AMF, SMF, UPF-EDGE, UPF-CENTRAL, AUSF, UDM, NRF, PCF) and a data-network server.

Scenarios
  attach    static UEs (e03 drop): attach, registration, PDU session, downlink traffic      (e09, e10)
  mobility  static UEs + one UE on each e05 walk; A3 in the twin triggers handovers          (e11)
  site_off  static UEs; one site is switched off; its UEs fail over and come back (Service Request)  (e11)
"""
import itertools

import numpy as np

from .engine import Network
from .interfaces import INTERFACES, DESCRIPTION
from .radio import RadioLayer
from .trace import Trace
from .nodes import UE, RU, DU, CUCP, CUUP, AMF, SMF, UPF, AUSF, UDM, NRF, PCF, DNServer


class E2ENetwork:
    def __init__(self, cfg, data_dir, strategy="T3", scenario="attach"):
        self.cfg, e = cfg, cfg["e2e"]
        self.e, self.scenario = e, scenario
        mob = e["mobility"]
        walks = [1, 2, 3] if scenario == "mobility" else []
        n_static = mob["static_ues"] if walks else e["num_ues"]
        self.radio = RadioLayer(cfg, data_dir, e["drop"], n_static, strategy, walks)
        self.trace = Trace()
        self.net = net = Network(e, self.radio.slot_ms, self.trace)
        net.cell_owner = {}
        _ho = itertools.count(1)
        net.new_ho_id = lambda: next(_ho)
        self.epoch_ms = e["epoch_slots"] * self.radio.slot_ms

        # ---- core network + data network
        net.add(NRF("NRF", net))
        self.dn = net.add(DNServer("DN", net, e["traffic"], e["seed"]))
        self.upfs = [net.add(UPF(u["name"], net, u, "DN")).name for u in e["upfs"]]
        net.add(AMF("AMF", net, e["tac"]))
        net.add(AUSF("AUSF", net))
        self.subscribers = {}                       # SUCI -> SUPI, filled when the UEs are created
        net.add(UDM("UDM", net, self.subscribers))
        net.add(PCF("PCF", net, e["default_qos"]))
        net.add(SMF("SMF", net, self.upfs))
        # ---- one gNB per site: CU-CP + CU-UP + DU, and the site's three RUs
        self.sites = [s["name"] for s in cfg["ran"]["sites"]]
        self.dus, self.cu_ups, self.gnb_nodes = {}, {}, {}
        for s_i, s in enumerate(self.sites):
            cp = net.add(CUCP(f"CU-CP-{s}", net, "AMF", f"CU-UP-{s}", e["tac"], gnb_id=s_i + 1))
            up = net.add(CUUP(f"CU-UP-{s}", net, f"CU-CP-{s}", f"10.100.0.{11 + s_i}", f"10.200.0.{11 + s_i}"))
            du = net.add(DU(f"DU-{s}", net, s, cp.name, up.name, e["du_buffer_bytes"], e["air"],
                            cfg["carrier"]["bler_target"], seed=e["seed"] * 10 + s_i, slot_ms=self.radio.slot_ms))
            du.served_cells = [f"RU-{n}" for n, si in zip(self.radio.ru_names, self.radio.ru_site) if si == s_i]
            self.dus[s_i], self.cu_ups[s_i] = du, up
            self.gnb_nodes[s] = [cp, up, du]
        self.rus = []
        for r, (n, si) in enumerate(zip(self.radio.ru_names, self.radio.ru_site)):
            ru = net.add(RU(f"RU-{n}", net, f"DU-{self.sites[si]}", n))
            self.rus.append(ru.name)
            net.cell_owner[ru.name] = (f"DU-{self.sites[si]}", f"CU-CP-{self.sites[si]}")
            self.gnb_nodes[self.sites[si]].append(ru)
        self.ru_index = {n: i for i, n in enumerate(self.rus)}
        # ---- UEs: static ones first, then one per walk; each camps on the cell its strategy chooses
        self.ues, self.walker = [], {}
        movers_only = walks and mob.get("traffic", "walkers") == "walkers"
        for u in range(n_static + len(walks)):
            ue = net.add(UE(f"UE{u:02d}", net, u, self.rus[self.radio.serving[u]], supi=f"imsi-0010100000{u + 1:05d}"))
            self.subscribers[ue.suci] = ue.supi
            if u >= n_static:
                self.walker[ue.name] = walks[u - n_static]
            ue.app = (not movers_only) or ue.name in self.walker
            ue.ho_processing_ms, ue.prach_period_ms = mob["ue_rrc_processing_ms"], mob["prach_period_ms"]
            self.ues.append(ue)
        self.ue_by_name = {u.name: u for u in self.ues}
        self.ru_on = np.ones(len(self.rus), bool)
        self.a3 = {}                                 # walker -> (candidate RU, consecutive steps)
        self.kpi = []

    def du_of(self, ue):
        return next((du for du in self.dus.values() if ue in du.drb and not du.down), None)

    # ------------------------------------------------------------------ run
    def run(self):
        e, sim = self.e, self.net.sim
        for node in list(self.net.nodes.values()):
            sim.at(0.0, node.start)
        rng = np.random.default_rng(e["seed"])
        t_on = np.sort(rng.uniform(e["attach_start_ms"], e["attach_start_ms"] + e["attach_window_ms"], len(self.ues)))
        for ue, t in zip(self.ues, t_on):
            sim.at(float(t), ue.power_on)
        end = e["duration_ms"]
        if self.scenario == "mobility":
            m = e["mobility"]
            self.step_ms = 2.0 / m["speed_mps"] * 1e3
            for j in range(1, self.radio.steps):
                sim.at(m["walk_start_ms"] + j * self.step_ms, self.move, j)
            end = m["walk_start_ms"] + self.radio.steps * self.step_ms + 1000
        elif self.scenario == "site_off":
            so = e["site_off"]
            sim.at(so["t_ms"], self.switch_off, so["site"])
            end = so["duration_ms"]
        self.n_epochs = n = int(end // self.epoch_ms)
        for k in range(0, n + 1):
            sim.at(k * self.epoch_ms, self.epoch, k)
        self.radio_log = []
        sim.run(n * self.epoch_ms + 50.0)            # let the last messages arrive
        return self

    def epoch(self, k):
        """
        At t = k * epoch: every DU serves up to now and reports the epoch that just ended; then the radio
        twin's scheduler (B1 or T3) gives each schedulable UE its rate for the next epoch; then the DN emits
        the next epoch's packets.
        """
        E, n, t = self.epoch_ms, self.e["epoch_slots"], k * self.epoch_ms
        alive = [du for du in self.dus.values() if not du.down]
        for du in alive:
            du.advance(t)
            if k >= 1:
                du.flush(k)
        if k >= self.n_epochs:
            return
        sched = [(self.ue_by_name[u], du) for du in alive for u in du.schedulable(t)]
        sched.sort(key=lambda x: x[0].idx)
        rates = {du.name: {} for du in alive}
        res = None
        if sched:
            rows = [ue.idx for ue, _ in sched]
            serving = [self.ru_index[du.ue_ru[ue.name]] for ue, du in sched]
            bits, res = self.radio.schedule_now(rows, serving, self.ru_on, n,
                                                np.random.default_rng(self.e["seed"] * 100000 + k))
            for j, (ue, du) in enumerate(sched):
                rates[du.name][ue.name] = float(bits[j] / 8 / n)
                self.radio_log.append(dict(epoch=k + 1, ue=ue.name, capacity_mbps=float(res["thr_mbps"][j]),
                                           sinr_db=float(res["sinr_db"][j]), prbs_per_slot=float(res["prbs_per_slot"][j]),
                                           cqi=float(res["cqi"][j]), serving_ru=self.radio.ru_names[serving[j]]))
        for du in alive:
            du.set_rates(rates[du.name], n)
        # per-UE radio KPIs for the viewer (RSRP from the twin at the UE's current position)
        ch = self.radio.channel()
        sinr = {ue.name: float(res["sinr_db"][j]) for j, (ue, _) in enumerate(sched)} if sched else {}
        cap = {ue.name: float(res["thr_mbps"][j]) for j, (ue, _) in enumerate(sched)} if sched else {}
        for ue in self.ues:
            r = self.ru_index.get(ue.ru)
            self.kpi.append(dict(t_ms=t, ue=ue.name, ru=ue.ru, x=round(float(ch.pos[ue.idx, 0]), 1),
                                 y=round(float(ch.pos[ue.idx, 1]), 1),
                                 rsrp_dbm=round(float(self.radio.p_re + ch.pg_db[ue.idx, r]), 1) if r is not None else None,
                                 sinr_db=round(sinr[ue.name], 1) if ue.name in sinr else None,
                                 capacity_mbps=round(cap[ue.name], 2) if ue.name in cap else None,
                                 state="handover" if ue.ho else ue.rrc_state))
        self.dn.tick(k, t, t + E)

    # ------------------------------------------------------------------ mobility: A3 in the twin
    def move(self, j):
        m = self.e["mobility"]
        for w in self.radio.movers:
            self.radio.step[w] = j
        for name, w in self.walker.items():
            ue = self.ue_by_name[name]
            rsrp = np.where(self.ru_on, self.radio.rsrp_dbm(ue.idx), -np.inf)
            s = self.ru_index[ue.ru]
            best = int(np.argmax(rsrp))
            cand, cnt = self.a3.get(name, (None, 0))
            if best != s and rsrp[best] > rsrp[s] + m["a3_offset_db"]:
                cnt = cnt + 1 if cand == best else 1
                cand = best
            else:
                cand, cnt = None, 0
            if cnt >= m["ttt_steps"]:
                ue.report(self.rus[best], float(rsrp[s]), float(rsrp[best]), "Measurement Report")
                cand, cnt = None, 0
            self.a3[name] = (cand, cnt)

    # ------------------------------------------------------------------ what-if: a site switched off
    def switch_off(self, site):
        t = self.net.sim.now
        s_i = self.sites.index(site)
        du = self.dus[s_i]
        du.advance(t)
        du.flush(int(t // self.epoch_ms))
        self.lost_in_du = sum(du.qbytes.values())
        for node in self.gnb_nodes[site]:
            node.down = True
        self.ru_on = np.array([self.radio.ru_site[i] != s_i for i in range(len(self.rus))])
        self.off = dict(site=site, t_ms=t)
        rlf = self.e["site_off"]["rlf_ms"]
        for ue in self.ues:
            if self.ru_index[ue.ru] in np.where(~self.ru_on)[0]:
                rsrp = np.where(self.ru_on, self.radio.rsrp_dbm(ue.idx), -np.inf)
                self.net.sim.at(t + rlf, ue.radio_link_failure, self.rus[int(np.argmax(rsrp))])

    # ------------------------------------------------------------------ output
    def kpi_table(self):
        """Per UE per epoch: radio (RU, RSRP, SINR, capacity), delivered throughput and mean packet latency."""
        import pandas as pd
        k = pd.DataFrame(self.kpi)
        d = pd.DataFrame([x for du in self.dus.values() for x in du.delivered_log])
        if len(d):
            d["lat_x_bytes"] = d.mean_latency_ms.fillna(0) * d.delivered_bytes
            g = d.groupby(["epoch", "ue"]).agg(delivered=("delivered_bytes", "sum"), lxb=("lat_x_bytes", "sum")).reset_index()
            g["t_ms"] = (g.epoch - 1) * self.epoch_ms
            g["thr_mbps"] = g.delivered * 8 / (self.epoch_ms * 1e3)
            g["latency_ms"] = np.where(g.delivered > 0, g.lxb / g.delivered.where(g.delivered > 0, 1), np.nan)
            k = k.merge(g[["t_ms", "ue", "thr_mbps", "latency_ms"]], on=["t_ms", "ue"], how="left")
        k["thr_mbps"] = k.get("thr_mbps", 0).fillna(0).round(2)
        k["latency_ms"] = k.get("latency_ms", np.nan).round(2)
        return k

    def meta(self):
        e = self.e
        return dict(
            scenario=self.cfg["scene"]["name"], run=self.scenario, seed=e["seed"], ue_drop=e["drop"],
            scheduler=self.radio.strategy, traffic=dict(e["traffic"]), air=dict(e["air"]),
            duration_ms=self.n_epochs * self.epoch_ms, epoch_ms=self.epoch_ms, slot_ms=self.radio.slot_ms,
            elements={n: node.kind for n, node in self.net.nodes.items()},
            gnbs={s: [n.name for n in nodes] for s, nodes in self.gnb_nodes.items()},
            walkers=self.walker, site_off=getattr(self, "off", None),
            interfaces={k: dict(endpoints=sorted(v), description=DESCRIPTION[k]) for k, v in INTERFACES.items()},
            latency_ms=dict(e["latency_ms"]), processing_ms=dict(e["processing_ms"]),
            notes=["One gNB per site (CU-CP + CU-UP + DU); gNBs connected by Xn (Xn-C control, Xn-U forwarding).",
                   "Uu latency = wait for the next slot boundary + one slot.",
                   "User plane: packets travel in per-epoch batches; the trace has one record per epoch per UE "
                   "per hop (bytes, packets); each packet keeps its own timestamps and delay breakdown.",
                   "Air: per-UE capacity per epoch from the radio twin's scheduler (SINR -> CQI -> bits on its PRBs), "
                   "served FIFO slot by slot; + 1 slot on air + HARQ retransmissions (BLER from the config).",
                   "Every UE with a DRB loads its cell for the whole epoch (full-load interference): conservative "
                   "at low traffic.",
                   "NAS (N1) is carried hop by hop: RRC (Uu/fronthaul) -> F1AP (F1-C) -> NGAP (N2); see 'nas'.",
                   "T3 coordinates PRB muting jointly across the gNBs (near-RT RIC/E2 not modelled).",
                   "Traffic: Poisson packets per UE at traffic.rate_mbps (open loop, no TCP).",
                   "Handovers: A3 (offset, time-to-trigger in walk steps) evaluated on the twin's RSRP.",
                   "Messages to a switched-off element are logged with delivered=false.",
                   "Latencies and processing times are configurable assumptions, not measurements."])
