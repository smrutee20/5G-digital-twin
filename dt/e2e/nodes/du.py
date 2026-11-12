"""
DU (one per site / gNB): high PHY, MAC and RLC.

* MAC: random access (contention-based at attach, contention-free with a dedicated preamble at handover).
* RRC is relayed to the gNB's CU-CP over F1-C (F1AP, TS 38.473).
* User data arrives from the CU-UP over F1-U and waits in a per-UE RLC queue (FIFO, tail drop).
* Scheduling: at the start of every epoch the network gives each schedulable UE a rate (bytes per slot)
  from the radio twin's scheduler (B1 or T3: per-PRB SINR -> CQI on the PRBs it allocated). The DU serves
  its queues slot by slot up to "now" whenever something happens (lazy `advance`), so a handover in the
  middle of an epoch sees the right queue. A packet may use a slot only if it reached the DU early enough
  to cross the fronthaul before that slot; then it spends one slot on the air plus HARQ retransmissions.
"""
from collections import deque

import numpy as np

from ..engine import Node
from ..userplane import Batch

ACCESS, DL = "Initial Access", "User Plane DL"
UL_RRC = {"RRCSetupComplete", "ULInformationTransfer", "SecurityModeComplete", "RRCReconfigurationComplete",
          "MeasurementReport"}


