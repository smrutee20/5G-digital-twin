"""
Cell association + PRB scheduling strategies and a slot-level downlink simulator.

Every strategy makes its decisions on `ch_decide` (what the operator believes) and is
scored on `ch_eval` (what the radio channel really is). In Tasks 3-6 both are the twin;
in Task 7 decisions come from the twin and scoring from the 'physical' network.
"""
import numpy as np
from .kpi import (db, lin, effective_sinr, cqi_from_sinr_db, efficiency_from_cqi,
                  bits_per_prb, shannon_se)

STRATEGIES = {
    "B1 Fixed (nearest + equal PRBs)":      dict(assoc="nearest",  sched="fixed",   twin=False),
    "B2 Random (nearest + random PRBs)":    dict(assoc="nearest",  sched="random",  twin=False),
    "T1 Twin association":                  dict(assoc="max_rsrp", sched="fixed",   twin=True),
    "T2 Twin assoc + PF scheduling":        dict(assoc="twin_lb",  sched="pf",      twin=True),
    "T3 Twin full (PF + interference coord.)": dict(assoc="twin_lb", sched="pf_icic", twin=True),
}
SHORT = {k: k.split(" ")[0] for k in STRATEGIES}


# ----------------------------------------------------------------- received power
def rx_power(ch, cfg, active_rus=None):
    """Received power per PRB [U,R,K] in mW (equal power split across PRBs)."""
    c, r = cfg["carrier"], cfg["ran"]
    K = ch.H2.shape[-1]
    p_prb_dbm = r["tx_power_dbm"] - 10 * np.log10(c["num_prb"]) + r["bf_gain_db"]
    S = lin(p_prb_dbm) * ch.H2
    if active_rus is not None:
        S = S * active_rus[None, :, None]
    return S, lin(c["noise_prb_dbm"]), K


# ----------------------------------------------------------------- association
def assoc_nearest(ch, active):
    """Planning-style choice without any propagation knowledge: nearest site, sector by bearing."""
    sites = np.unique(ch.ru_site[active])
    site_xy = np.array([ch.ru_pos[ch.ru_site == s][0, :2] for s in sites])
    near = sites[np.argmin(np.linalg.norm(ch.pos[:, None, :2] - site_xy[None], axis=-1), axis=1)]
    out = np.empty(ch.U, int)
    for u in range(ch.U):
        cand = np.where((ch.ru_site == near[u]) & active)[0]
        bearing = np.rad2deg(np.arctan2(*(ch.pos[u, 1::-1] - ch.ru_pos[cand][:, 1::-1]).T))
        diff = np.abs((bearing - ch.ru_az[cand] + 180) % 360 - 180)
        out[u] = cand[np.argmin(diff)]
    return out


def assoc_max_rsrp(ch, active):
    pg = np.where(active[None], ch.pg_db, -np.inf)
    return np.argmax(pg, axis=1)


def assoc_twin_lb(ch, active, S, N, margin_db=8.0, rounds=4):
    """
    Twin-predicted load balancing: start from max-RSRP, then move UEs to another RU
    (within margin_db of their best) whenever it increases sum log(predicted rate),
    with predicted rate = spectral efficiency(wideband SINR) * K / cell load.
    """
    serv = assoc_max_rsrp(ch, active)
    Sw = S.mean(-1)                                               # [U,R]
    tot = Sw.sum(1, keepdims=True)
    se = shannon_se(Sw / (tot - Sw + N))                          # [U,R] if all RUs active
    pg = ch.pg_db
    for _ in range(rounds):
        moved = False
        for u in np.argsort(se[np.arange(ch.U), serv]):
            load = np.bincount(serv, minlength=len(active)).astype(float)
            cur = serv[u]
            cand = np.where(active & (pg[u] >= pg[u, cur] - margin_db))[0]
            best, best_gain = cur, 0.0
            for c in cand:
                if c == cur:
                    continue
                # utility change: u moves, others in cur gain, others in c lose
                g = np.log(se[u, c] / (load[c] + 1) + 1e-9) - np.log(se[u, cur] / load[cur] + 1e-9)
                g += (load[cur] - 1) * np.log(load[cur] / max(load[cur] - 1, 1)) * (load[cur] > 1)
                g -= load[c] * np.log((load[c] + 1) / max(load[c], 1)) * (load[c] > 0)
                if g > best_gain + 1e-6:
                    best, best_gain = c, g
            if best != cur:
                serv[u] = best
                moved = True
        if not moved:
            break
    return serv


