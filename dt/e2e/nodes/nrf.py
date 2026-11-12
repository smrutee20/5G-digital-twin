"""NRF: NF repository; NF registration and discovery."""
from ..engine import Node


class NRF(Node):
    kind = "NRF"

    def __init__(self, name, net):
        super().__init__(name, net)
        self.registry = {}             # nf_type -> [instance names]

    def on_Nnrf_NFManagement_NFRegister(self, m):
        self.registry.setdefault(m.payload["nf_type"], []).append(m.payload["nf_instance"])
        self.reply(m, "Nnrf_NFManagement_NFRegister_Response", status="201 Created", heartbeat_s=60)

    def on_Nnrf_NFDiscovery_Request(self, m):
        found = self.registry.get(m.payload["target_nf_type"])
        if not found:
            raise RuntimeError(f"NRF: no {m.payload['target_nf_type']} registered yet (t={self.sim.now} ms)")
        self.reply(m, "Nnrf_NFDiscovery_Response", status="200 OK", nf_instance=found[0])