class DU(Node):
    kind = "DU"

    def __init__(self, name, net, site, cu_cp, cu_up, buffer_cap_bytes, air, bler, seed, slot_ms):
        super().__init__(name, net)
        self.site, self.cu_cp, self.cu_up, self.cap = site, cu_cp, cu_up, buffer_cap_bytes
        self.slot_ms = slot_ms
        self.ue_ru, self.drb = {}, {}       # UE -> RU it is served on; DRB context (tunnels, set-up time)
        self.queue, self.qbytes = {}, {}    # UE -> deque of [batch, index, bytes_left]
        self.rate, self.credit = {}, {}     # UE -> bytes per slot this epoch; unused bytes in the current slot
        self.suspended = set()              # UEs being handed over (not schedulable)
        self.leaving = set()                # UEs handed over to another gNB (data goes back to the CU-UP)
        self.next_slot = 0.0
        self.pending = {}                   # UE -> [(batch, index, slot_start)] delivered since the last flush
        self.epoch_acc = {}                 # UE -> dict(capacity, served) in the current epoch
        self.dropped, self._rnti, self._teid = 0, 0x4600, 0xD00 + 0x100 * (ord(site) - 64)
        self.dropped_gen = {}               # UE -> generation times of packets tail-dropped (buffer full)
        self.f1u_ip = f"10.200.{ord(site) - 64}.1"
        net.ip_table[self.f1u_ip] = name
        self.harq_rtt, self.max_retx, self.bler = air["harq_rtt_ms"], int(air["max_harq_retx"]), bler
        self.rng = np.random.default_rng(seed)
        self.delivered_log = []

    def start(self):
        self.request(self.cu_cp, "F1-C", "F1 Setup", "F1SetupRequest", lambda r: None,
                     gnb_du_id=self.name, served_cells=self.served_cells)

    def to_ue(self, ue, procedure, uu, **payload):
        self.send(self.ue_ru[ue], "fronthaul", procedure, "UPlaneDL", ue=ue, uu=uu, **payload)

    # ----------------------------------------------------------- fronthaul uplink
    def on_UPlaneUL(self, m):
        uu, ue, p = m.payload["uu"], m.ue, {k: v for k, v in m.payload.items() if k not in ("uu", "ref_point")}
        if uu == "RandomAccessPreamble":                       # MAC: answer with a RAR
            self.ue_ru[ue] = m.src
            self._rnti += 1
            self.to_ue(ue, m.procedure, "RandomAccessResponse", channel="PDSCH", msg="Msg2",
                       c_rnti=hex(self._rnti), timing_advance=0, ul_grant="Msg3")
        elif uu == "RRCSetupRequest":
            self.send(self.cu_cp, "F1-C", m.procedure, "InitialULRRCMessageTransfer", ue=ue, rrc=uu,
                      nr_cgi=m.src, c_rnti=hex(self._rnti), du_to_cu_rrc_container="CellGroupConfig",
                      **{k: v for k, v in p.items() if k not in ("channel", "msg")})
        elif uu in UL_RRC:
            if uu == "RRCReconfigurationComplete" and ue in self.suspended:   # handover done: schedulable here
                self.advance(self.sim.now)
                self.suspended.discard(ue)
            self.send(self.cu_cp, "F1-C", m.procedure, "ULRRCMessageTransfer", ue=ue, rrc=uu, srb_id=1,
                      **{k: v for k, v in p.items() if k != "channel"})
        elif uu == "PUSCH":                                    # user data -> CU-UP over the DRB's F1-U tunnel
            self.send(self.drb[ue]["cu_up"], "F1-U", m.procedure, "G-PDU", ue=ue, bytes=p["bytes"], direction="UL",
                      teid=self.drb[ue]["ul_teid"], qfi=p.get("qfi"), app=p.get("app"))
        else:
            raise RuntimeError(f"{self.name}: unexpected uplink {uu}")

    # ----------------------------------------------------------- F1-C from the CU-CP
    def on_DLRRCMessageTransfer(self, m):
        p = {k: v for k, v in m.payload.items() if k not in ("rrc", "ref_point")}
        self.to_ue(m.ue, m.procedure, m.payload["rrc"], channel="PDSCH", **p)

    def setup_drb(self, ue, d):
        ul = d["ul_up_tnl_information"]
        self._teid += 1
        self.drb[ue] = dict(drb_id=d["drb_id"], ul_teid=ul["gtp_teid"], cu_up=self.net.route(ul["transport_layer_address"]),
                            dl_teid=hex(self._teid), t_setup=self.sim.now, five_qi=d["qos"]["five_qi"])
        self.queue.setdefault(ue, deque())
        self.qbytes.setdefault(ue, 0)
        return dict(drb_id=d["drb_id"], rlc_mode="RLC-AM",
                    dl_up_tnl_information=dict(gtp_teid=hex(self._teid), transport_layer_address=self.f1u_ip))

    def on_UEContextSetupRequest(self, m):
        p = m.payload
        if p.get("handover"):                                  # incoming handover: context before the UE arrives
            self.ue_ru[m.ue] = p["target_cell"]
            self.suspended.add(m.ue)
        if p.get("rrc"):
            self.to_ue(m.ue, m.procedure, p["rrc"], channel="PDSCH")
        drbs = [self.setup_drb(m.ue, d) for d in p.get("drbs_to_be_setup", [])]
        self.reply(m, "UEContextSetupResponse", srbs_setup="SRB1, SRB2", du_to_cu_rrc_information="CellGroupConfig",
                   **({"drbs_setup": drbs} if drbs else {}))

    def on_UEContextModificationRequest(self, m):
        p = m.payload
        if p.get("transmission_action_indicator") == "stop":   # handover command: stop serving this UE here
            self.advance(self.sim.now)
            self.flush(None, only=m.ue)
            self.to_ue(m.ue, m.procedure, p["rrc"], channel="PDSCH",
                       **{k: v for k, v in p.items() if k in ("reconfiguration_with_sync", "target_cell", "ho_id",
                                                              "rach_config_dedicated")})
            self.suspended.add(m.ue)
            if not p["intra_du"]:                              # Xn: undelivered data goes back to the CU-UP
                self.leaving.add(m.ue)
                self.return_queue(m.ue, m.procedure)
            self.reply(m, "UEContextModificationResponse")
            return
        drbs = [self.setup_drb(m.ue, d) for d in p["drbs_to_be_setup"]]
        self.reply(m, "UEContextModificationResponse", drbs_setup=drbs)

    def return_queue(self, ue, procedure):
        q = self.queue.get(ue)
        if not q:
            return
        batch = Batch.concat([it[0].take(np.array([it[1]])) for it in q])
        batch.hold_until(self.sim.now, "du_queue")
        q.clear()
        self.qbytes[ue] = 0
        self.send(self.drb[ue]["cu_up"], "F1-U", procedure, "DLDataDeliveryStatus", ue=ue, delivered_bytes=0,
                  returned_packets=len(batch), returned_bytes=batch.bytes, _batch=batch)

    def on_UEContextReleaseCommand(self, m):
        self.advance(self.sim.now)
        for d in (self.ue_ru, self.drb, self.queue, self.qbytes, self.rate, self.credit, self.pending):
            d.pop(m.ue, None)
        self.suspended.discard(m.ue)
        self.leaving.discard(m.ue)
        self.reply(m, "UEContextReleaseComplete")

    # ----------------------------------------------------------- F1-U from the CU-UP
    def on_G_PDU(self, m):
        b = m.payload["_batch"].hop(self.net.link_ms("F1-U"), "midhaul", self.net.proc["DU"], "ran_proc")
        if m.ue in self.leaving:                               # arrived after the handover command: bounce back
            self.send(self.drb[m.ue]["cu_up"], "F1-U", m.procedure, "DLDataDeliveryStatus", ue=m.ue,
                      delivered_bytes=0, returned_packets=len(b), returned_bytes=b.bytes, _batch=b)
            return
        q = self.queue[m.ue]
        for i in range(len(b)):                                # RLC tail drop when the buffer is full
            if self.qbytes[m.ue] + b.size[i] > self.cap:
                self.dropped += int(b.size[i])
                self.dropped_gen.setdefault(m.ue, []).append(float(b.gen[i]))
                continue
            q.append([b, i, int(b.size[i])])
            self.qbytes[m.ue] += int(b.size[i])

    # ----------------------------------------------------------- MAC scheduling
    def schedulable(self, t0):
        """UEs with a DRB, served here and not in a handover (all load their cell: full-load interference)."""
        return [u for u, d in self.drb.items() if d["t_setup"] <= t0 and u not in self.suspended
                and u not in self.leaving and u in self.ue_ru]

    def set_rates(self, rates, n_slots):
        """rates: UE -> bytes per slot for the epoch that starts now (from the radio twin's scheduler)."""
        self.rate = dict(rates)
        for u, r in rates.items():
            self.epoch_acc.setdefault(u, dict(capacity=0.0, served=0.0))["capacity"] += r * n_slots

    def advance(self, t):
        """Serve every slot that starts before t."""
        lead = self.net.link_ms("fronthaul") + self.net.proc["RU"]   # DU -> RU before the slot starts
        active = [u for u, r in self.rate.items() if r > 0 and u not in self.suspended and self.queue.get(u)]
        s = self.next_slot
        while s < t - 1e-9:
            for u in active:
                q = self.queue[u]
                credit = self.credit.get(u, 0.0) + self.rate[u]
                while q and credit >= 1 and q[0][0].t[q[0][1]] + lead <= s + 1e-9:
                    item = q[0]
                    n = min(item[2], int(credit))
                    item[2] -= n
                    credit -= n
                    self.epoch_acc[u]["served"] += n
                    if item[2] == 0:                        # last byte of the packet sent in this slot
                        q.popleft()
                        self.qbytes[u] -= int(item[0].size[item[1]])
                        self.pending.setdefault(u, []).append((item[0], item[1], s))
                # unused PRBs in this slot are not saved for later
                self.credit[u] = credit if (q and q[0][0].t[q[0][1]] + lead <= s + 1e-9) else 0.0
            s += self.slot_ms
        self.next_slot = s

    def flush(self, epoch, only=None):
        """Send what was delivered since the last flush (one PDSCH record per UE) and log the epoch."""
        lead = self.net.link_ms("fronthaul") + self.net.proc["RU"]
        # sorted: the HARQ draws below must come in a fixed UE order, or runs differ with Python's hash seed
        for u in ([only] if only else sorted(set(self.pending) | set(self.epoch_acc))):
            done = self.pending.pop(u, [])
            out = Batch.concat([b.take(np.array([i])) for b, i, _ in done]) if done else Batch([], 0)
            if done:
                s_last = np.array([s for _, _, s in done])
                out.comp["du_queue"] += s_last - (out.t + lead)
                out.comp["fronthaul"] += lead
                k = np.minimum(self.rng.geometric(1 - self.bler, len(out)) - 1, self.max_retx)
                out.comp["air"] += self.slot_ms + k * self.harq_rtt
                out.t = s_last + self.slot_ms + k * self.harq_rtt
                self.to_ue(u, DL, "PDSCH", channel="PDSCH", bytes=out.bytes, packets=len(out), epoch=epoch,
                           drb=self.drb[u]["drb_id"] if u in self.drb else None, _batch=out)
            if only is None:
                acc = self.epoch_acc.pop(u, dict(capacity=0.0, served=0.0))
                lat = float(np.mean(out.t - out.gen)) if len(out) else None
                self.delivered_log.append(dict(epoch=epoch, ue=u, capacity_bytes=acc["capacity"],
                                               served_bytes=acc["served"], delivered_bytes=out.bytes,
                                               queue_bytes=self.qbytes.get(u, 0), mean_latency_ms=lat))
                if u in self.drb and u in self.ue_ru:
                    self.send(self.drb[u]["cu_up"], "F1-U", DL, "DLDataDeliveryStatus", ue=u,
                              delivered_bytes=out.bytes, desired_buffer_size=self.cap - self.qbytes.get(u, 0),
                              epoch=epoch)
            elif done:
                acc = self.epoch_acc.setdefault(u, dict(capacity=0.0, served=0.0))
                self.delivered_log.append(dict(epoch=epoch, ue=u, capacity_bytes=0.0, served_bytes=0.0,
                                               delivered_bytes=out.bytes, queue_bytes=self.qbytes.get(u, 0),
                                               mean_latency_ms=float(np.mean(out.t - out.gen))))
