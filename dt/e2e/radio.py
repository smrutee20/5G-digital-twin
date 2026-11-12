"""
Read-only adapter between the end-to-end layer and the existing radio twin.

Nothing in dt/alloc.py, dt/channel.py or dt/twin.py is changed: the per-PRB channels come from
data/<tag>/twin_pool.npz (static UEs, e03's drop) and data/<tag>/mobility_traces.npz (the three e05 walks,
2 m steps), and the DU scheduler is an existing strategy (T3 by default, or the B1 baseline) called
through dt.alloc.simulate() once per scheduling epoch. Each UE's air-interface capacity comes from its
per-PRB SINR -> CQI -> bits on the PRBs the strategy gave it.

T3 coordinates PRB muting across all RUs, i.e. across the 3 gNBs. In an O-RAN deployment that joint
decision would come from the near-RT RIC over E2; the RIC and E2 are not modelled here.
"""
import numpy as np

from dt.channel import ChannelSet
from dt.alloc import simulate, rx_power, assoc_twin_lb, assoc_nearest, assoc_max_rsrp, STRATEGIES

FULL = {k.split()[0]: k for k in STRATEGIES}          # "B1" -> "B1 Fixed (nearest + equal PRBs)", ...
T3 = FULL["T3"]


class RadioLayer:
    def __init__(self, cfg, data_dir, drop, num_ues, strategy="T3", movers=()):
        self.cfg = cfg
        self.short, self.strategy = strategy, FULL[strategy]
        pool = ChannelSet.load(data_dir / "twin_pool.npz")
        uniform = np.where(~np.array(pool.meta["is_hotspot"]))[0]
        # same UE drop as experiments/e03_compare_strategies.py, drop `drop`
        self.pool_idx = np.random.default_rng(1000 + drop).choice(uniform, num_ues, replace=False)
        self.ch = pool.subset(self.pool_idx)
        self.movers = list(movers)                        # walk ids 1..3 (e05 trajectories)
        if self.movers:
            self.mob = ChannelSet.load(data_dir / "mobility_traces.npz")
            self.steps = self.mob.U // 3                      # 66 points per walk, walks stored one after another
            self.step = {w: 0 for w in self.movers}
        self.n_static = num_ues
        self.ru_names = list(self.ch.ru_names)
        self.ru_site = np.array(self.ch.ru_site)
        self.slot_ms = cfg["carrier"]["slot_s"] * 1e3
        c, r = cfg["carrier"], cfg["ran"]
        self.p_re = r["tx_power_dbm"] - 10 * np.log10(c["num_prb"] * 12) + r["bf_gain_db"]
        ch = self.channel()
        R = len(self.ru_names)
        S, N, _ = rx_power(ch, cfg)
        active = np.ones(R, bool)
        # cell each UE camps on = the strategy's own association (same as inside simulate())
        assoc = STRATEGIES[self.strategy]["assoc"]
        self.serving = (assoc_nearest(ch, active) if assoc == "nearest" else
                        assoc_max_rsrp(ch, active) if assoc == "max_rsrp" else
                        assoc_twin_lb(ch, active, S, N))
        self._cache = {}

    def channel(self):
        """Channels of all UEs now: static UEs + each walker at its current step."""
        if not self.movers:
            return self.ch
        rows = [(w - 1) * self.steps + self.step[w] for w in self.movers]
        return ChannelSet.concat([self.ch, self.mob.subset(rows)])

    def rsrp_dbm(self, u):
        """SS-RSRP [dBm] of UE row u from every RU (per resource element)."""
        return self.p_re + self.channel().pg_db[u]

    def schedule(self, active, num_slots, rng):
        """Static UEs, all RUs on, the strategy's own association: used to check against e03."""
        active = np.asarray(active)
        res = simulate(self.cfg, self.ch.subset(active), self.strategy, num_slots=num_slots, rng=rng,
                       forced_serving=self.serving[active])
        return res["thr_mbps"] * 1e6 * num_slots * self.slot_ms * 1e-3, res

    def schedule_now(self, rows, serving, active_rus, num_slots, rng):
        """Run the strategy for UE rows `rows` served by RU indices `serving` with only `active_rus` on.
        The result depends only on the radio state (positions, serving cells, RUs on), so it is cached."""
        key = (tuple(rows), tuple(serving), tuple(active_rus),
               tuple(self.step[w] for w in self.movers) if self.movers else ())
        if key not in self._cache:
            sub = self.channel().subset(np.asarray(rows))
            res = simulate(self.cfg, sub, self.strategy, num_slots=num_slots, rng=rng,
                           active_rus=np.asarray(active_rus, bool), forced_serving=np.asarray(serving))
            self._cache[key] = res
        res = self._cache[key]
        return res["thr_mbps"] * 1e6 * num_slots * self.slot_ms * 1e-3, res
