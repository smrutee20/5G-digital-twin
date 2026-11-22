"""
Vegetation loss for ray-traced paths ("option C"): trees are NOT objects in the Sionna scene (refraction stays off, so a
tree would block every ray like a wall). Instead, after tracing, every path is followed segment by segment
(transmitter -> interaction points -> receiver), the length of each segment inside tree crowns is added up, and the
path's power is reduced by

    loss_dB = min(VEG_DB_PER_M * length_in_crowns_m, VEG_CAP_DB)

*** TO BE CALIBRATED ***
VEG_DB_PER_M and VEG_CAP_DB are placeholder starting values, NOT fitted to IITGN and not yet checked against
ITU-R P.833 (attenuation in vegetation) for in-leaf trees at 3.5 GHz: do that first, then calibrate on site. The crown model (an ellipsoid from CROWN_BASE_M up to the
tree height, with the crown diameter from trees.csv: 6 m and 8 m by default) is an assumption too. Calibrate all of
them against measurements (e.g. an RSRP walk under and beside the hostel trees) before trusting absolute numbers.

Crowns: trees.csv in the scene folder (id, x_m, y_m, crown_d_m, height_m, source), twin local metres.
"""
import csv
from pathlib import Path

import numpy as np

VEG_DB_PER_M = 1.0              # TO BE CALIBRATED: specific attenuation inside a crown [dB/m]
VEG_CAP_DB = 20.0               # TO BE CALIBRATED: maximum vegetation loss on one path [dB]
CROWN_BASE_M = 2.5              # TO BE CALIBRATED: height of the crown's bottom above ground (trunk below)


def load_trees(scene_xml):
    """Tree crowns of a scene: None if the scene folder has no trees.csv (v1)."""
    f = Path(scene_xml).parent / "trees.csv"
    if not f.exists():
        return None
    rows = list(csv.DictReader(open(f)))
    xy = np.array([[float(r["x_m"]), float(r["y_m"])] for r in rows])
    d = np.array([float(r["crown_d_m"]) for r in rows]); h = np.array([float(r["height_m"]) for r in rows])
    base = np.minimum(CROWN_BASE_M, 0.5 * h)
    return dict(xy=xy, r=d / 2, zc=(base + h) / 2, c=(h - base) / 2, n=len(rows))


