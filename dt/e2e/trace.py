"""Message trace: every message on every interface, written to results/<tag>/e2e_trace.json."""
import json

REQUIRED = ("t_ms", "src", "dst", "interface", "procedure", "message")


class Trace:
    def __init__(self):
        self.records = []

    def log(self, m):
        r = dict(seq=len(self.records), t_ms=round(m.t_sent, 4), t_arrive_ms=round(m.t_arrive, 4),
                 src=m.src, dst=m.dst, interface=m.interface, procedure=m.procedure, message=m.message)
        if m.ue is not None:
            r["ue"] = m.ue
        r.update({k: v for k, v in m.payload.items() if v is not None and not k.startswith("_")})
        self.records.append(r)

    def write(self, path, meta):
        with open(path, "w") as f:
            json.dump(dict(meta=meta, messages=self.records), f, indent=1)
