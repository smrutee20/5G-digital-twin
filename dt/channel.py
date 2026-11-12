"""
Channel database produced by the twin, plus the 3GPP TR 38.901 helpers used to
(a) fill links the ray tracer could not resolve and (b) build a non-site-specific
statistical model to compare the twin against.
"""
from dataclasses import dataclass, field
import numpy as np
import pandas as pd


# ----------------------------------------------------------------- 3GPP TR 38.901 helpers
def sector_gain_db(ru_pos, ru_az_deg, ru_tilt_deg, ue_pos):
    """TR 38.901 Table 7.3-1 element pattern (8 dBi max) seen from each RU towards each UE."""
    d = ue_pos[:, None, :] - ru_pos[None, :, :]                        # [U,R,3]
    a, b = np.deg2rad(ru_az_deg)[None, :], np.deg2rad(ru_tilt_deg)[None, :]
    # rotate into antenna frame: Ry(b)^T Rz(a)^T d
    x1 = np.cos(a) * d[..., 0] + np.sin(a) * d[..., 1]
    y1 = -np.sin(a) * d[..., 0] + np.cos(a) * d[..., 1]
    z1 = d[..., 2]
    x2 = np.cos(b) * x1 - np.sin(b) * z1
    z2 = np.sin(b) * x1 + np.cos(b) * z1
    r = np.linalg.norm(d, axis=-1)
    theta = np.rad2deg(np.arccos(np.clip(z2 / r, -1, 1)))
    phi = np.rad2deg(np.arctan2(y1, x2))
    av = -np.minimum(12 * ((theta - 90) / 65) ** 2, 30)
    ah = -np.minimum(12 * (phi / 65) ** 2, 30)
    return 8.0 - np.minimum(-(av + ah), 30)


def uma_pathloss_db(d3d, d2d, fc_hz, h_bs=25.0, h_ut=1.5, los=None):
    """TR 38.901 Table 7.4.1-1 UMa path loss. los=None -> LOS-probability-weighted average."""
    fc = fc_hz / 1e9
    d3d = np.maximum(d3d, 10.0)
    pl_los = 28.0 + 22 * np.log10(d3d) + 20 * np.log10(fc)
    pl_nlos = np.maximum(pl_los, 13.54 + 39.08 * np.log10(d3d) + 20 * np.log10(fc) - 0.6 * (h_ut - 1.5))
    if los is True:
        return pl_los
    if los is False:
        return pl_nlos
    p_los = np.where(d2d <= 18, 1.0, 18 / d2d + np.exp(-d2d / 63) * (1 - 18 / d2d))
    lin = p_los * 10 ** (-pl_los / 10) + (1 - p_los) * 10 ** (-pl_nlos / 10)
    return -10 * np.log10(lin)


