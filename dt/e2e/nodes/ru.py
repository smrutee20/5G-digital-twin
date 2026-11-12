"""RU (one of the 9 sectors): RF + low PHY. Relays Uu <-> fronthaul (O-RAN 7.2x eCPRI)."""
from ..engine import Node


class RU(Node):
    kind = "RU"

    def __init__(self, name, net, du, sector):
        super().__init__(name, net)
        self.du, self.sector = du, sector

    def receive(self, m):
        p = {k: v for k, v in m.payload.items() if k != "ref_point"}
        if m.interface == "Uu":                     # uplink from a UE -> DU
            self.send(self.du, "fronthaul", m.procedure, "UPlaneUL", ue=m.ue, uu=m.message, **p)
        else:                                       # downlink from the DU -> UE over the air
            uu = p.pop("uu")
            self.send(m.ue, "Uu", m.procedure, uu, ue=m.ue, **p)
