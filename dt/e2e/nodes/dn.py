"""
Data-network server: once a UE has asked for it (uplink request), streams Poisson packets to it over
N6. Each UE's packet process is seeded by its index, so B1 and T3 runs see identical traffic.
"""
from ..engine import Node
from ..userplane import Batch, make_source


class DNServer(Node):
    kind = "DN"

    def __init__(self, name, net, traffic, seed):
        super().__init__(name, net)
        self.traffic = traffic
        self.rate, self.pkt, self.seed = traffic["rate_mbps"], int(traffic["packet_bytes"]), seed
        self.flows = {}                # ue -> dict(upf, ip, src, start)
        self.sent = {}
        self.sent_gen = {}             # ue -> generation times of every packet sent [ms]

    def on_IPPacket(self, m):          # uplink request from a UE: start its downlink stream
        if m.ue not in self.flows:
            self.flows[m.ue] = dict(upf=m.src, ip=m.payload.get("src_ip"), start=None,
                                    src=make_source(self.traffic, self.seed * 1000 + int(m.ue[2:])))

    def tick(self, epoch, t0, t1):
        """Send the packets each active flow generates in [t0, t1) as one batch per UE."""
        for ue, f in self.flows.items():
            if f["start"] is None:
                f["start"] = t0                       # streams start at the first epoch after the request
            times = f["src"].until(t1)
            times = times[times >= f["start"]]
            if not len(times):
                continue
            b = Batch(times, self.pkt)
            self.sent[ue] = self.sent.get(ue, 0) + b.bytes
            self.sent_gen.setdefault(ue, []).append(times)
            self.send(f["upf"], "N6", "User Plane DL", "IPPacket", ue=ue, bytes=b.bytes, packets=len(b),
                      direction="DL", dst_ip=f["ip"], epoch=epoch, _batch=b)