# ----------------------------------------------------------------- channel database
@dataclass
class ChannelSet:
    pos: np.ndarray            # [U,3] UE positions
    H2: np.ndarray             # [U,R,K] channel power gain per PRB (linear, antenna gains included)
    los: np.ndarray            # [U,R] geometric line of sight
    ru_pos: np.ndarray
    ru_az: np.ndarray
    ru_tilt: np.ndarray
    ru_site: np.ndarray
    ru_names: list
    delay_spread_ns: np.ndarray = None
    num_paths: np.ndarray = None
    rt_found: np.ndarray = None   # [U,R] ray tracer found at least one path
    profile: str = "twin"
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.rt_found is None:
            self.rt_found = self.H2.mean(-1) > 1e-25

    # ---- derived quantities
    @property
    def U(self):
        return self.H2.shape[0]

    @property
    def pg_db(self):
        return 10 * np.log10(self.H2.mean(-1) + 1e-30)

    def dist(self, three_d=True):
        d = self.pos[:, None, :] - self.ru_pos[None]
        return np.linalg.norm(d if three_d else d[..., :2], axis=-1)

    def subset(self, idx, label=None):
        idx = np.asarray(idx)
        return ChannelSet(self.pos[idx], self.H2[idx], self.los[idx], self.ru_pos, self.ru_az,
                          self.ru_tilt, self.ru_site, self.ru_names,
                          None if self.delay_spread_ns is None else self.delay_spread_ns[idx],
                          None if self.num_paths is None else self.num_paths[idx],
                          self.rt_found[idx], label or self.profile, dict(self.meta))

    def with_prbs(self, k):
        c = self.subset(np.arange(self.U))
        c.H2 = self.H2[:, :, :k]
        return c

    @staticmethod
    def concat(sets, label=None):
        a = sets[0]
        cat = lambda f: None if getattr(a, f) is None else np.concatenate([getattr(s, f) for s in sets])
        return ChannelSet(cat("pos"), cat("H2"), cat("los"), a.ru_pos, a.ru_az, a.ru_tilt, a.ru_site,
                          a.ru_names, cat("delay_spread_ns"), cat("num_paths"), cat("rt_found"),
                          label or a.profile, dict(a.meta))

    # ---- hybrid fill for links the ray tracer missed or resolved implausibly weakly
    def fill_unresolved(self, fc_hz, calib=None, weak_db=18.0, shadow_db=6.0, seed=0):
        """
        Depth-limited ray tracing misses links (multiple diffractions over roofs) or resolves them
        through a single weak multi-bounce path. A link is filled when
          * no path was traced, or
          * its traced gain is more than `weak_db` below the TR 38.901 UMa-NLOS value (+ sector
            pattern) at that distance. Default 18 dB = 3 x the 6 dB UMa-NLOS shadow-fading sigma
            (TR 38.901 Table 7.4.1-1): genuine shadowing that deep has probability ~0.1 %, so such
            links are treated as tracing artefacts. weak_db=None keeps every traced link.
        Filled links get 38.901 UMa-NLOS + sector pattern + a calibration offset (median residual of
        the resolved, non-weak NLOS links, i.e. as strong as a typical resolved NLOS link) + log-normal
        shadowing (std `shadow_db`). The fixed `seed` gives the same draw per link index, so the twin
        at true and at GPS positions agree. Filled links are marked rt_found = False.
        """
        d3, d2 = self.dist(True), self.dist(False)
        model_db = -uma_pathloss_db(d3, d2, fc_hz, los=False) + \
            sector_gain_db(self.ru_pos, self.ru_az, self.ru_tilt, self.pos)
        resid = self.pg_db - model_db
        missing = ~self.rt_found
        weak = self.rt_found & (resid < -weak_db) if weak_db is not None else np.zeros_like(missing)
        fill = missing | weak
        if calib is None:
            ok = ~fill & ~self.los
            calib = float(np.median(resid[ok]))
        shadow = np.random.default_rng(seed).normal(0.0, shadow_db, size=fill.shape)
        floor = 10 ** ((model_db + calib + shadow) / 10)
        self.H2 = np.where(fill[..., None], floor[..., None], self.H2).astype(np.float32)
        self.rt_found = self.rt_found & ~fill
        self.meta.update(fill_calib_db=calib, filled_frac=float(fill.mean()),
                         filled_missing_frac=float(missing.mean()), filled_weak_frac=float(weak.mean()),
                         fill_weak_db=weak_db, fill_shadow_db=shadow_db)
        return calib

    # ---- persistence
    def save(self, path):
        np.savez_compressed(path, pos=self.pos, H2=self.H2.astype(np.float32),
                            los=self.los, ru_pos=self.ru_pos, ru_az=self.ru_az, ru_tilt=self.ru_tilt,
                            ru_site=self.ru_site, ru_names=np.array(self.ru_names),
                            delay_spread_ns=self.delay_spread_ns, num_paths=self.num_paths,
                            rt_found=self.rt_found, profile=self.profile,
                            meta=np.array([repr(self.meta)]))

    @staticmethod
    def load(path):
        z = np.load(path, allow_pickle=True)
        c = ChannelSet(z["pos"], z["H2"], z["los"], z["ru_pos"], z["ru_az"], z["ru_tilt"], z["ru_site"],
                       list(z["ru_names"]), z["delay_spread_ns"], z["num_paths"], z["rt_found"],
                       str(z["profile"]))
        c.meta = eval(str(z["meta"][0]), {"nan": np.nan})
        return c

    def to_table(self, cfg):
        """Long table: one row per (UE, RU) link -- the 'channel database' deliverable."""
        c, r = cfg["carrier"], cfg["ran"]
        p_re = r["tx_power_dbm"] - 10 * np.log10(c["num_prb"] * 12)
        U, R = self.H2.shape[:2]
        uu, rr = np.meshgrid(np.arange(U), np.arange(R), indexing="ij")
        return pd.DataFrame(dict(
            ue_id=uu.ravel(), ru=np.array(self.ru_names)[rr.ravel()],
            x=self.pos[uu.ravel(), 0].round(2), y=self.pos[uu.ravel(), 1].round(2),
            z=self.pos[uu.ravel(), 2], dist_3d_m=self.dist().ravel().round(1),
            los=self.los.ravel(), rt_path_found=self.rt_found.ravel(),
            pathgain_db=self.pg_db.ravel().round(2),
            rsrp_dbm=(p_re + r["bf_gain_db"] + self.pg_db).ravel().round(2),
            delay_spread_ns=np.round(self.delay_spread_ns.ravel(), 1),
            num_paths=self.num_paths.ravel()))


