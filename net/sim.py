"""
The clock and the message log that every network element uses.

* Network  - holds the elements and the clock. send() delivers a message after the interface's delay, writes
             it to the log, and remembers every identity the message carries (for the identity panel).
* Element  - base class of UE, gNB, AMF, ... A message called "X" is handled by the element's method on_X.
Times are in milliseconds.
"""
import heapq
import itertools

import config as C

# identities shown at the bottom of the page: message field -> label
IDENTITIES = {
    "suci": "SUCI", "supi": "SUPI", "guti": "5G-GUTI", "s_tmsi": "5G-S-TMSI", "c_rnti": "C-RNTI",
    "ran_ue_ngap_id": "RAN UE NGAP ID", "amf_ue_ngap_id": "AMF UE NGAP ID", "ul_teid": "TEID uplink (UPF)",
    "dl_teid": "TEID downlink (gNB)", "pdu_session_id": "PDU session ID", "ue_ip": "UE IP", "s_nssai": "S-NSSAI",
    "qfi": "QFI", "five_qi": "5QI",
}

FLOWS = {1: "Broadcast, random access, RRC setup", 2: "Registration", 3: "PDU session",
         4: "Uplink and downlink data", 5: "Handover over Xn", 6: "Idle and paging"}


class Network:
    def __init__(self):
        self.now = 0.0
        self._queue, self._order = [], itertools.count()
        self.elements = {}
        self.log = []               # everything that happened, in order: what the page plays back
        self.ids = {}               # identities in use right now
        self.flow = 1               # which of the six flows is running
        self.step = 0               # where the UE is on the walk
        self.serving = None         # the sector (cell) the UE is connected to, or camps on when idle, e.g. "B225"
        self.ue_state = "off"       # "RRC connected" or "RRC idle"

    def add(self, element):
        self.elements[element.name] = element
        return element

    # ---- the clock
    def at(self, t_ms, fn, *args):
        heapq.heappush(self._queue, (t_ms, next(self._order), fn, args))

    def run(self, until_ms):
        while self._queue and self._queue[0][0] <= until_ms:
            self.now, _, fn, args = heapq.heappop(self._queue)
            fn(*args)

    # ---- messages
    def send(self, src, dst, interface, message, note, nas=None, **fields):
        t_arrive = self.now + C.DELAY_MS[interface]
        for key, value in fields.items():
            if key in IDENTITIES:
                self.ids[key] = value
        self.log.append(dict(kind="msg", t=round(self.now, 2), t_arrive=round(t_arrive, 2), flow=self.flow,
                             step=self.step, serving=self.serving, ue_state=self.ue_state, src=src, dst=dst,
                             interface=interface, message=message, nas=nas, note=note, fields=fields,
                             carries=[k for k in fields if k in IDENTITIES], ids=dict(self.ids)))
        msg = dict(src=src, message=message, nas=nas, flow=self.flow, **fields)
        self.at(t_arrive + C.PROCESSING_MS, self.elements[dst].receive, msg)

    def say(self, note, kind="info", **extra):
        """Something that is not a message (the UE takes a step, the twin's A3 rule fires, ...)."""
        self.log.append(dict(kind=kind, t=round(self.now, 2), flow=self.flow, step=self.step, note=note,
                             serving=self.serving, ue_state=self.ue_state,
                             ids=dict(self.ids), **extra))

    def forget(self, *keys):
        """Identities that stop being used (e.g. the C-RNTI when the phone goes idle)."""
        for k in keys:
            self.ids.pop(k, None)


class Element:
    def __init__(self, name, net):
        self.name, self.net = name, net

    def send(self, dst, interface, message, note, **fields):
        self.net.send(self.name, dst, interface, message, note, **fields)

    def receive(self, msg):
        self.net.flow = msg["flow"]                  # whatever this message causes belongs to the same flow
        handler = getattr(self, "on_" + msg["message"], None)
        if handler is None:
            raise RuntimeError(f"{self.name} has no handler for {msg['message']} from {msg['src']}")
        handler(msg)