# ----------------------------------------------------------------- simulator
def simulate(cfg, ch_eval, strategy, ch_decide=None, active_rus=None, num_slots=None,
             rng=None, tau=20.0, forced_serving=None):
    st = STRATEGIES[strategy] if isinstance(strategy, str) else strategy
    rng = rng or np.random.default_rng(0)
    ch_decide = ch_decide or ch_eval
    T = num_slots or cfg["experiments"]["num_slots"]
    R = len(ch_eval.ru_names)
    active = np.ones(R, bool) if active_rus is None else np.asarray(active_rus, bool)
    S, N, K = rx_power(ch_eval, cfg, active)
    Sd, _, _ = rx_power(ch_decide, cfg, active)
    U = ch_eval.U

    # ---- association (decided on the twin / on geometry)
    if forced_serving is not None:
        serv = np.asarray(forced_serving)
    elif st["assoc"] == "nearest":
        serv = assoc_nearest(ch_decide, active)
    elif st["assoc"] == "max_rsrp":
        serv = assoc_max_rsrp(ch_decide, active)
    else:
        serv = assoc_twin_lb(ch_decide, active, Sd, N)
    members = [np.where(serv == r)[0] for r in range(R)]
    loaded = np.array([len(m) > 0 for m in members])

    # padded member table for vectorised per-cell argmax
    nmax = max(1, max(len(m) for m in members))
    M = -np.ones((R, nmax), int)
    for r, m in enumerate(members):
        M[r, :len(m)] = m

    # twin-predicted per-PRB SINR of each UE at its serving RU (all loaded cells transmitting)
    Ld = Sd * loaded[None, :, None]
    sig_d = Sd[np.arange(U), serv]                                   # [U,K]
    sinr_est = sig_d / (Ld.sum(1) - Ld[np.arange(U), serv] + N)
    r_est = shannon_se(sinr_est)                                     # [U,K]

    # fixed equal contiguous blocks
    fixed = -np.ones((R, K), int)
    for r, m in enumerate(members):
        if len(m):
            fixed[r] = m[np.minimum((np.arange(K) * len(m)) // K, len(m) - 1)]

    rbar = np.maximum(r_est.mean(1) * K / np.maximum(np.bincount(serv, minlength=R)[serv], 1), 1e-3)
    bits = np.zeros(U); sinr_acc = [[] for _ in range(U)]; intf_acc = [[] for _ in range(U)]
    cqi_acc = [[] for _ in range(U)]; util = np.zeros(R); prbs = np.zeros(U)
    rows = np.arange(R)
    bits_prev = np.zeros(U)

    for t in range(T):
        # ---------------- scheduling decision
        if st["sched"] == "fixed":
            assign = fixed
        elif st["sched"] == "random":
            assign = -np.ones((R, K), int)
            for r, m in enumerate(members):
                if len(m):
                    assign[r] = rng.choice(m, size=K)
        else:
            assign = -np.ones((R, K), int)
            inslot = np.zeros(U)
            valid = M >= 0
            for k in rng.permutation(K):
                metric = np.where(valid, r_est[np.maximum(M, 0), k] /
                                  (rbar[np.maximum(M, 0)] + inslot[np.maximum(M, 0)] / tau), -1)
                pick = M[rows, np.argmax(metric, 1)]
                assign[:, k] = np.where(loaded, pick, -1)
                np.add.at(inslot, pick[loaded], r_est[pick[loaded], k])
            if st["sched"] == "pf_icic":
                assign = coordinate_muting(assign, Sd, N, 1.0 / rbar)

        # ---------------- evaluate on the real channel
        act = assign >= 0                                            # [R,K]
        I_tot = np.einsum("urk,rk->uk", S, act)                      # total received per UE/PRB
        for r in np.where(act.any(1))[0]:
            ks = np.where(act[r])[0]
            us = assign[r, ks]
            sig = S[us, r, ks]
            intf = I_tot[us, ks] - sig + N
            sinr = sig / intf
            for u in np.unique(us):
                sel = us == u
                se = effective_sinr(sinr[sel])
                # link adaptation from CQI feedback (real channel), 10% BLER target
                cqi = cqi_from_sinr_db(db(se))
                bits[u] += bits_per_prb(efficiency_from_cqi(cqi), cfg) * sel.sum()
                sinr_acc[u].append(db(se)); cqi_acc[u].append(cqi)
                intf_acc[u].append(db(np.mean(intf[sel] - N) + 1e-30))
                prbs[u] += sel.sum()
        util += act.mean(1)
        # PF average-rate update with the achieved rate, in the same unit as r_est
        # (spectral efficiency summed over PRBs in the slot)
        rate_t = (bits - bits_prev) / bits_per_prb(1.0, cfg)
        bits_prev = bits.copy()
        rbar = (1 - 1 / tau) * rbar + (1 / tau) * rate_t

    slot = cfg["carrier"]["slot_s"]
    # wideband 'geometry' SINR at the serving RU with every loaded RU transmitting (true channel)
    Le = S.mean(-1) * loaded[None]
    geo = S.mean(-1)[np.arange(U), serv] / (Le.sum(1) - Le[np.arange(U), serv] + N)
    return dict(
        serving=serv, loaded=loaded, thr_mbps=bits / (T * slot) / 1e6,
        sinr_db=np.array([np.mean(s) if s else -20.0 for s in sinr_acc]),
        interf_dbm=np.array([np.mean(s) if s else np.nan for s in intf_acc]),
        cqi=np.array([np.mean(s) if s else 0.0 for s in cqi_acc]),
        prb_util=util / T, prbs_per_slot=prbs / T, geo_sinr_db=db(geo),
        bw_hz=K * cfg["carrier"]["prb_bw_hz"], last_assign=assign)


def coordinate_muting(assign, Sd, N, w, iters=3):
    """
    Twin-assisted interference coordination: on each PRB, greedily switch off the cell
    whose silence most increases the PF-weighted sum rate predicted by the twin.
    """
    R, K = assign.shape
    act = assign >= 0
    u = np.maximum(assign, 0)
    G = Sd[u[:, None, :], np.arange(R)[None, :, None], np.arange(K)[None, None, :]]   # [r,j,k]
    own = G[np.arange(R), np.arange(R)]                                                # [R,K]
    wk = w[u]

    def util(a):
        I = np.einsum("rjk,jk->rk", G, a) - own * a
        return (a * wk * shannon_se(own / (I + N))).sum(0)

    base = util(act)
    for _ in range(iters):
        gains = np.full((R, K), -np.inf)
        for c in range(R):
            if not act[c].any():
                continue
            a2 = act.copy(); a2[c] = False
            gains[c] = util(a2) - base
        best = np.argmax(gains, 0)
        g = gains[best, np.arange(K)]
        do = g > 1e-9 * np.maximum(base, 1e-12)
        if not do.any():
            break
        act[best[do], np.where(do)[0]] = False
        base = util(act)
    return np.where(act, assign, -1)
