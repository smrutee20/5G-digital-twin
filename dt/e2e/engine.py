"""
Discrete-event engine for the end-to-end 5G flow layer.

* `Sim`      — event queue ordered by (time, insertion order), so every run is deterministic.
* `Message`  — one protocol message on one interface (one hop).
* `Node`     — base class of every network element. A message is handled by the method
               `on_<MessageName>`; a reply to a `request()` is handled by the callback given there.
* `Network`  — owns the elements, checks that each message uses a legal interface between
               the right element types, applies interface latency + receiver processing time,
               and logs every message to the trace.
Times are in milliseconds.
"""
import heapq
import itertools
import math
import re
from dataclasses import dataclass, field

from .interfaces import check_link, latency_key, ref_point


class Sim:
    def __init__(self):
        self.now = 0.0
        self._q = []
        self._seq = itertools.count()

    def at(self, t, fn, *args):
        heapq.heappush(self._q, (t, next(self._seq), fn, args))

    def after(self, dt, fn, *args):
        self.at(self.now + dt, fn, *args)

    def run(self, until):
        while self._q and self._q[0][0] <= until:
            t, _, fn, args = heapq.heappop(self._q)
            self.now = t
            fn(*args)
        self.now = until


@dataclass
class Message:
    src: str
    dst: str
    interface: str
    procedure: str
    message: str
    ue: str = None
    tid: int = None           # transaction id of a request
    reply_to: int = None      # set on replies: the request's tid
    payload: dict = field(default_factory=dict)
    t_sent: float = 0.0
    t_arrive: float = 0.0


def handler_name(message):
    return "on_" + re.sub(r"\W+", "_", message).strip("_")


class Node:
    kind = "?"

    def __init__(self, name, net):
        self.name, self.net, self.sim = name, net, net.sim
        self._pending = {}
        self.nf_cache = {}
        self.down = False           # switched off (what-if): sends nothing, receives nothing          # SBI: NF type -> instance name, filled by NRF discovery

    # ------------------------------------------------------------- messaging
    def send(self, dst, interface, procedure, message, ue=None, **payload):
        self.net.transmit(Message(self.name, dst, interface, procedure, message, ue, payload=payload))

    def request(self, dst, interface, procedure, message, on_reply, ue=None, **payload):
        tid = self.net.new_tid()
        self._pending[tid] = on_reply
        self.net.transmit(Message(self.name, dst, interface, procedure, message, ue, tid=tid, payload=payload))

    def reply(self, req, message, **payload):
        self.net.transmit(Message(self.name, req.src, req.interface, req.procedure, message, req.ue,
                                  reply_to=req.tid, payload=payload))

    def receive(self, m):
        if self.down:
            return
        if m.reply_to is not None:
            self._pending.pop(m.reply_to)(m)
            return
        h = getattr(self, handler_name(m.message), None)
        if h is None:
            raise RuntimeError(f"{self.name} cannot handle {m.message} ({m.interface} from {m.src})")
        h(m)

    # ------------------------------------------------------------- SBI helper
    def discover(self, nf_type, procedure, then, ue=None):
        """Find an NF instance through the NRF (Nnrf_NFDiscovery), then call then(instance)."""
        if nf_type in self.nf_cache:
            then(self.nf_cache[nf_type])
            return

        def got(r):
            self.nf_cache[nf_type] = r.payload["nf_instance"]
            then(r.payload["nf_instance"])
        self.request("NRF", "SBI", procedure, "Nnrf_NFDiscovery_Request", got, ue=ue,
                     target_nf_type=nf_type, requester_nf_type=self.kind)

    def start(self):
        """Called once at t = 0 (start-up procedures)."""


class Network:
    def __init__(self, e2e_cfg, slot_ms, trace):
        self.sim = Sim()
        self.nodes = {}
        self.trace = trace
        self.lat = {k: float(v) for k, v in e2e_cfg["latency_ms"].items() if k != "Uu"}
        self.proc = {k: float(v) for k, v in e2e_cfg["processing_ms"].items()}
        self.slot_ms = slot_ms
        self._tid = itertools.count(1)
        self.ip_table = {}             # transport IP address -> element name (GTP-U tunnel endpoints)
        self.lost_bytes = 0            # user data sent towards a switched-off element

    def add(self, node):
        assert node.name not in self.nodes, node.name
        self.nodes[node.name] = node
        return node

    def link_ms(self, interface):
        """Fixed transport latency of an interface (not Uu, which the DU scheduler handles per slot)."""
        return self.lat[latency_key(interface)]

    def route(self, ip):
        return self.ip_table[ip]

    def new_tid(self):
        return next(self._tid)

    def link_delay(self, interface, now):
        if interface == "Uu":
            # air interface: wait for the next slot boundary, then one slot on the air
            nxt = math.floor(now / self.slot_ms + 1e-9) * self.slot_ms + self.slot_ms
            return nxt - now + self.slot_ms
        return self.lat[latency_key(interface)]

    def transmit(self, m):
        a, b = self.nodes[m.src], self.nodes[m.dst]
        check_link(m.interface, a.kind, b.kind)
        if a.down:
            return
        if b.down:                     # logged, never delivered
            m.payload["delivered"] = False
            if "_batch" in m.payload:
                self.lost_bytes += m.payload["_batch"].bytes
        m.t_sent = self.sim.now
        m.t_arrive = m.t_sent + self.link_delay(m.interface, m.t_sent)
        rp = ref_point(m.interface, a.kind, b.kind)
        if rp:
            m.payload.setdefault("ref_point", rp)
        self.trace.log(m)
        if not b.down:
            self.sim.at(m.t_arrive + self.proc[b.kind], b.receive, m)