# ----------------------------------------------------------------- non-twin and 'physical' channels
def statistical_channel(ref: ChannelSet, fc_hz, label="38.901-statistical"):
    """What a planning tool without a twin would predict: UMa path loss + sector pattern, flat in frequency."""
    g = -uma_pathloss_db(ref.dist(True), ref.dist(False), fc_hz) + \
        sector_gain_db(ref.ru_pos, ref.ru_az, ref.ru_tilt, ref.pos)
    c = ref.subset(np.arange(ref.U), label)
    c.H2 = np.repeat((10 ** (g / 10))[..., None], ref.H2.shape[-1], -1).astype(np.float32)
    return c


def calibrate_with_measurements(twin: ChannelSet, phys: ChannelSet, rng, n_report=8,
                                sigma_db=2.0, min_pg_db=-150.0, label="twin+MR-calibrated"):
    """
    Closed-loop synchronisation of the twin with the physical network (TR 28.915 'data'):
    each UE reports SS-RSRP of its n_report strongest cells (TS 38.331 measurement report,
    1 dB resolution, ~2 dB measurement error). The twin keeps its own frequency-selective
    shape per link but rescales the wideband level to the reported value; links that are
    not reported are capped at the weakest reported level.
    """
    meas = phys.pg_db + rng.normal(0, sigma_db, phys.pg_db.shape)
    meas = np.round(meas)
    order = np.argsort(-phys.pg_db, axis=1)
    rep = np.zeros_like(phys.los)
    np.put_along_axis(rep, order[:, :n_report], True, axis=1)
    rep &= phys.pg_db > min_pg_db
    out = twin.subset(np.arange(twin.U), label)
    wb = twin.H2.mean(-1)
    scale = np.where(rep, 10 ** (meas / 10) / np.maximum(wb, 1e-30), 1.0)
    weakest = np.where(rep, meas, np.inf).min(1, keepdims=True)
    cap = np.where(~rep & (twin.pg_db > weakest), 10 ** (weakest / 10) / np.maximum(wb, 1e-30), 1.0)
    out.H2 = (twin.H2 * (scale * cap)[..., None]).astype(np.float32)
    out.meta.update(reported_links=float(rep.mean()))
    return out


def apply_impairments(ch: ChannelSet, cfg, rng):
    """Effects present in the physical network but absent from the twin."""
    imp = cfg["physical_impairments"]
    U, R, K = ch.H2.shape
    shadow = 10 ** (rng.normal(0, imp["shadowing_std_db"], size=(U, R, 1)) / 10)
    # frequency-correlated Rayleigh fading on NLOS links (coherence ~ 10 PRBs)
    g = (rng.normal(size=(U, R, K + 20)) + 1j * rng.normal(size=(U, R, K + 20))) / np.sqrt(2)
    ker = np.ones(10) / np.sqrt(10)
    g = np.apply_along_axis(lambda v: np.convolve(v, ker, mode="same"), -1, g)[..., 10:K + 10]
    fade = np.where(ch.los[..., None], 1.0, np.abs(g) ** 2)
    out = ch.subset(np.arange(U), ch.profile + "+impairments")
    out.H2 = (ch.H2 * shadow * fade).astype(np.float32)
    return out
