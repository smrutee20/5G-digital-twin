"""
Who serves each UE, and which PRBs it gets: the two baselines (B1, B2) and the twin strategy.

Each UE needs PRBS_PER_UE PRBs, so a sector uses only the PRBs its UEs need (partial load), and which PRBs it
picks decides whom it interferes with. B1 gives every UE a fixed block counted from PRB 0 in every sector, and
B2 picks the PRBs at random. The Twin estimates from the ray tracing how strongly each pair of sectors
interferes, and gives strongly interfering sectors different PRBs.

A PRB plan is an array owner[sector, prb]: the UE that uses that PRB in that sector, or -1 if the sector leaves
the PRB empty (does not transmit on it). evaluate() turns a plan into SINR and throughput per UE.
"""
import numpy as np

import config
from twin.radio import noise_mw, bits_per_prb, to_db, SLOT_S
from twin.scene import NUM_PRB

PRBS_PER_UE = 12                                # each UE needs 12 PRBs (4.3 MHz); a sector has 273


# ------------------------------------------------------------------ who serves each UE
def nearest_sector(ue_xy, active):
    """Without the twin (planning by map only): the nearest site, then its sector that points at the UE."""
    sectors = config.sectors()
    serving = np.empty(len(ue_xy), int)
    for u, (x, y) in enumerate(ue_xy):
        on = [i for i, s in enumerate(sectors) if active[i]]
        site = min({sectors[i]["site"] for i in on},
                   key=lambda s: np.hypot(x - config.SITES[s]["xy"][0], y - config.SITES[s]["xy"][1]))
        sx, sy = config.SITES[site]["xy"]
        bearing = np.degrees(np.arctan2(y - sy, x - sx))                     # direction site -> UE
        mine = [i for i in on if sectors[i]["site"] == site]
        off_axis = [abs((bearing - sectors[i]["az"] + 180) % 360 - 180) for i in mine]
        serving[u] = mine[int(np.argmin(off_axis))]
    return serving


def strongest_sector(rx_mw, active):
    """With the twin: the sector whose ray-traced signal is strongest at the UE."""
    return np.argmax(np.where(active, rx_mw, 0), axis=1)


# ------------------------------------------------------------------ which PRBs each UE gets
def prbs_needed(n_ues):
    """PRBs a sector uses for n UEs: 12 each, but never more than the 273 it has."""
    return min(n_ues * PRBS_PER_UE, NUM_PRB)


def share(row, prbs, ues):
    """Give the PRBs listed in prbs to the UEs in ues, in equal blocks."""
    row[prbs] = ues[np.arange(len(prbs)) * len(ues) // len(prbs)]


def fixed_prbs(serving, n_sectors):
    """B1: every sector counts from PRB 0, so UE 1 of each sector gets PRBs 0-11, UE 2 gets 12-23, ..."""
    owner = -np.ones((n_sectors, NUM_PRB), int)
    for s in range(n_sectors):
        ues = np.where(serving == s)[0]
        if len(ues):
            share(owner[s], np.arange(prbs_needed(len(ues))), ues)
    return owner


def random_prbs(serving, n_sectors, rng):
    """B2: every sector picks the PRBs it needs at random."""
    owner = -np.ones((n_sectors, NUM_PRB), int)
    for s in range(n_sectors):
        ues = np.where(serving == s)[0]
        if len(ues):
            share(owner[s], np.sort(rng.permutation(NUM_PRB)[:prbs_needed(len(ues))]), ues)
    return owner


def coordinated_prbs(serving, rx_mw, n_sectors):
    """
    Twin: strongly interfering sectors get different PRBs.
    1. From the ray tracing, estimate how much sector j interferes with sector i: for each UE of sector i, the
       power from j divided by the power from i, added up. Add both directions, i -> j and j -> i.
    2. The busiest sector picks its PRBs first; every next sector picks the PRBs where the sectors that
       interfere with it most are not transmitting.
    """
    coupling = np.zeros((n_sectors, n_sectors))
    for u, i in enumerate(serving):
        coupling[i] += rx_mw[u] / rx_mw[u, i]                     # interference from every sector, relative to i
    np.fill_diagonal(coupling, 0)
    coupling = coupling + coupling.T                               # both directions count

    owner = -np.ones((n_sectors, NUM_PRB), int)
    used = np.zeros((n_sectors, NUM_PRB))                          # 1 where a sector already transmits
    for s in sorted(range(n_sectors), key=lambda s: -np.sum(serving == s)):
        ues = np.where(serving == s)[0]
        if not len(ues):
            continue
        cost = coupling[s] @ used                                  # per PRB: interference with sectors already there
        chosen = np.sort(np.argsort(cost, kind="stable")[:prbs_needed(len(ues))])   # the quietest PRBs
        share(owner[s], chosen, ues)
        used[s, chosen] = 1
    return owner


# ------------------------------------------------------------------ the result of a plan
def evaluate(owner, rx_mw, serving):
    """SINR, interference and throughput of every UE for a PRB plan (rx_mw = power per PRB, [UE, sector])."""
    on = owner >= 0                                                           # [sector, PRB]: who transmits where
    total = rx_mw @ on                                                        # [UE, PRB]: all power received
    U = len(serving)
    sinr_db, interference_dbm, throughput = np.full(U, np.nan), np.full(U, np.nan), np.zeros(U)
    for u in range(U):
        prbs = np.where(owner[serving[u]] == u)[0]                           # this UE's PRBs
        if not len(prbs):
            continue                                                          # no PRB left: 0 Mbps
        signal = rx_mw[u, serving[u]]
        interference = total[u, prbs] - signal
        sinr = to_db(signal / (interference + noise_mw()))
        throughput[u] = bits_per_prb(sinr).sum() / SLOT_S / 1e6
        sinr_db[u] = to_db(np.mean(10 ** (sinr / 10)))
        interference_dbm[u] = to_db(np.mean(interference))
    loaded = np.isin(np.arange(len(owner)), serving)                         # sectors that serve someone
    return dict(serving=serving, sinr_db=sinr_db, interference_dbm=interference_dbm, throughput_mbps=throughput,
                prb_utilisation=on[loaded].mean(), prb_plan=owner)


def run(strategy, rx_mw, ue_xy, active=None, rng=None, serving=None):
    """
    One strategy, start to finish: B1, B2 or Twin. Pass serving to fix who serves each UE (task 5 does this for
    the walking UE, whose serving sector follows the A3 handover rule).
    """
    active = np.ones(rx_mw.shape[1], bool) if active is None else np.asarray(active)
    S = rx_mw.shape[1]
    if serving is None:
        serving = strongest_sector(rx_mw, active) if strategy == "Twin" else nearest_sector(ue_xy, active)
    if strategy == "B1":                                                     # nearest site + fixed PRBs
        owner = fixed_prbs(serving, S)
    elif strategy == "B2":                                                   # nearest site + random PRBs
        owner = random_prbs(serving, S, rng or np.random.default_rng(0))
    else:                                                                    # Twin: strongest + coordinated PRBs
        owner = coordinated_prbs(serving, rx_mw, S)
    owner[~active] = -1                                                      # a switched-off sector sends nothing
    return evaluate(owner, rx_mw, serving)
