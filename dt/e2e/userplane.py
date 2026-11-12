"""
User-plane packets for the end-to-end layer.

Packets travel in per-epoch batches (one batch per UE per hop per scheduling epoch), so the trace
keeps one record per hop per epoch, while every packet keeps its own timestamp and a breakdown of
where its delay was spent. The batch rides in the message payload under the key `_batch` (keys that
start with '_' are not written to the trace).

Latency budget components [ms], in path order (server -> UE):
  n6         server -> UPF transport (N6)
  core       UPF processing (+ buffering while the session's DL FAR is still BUFF)
  backhaul   UPF -> CU-UP transport (N3, GTP-U)
  xn         source -> target CU-UP data forwarding during an Xn handover (Xn-U)
  ran_proc   CU-UP (PDCP/SDAP) + DU (RLC/MAC) processing
  midhaul    CU-UP -> DU transport (F1-U)
  du_queue   waiting in the DU's RLC queue for the scheduler (PRBs from B1/T3), incl. slot alignment
  fronthaul  DU -> RU transport + RU processing (must fit before the packet's slot)
  air        one slot on the air + HARQ retransmissions
"""
import numpy as np

COMPONENTS = ["n6", "core", "backhaul", "xn", "midhaul", "ran_proc", "du_queue", "fronthaul", "air"]
GROUP = {"n6": "data network (N6)", "core": "core processing (UPF)", "backhaul": "backhaul (N3)",
         "xn": "Xn-U forwarding (handover)",
         "midhaul": "midhaul (F1-U)", "ran_proc": "RAN processing (CU-UP, DU)",
         "du_queue": "air: scheduling / queueing", "fronthaul": "fronthaul (RU-DU)",
         "air": "air: TTI + HARQ"}


class Batch:
    """A set of packets of one UE. `t` is each packet's current time on its way to the UE."""

    def __init__(self, gen, size):
        self.gen = np.asarray(gen, float)
        self.t = self.gen.copy()
        self.size = np.full(len(self.gen), int(size))
        self.comp = {c: np.zeros(len(self.gen)) for c in COMPONENTS}

    def __len__(self):
        return len(self.gen)

    @property
    def bytes(self):
        return int(self.size.sum())

    def hop(self, link_ms, link_comp, proc_ms, proc_comp):
        self.t += link_ms + proc_ms
        self.comp[link_comp] += link_ms
        self.comp[proc_comp] += proc_ms
        return self

    def hold_until(self, t_release, comp):
        wait = np.maximum(0.0, t_release - self.t)
        self.t += wait
        self.comp[comp] += wait
        return self

    def take(self, idx):
        b = Batch.__new__(Batch)
        b.gen, b.t, b.size = self.gen[idx], self.t[idx], self.size[idx]
        b.comp = {c: v[idx] for c, v in self.comp.items()}
        return b

    @staticmethod
    def concat(batches):
        batches = [b for b in batches if len(b)]
        if not batches:
            return Batch([], 0)
        b = Batch.__new__(Batch)
        b.gen = np.concatenate([x.gen for x in batches])
        b.t = np.concatenate([x.t for x in batches])
        b.size = np.concatenate([x.size for x in batches])
        b.comp = {c: np.concatenate([x.comp[c] for x in batches]) for c in COMPONENTS}
        return b


class ConstantSource:
    """Full buffer: back-to-back packets at a fixed line rate far above any UE's air capacity, so the DU's
    RLC queue is never empty and the delivered rate is the scheduler's capacity (excess is tail-dropped)."""

    def __init__(self, rate_mbps, packet_bytes):
        self.gap_ms = packet_bytes * 8 / (rate_mbps * 1e6) * 1e3
        self.next_t = 0.0

    def until(self, t1):
        n = max(0, int(np.ceil((t1 - self.next_t) / self.gap_ms)))
        out = self.next_t + self.gap_ms * np.arange(n)
        self.next_t += n * self.gap_ms
        return out


def make_source(traffic, seed):
    """Traffic model from the config: 'poisson' (rate_mbps) or 'full_buffer' (full_buffer_line_rate_mbps)."""
    model, pkt = traffic.get("model", "poisson"), int(traffic["packet_bytes"])
    if model == "full_buffer":
        return ConstantSource(traffic.get("full_buffer_line_rate_mbps", 500), pkt)
    if model == "poisson":
        return PoissonSource(traffic["rate_mbps"], pkt, seed)
    raise ValueError(f"unknown e2e traffic model {model!r}")


class PoissonSource:
    """Poisson packet arrivals for one UE, from t = 0, with its own seed (identical for B1 and T3)."""

    def __init__(self, rate_mbps, packet_bytes, seed):
        self.gap_ms = packet_bytes * 8 / (rate_mbps * 1e6) * 1e3
        self.rng = np.random.default_rng(seed)
        self.next_t = self.rng.exponential(self.gap_ms)

    def until(self, t1):
        """All arrival times before t1 [ms] not returned yet."""
        out = []
        while self.next_t < t1:
            out.append(self.next_t)
            self.next_t += self.rng.exponential(self.gap_ms)
        return np.array(out)