def length_in_crowns(p0, p1, trees, chunk=20000):
    """Total length [m] of each segment p0[i] -> p1[i] (arrays [N, 3]) that lies inside any crown ellipsoid."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    out = np.zeros(len(p0))
    if trees is None or len(p0) == 0:
        return out
    C = np.c_[trees["xy"], trees["zc"]]                                     # [T, 3]
    S = np.c_[trees["r"], trees["r"], trees["c"]]                           # semi-axes
    for s in range(0, len(p0), chunk):
        a, b = p0[s:s + chunk], p1[s:s + chunk]
        seg_len = np.linalg.norm(b - a, axis=1)
        # quick 2D rejection: the segment's bounding box must come within a crown radius of the tree
        lo, hi = np.minimum(a, b)[:, None, :2], np.maximum(a, b)[:, None, :2]
        near = np.all((C[None, :, :2] > lo - S[None, :, :2]) & (C[None, :, :2] < hi + S[None, :, :2]), axis=2)
        si, ti = np.nonzero(near)
        if len(si) == 0:
            continue
        q0 = (a[si] - C[ti]) / S[ti]; q1 = (b[si] - C[ti]) / S[ti]              # unit-sphere frame
        d = q1 - q0
        A = (d * d).sum(1); B = 2 * (q0 * d).sum(1); Cq = (q0 * q0).sum(1) - 1
        disc = B * B - 4 * A * Cq
        ok = (disc > 0) & (A > 0)
        sq = np.sqrt(np.where(ok, disc, 0))
        t0 = np.clip((-B - sq) / np.where(ok, 2 * A, 1), 0, 1); t1 = np.clip((-B + sq) / np.where(ok, 2 * A, 1), 0, 1)
        frac = np.where(ok, np.maximum(t1 - t0, 0), 0)
        np.add.at(out, s + si, frac * seg_len[si])
    return out


def loss_db(length_m):
    return np.minimum(VEG_DB_PER_M * np.asarray(length_m), VEG_CAP_DB)


def path_loss_db(paths, trees):
    """Vegetation loss [dB] of every path, shape [num_rx, num_tx, num_paths] (synthetic arrays)."""
    from sionna.rt.constants import InteractionType
    V = np.array(paths.vertices)                                            # [depth, rx, tx, P, 3]
    I = np.array(paths.interactions)                                        # [depth, rx, tx, P]
    D, R, T, P = I.shape
    src, tgt = np.array(paths.sources), np.array(paths.targets)             # Point3f -> [3, n]
    src = src.T if src.shape[0] == 3 and src.shape[-1] == T else src.reshape(T, 3)
    tgt = tgt.T if tgt.shape[0] == 3 and tgt.shape[-1] == R else tgt.reshape(R, 3)
    rx_pos = np.broadcast_to(tgt[:, None, None, :], (R, T, P, 3))
    total = np.zeros((R, T, P))
    prev = np.broadcast_to(src[None, :, None, :], (R, T, P, 3)).copy()      # each path starts at its transmitter
    done = np.zeros((R, T, P), bool)

    def add(mask, a, b):
        idx = np.nonzero(mask)
        if len(idx[0]):
            total[idx] += length_in_crowns(a[idx], b[idx], trees)

    for k in range(D):
        here = (I[k] != int(InteractionType.NONE)) & ~done                  # the path has a k-th interaction point
        ends = (I[k] == int(InteractionType.NONE)) & ~done                  # the path has no more: last leg to the UE
        add(here, prev, V[k])
        add(ends, prev, rx_pos)
        prev = np.where(here[..., None], V[k], prev)
        done |= ends
    add(~done, prev, rx_pos)                                                # paths that used every interaction depth
    return loss_db(total)


def cfr(paths, frequencies, trees):
    """
    Channel frequency response like paths.cfr(..., out_type="numpy") ([rx, rx_ant, tx, tx_ant, 1, f]), but with the
    vegetation loss applied to every path's amplitude. Same steps as Sionna's Paths.cir + cfr (delays relative to
    each link's first path, carrier phase, then the band offsets); checked equal to paths.cfr when there are no trees.
    """
    a_re, a_im = (np.array(x) for x in paths.a)                             # [rx, rx_ant, tx, tx_ant, P]
    a = a_re + 1j * a_im
    tau = np.array(paths.tau)                                               # [rx, tx, P]
    valid = np.array(paths.valid)                                           # [rx, tx, P] (synthetic)
    if valid.ndim == 5:
        valid = valid[:, 0, :, 0, :]
    att = 10 ** (-path_loss_db(paths, trees) / 20) * valid                  # amplitude factor
    t = np.where(valid, tau, np.nan)
    t0 = np.nanmin(np.where(np.isfinite(t), t, np.inf), axis=-1, keepdims=True)
    t0 = np.where(np.isfinite(t0), t0, 0)
    rel = np.where(valid, tau - t0, 0)
    # baseband: each path also turns by the carrier phase -2 pi f_c tau (as Sionna's Paths.cir does); with the
    # band offsets f this is -2 pi (f_c + f) tau, delays relative to the link's first path
    fc = float(np.array(paths._frequency).ravel()[0])
    f = fc + np.asarray(frequencies, float)
    E = np.exp(-2j * np.pi * rel[..., None] * f) * att[..., None]           # [rx, tx, P, F]
    H = np.einsum("rytap,rtpf->rytaf", a, E, optimize=True)                 # [rx, rx_ant, tx, tx_ant, F]
    return H[:, :, :, :, None, :]
