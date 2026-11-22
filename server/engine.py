"""
The Configure engine: the twin's Sionna RT scene with user-chosen antenna settings and UE positions.

  ues()       per UE and sector: best-beam RSRP, the beam, the beam-averaged power (for interference), line of sight;
              then the serving sector (strongest RSRP) and SINR
  coverage()  Sionna's radio-map solver on a 5 m grid at UE height: best-server RSRP of every outdoor cell

Both use the same scene, ray settings and beam codebook as each other, and with the default settings the same
numbers as twin/scene.py and twin/radio.py (1x1 tr38901 V, 46 dBm, 8 deg tilt; UE 1x1 iso, 1.5 m, NF 9 dB).

Sionna RT 2.2.0 notes (checked against the installed version):
  * scene.tx_array is one array for every transmitter, so sectors with different antenna settings are traced in
    separate passes (one pass per distinct setting).
  * RadioMapSolver never uses scene.rx_array: the coverage map always assumes one isotropic UE antenna.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config                                   # noqa: E402
import twin.scene as sc                         # noqa: E402
from twin import vegetation                     # noqa: E402
from server import beams                        # noqa: E402

INTERACTIVE_RAYS = 200_000                      # interactive runs; the study used 1 000 000 (sc.RAYS_PER_SECTOR)
GRID_M = 5.0                                    # coverage map cell size
RE_PER_CARRIER = sc.NUM_PRB * 12                # RSRP = power of one of the 273 x 12 resource elements
PRB_HZ = 12 * sc.SCS_HZ
NO_PATH_DB = -300.0

GNB_DEFAULT = dict(array="1x1", pattern=sc.SECTOR_ANTENNA, polarization="V", power_dbm=sc.TX_POWER_DBM,
                   downtilt_deg=sc.DOWNTILT_DEG, num_beams=8)
UE_DEFAULT = dict(array="1x1", pattern=sc.UE_ANTENNA, polarization="V", height_m=sc.UE_HEIGHT_M,
                  noise_figure_db=sc.NOISE_FIGURE_DB)


def default_sectors():
    return [dict(name=s["name"], azimuth_deg=s["az"], height_m=float(s["pos"][2]), **GNB_DEFAULT)
            for s in config.sectors()]


def sector_xy(name):
    return next(s["pos"][:2] for s in config.sectors() if s["name"] == name)


def rows_cols(array):
    r, c = array.split("x")
    return int(r), int(c)


def planar_array(cfg):
    from sionna.rt import PlanarArray
    r, c = rows_cols(cfg["array"])
    return PlanarArray(num_rows=r, num_cols=c, vertical_spacing=0.5, horizontal_spacing=0.5,
                       pattern=cfg["pattern"], polarization=cfg["polarization"])


def antenna_key(s):
    """Sectors with the same key share one array and codebook, so they are traced in the same pass."""
    return (s["array"], s["pattern"], s["polarization"], s["num_beams"])


def describe(sectors, ue=None):
    """The assumptions in words, e.g. '8x8 tr38901 V, 46 dBm, 8° tilt, 8 SSB beams, 30 m'."""
    def one(s):
        beams_txt = f", {s['num_beams']} SSB beams" if s["array"] != "1x1" else ""
        return (f"{s['array']} {s['pattern']} {s['polarization']}, {s['power_dbm']:g} dBm, "
                f"{s['downtilt_deg']:g}° tilt{beams_txt}, {s['height_m']:g} m")
    texts = sorted({one(s) for s in sectors})
    gnb = texts[0] if len(texts) == 1 else "mixed: " + "; ".join(
        f"{t} ({', '.join(s['name'] for s in sectors if one(s) == t)})" for t in texts)
    if ue is None:
        return gnb
    return (f"{gnb}; UE {ue['array']} {ue['pattern']} {ue['polarization']}, {ue['height_m']:g} m, "
            f"NF {ue['noise_figure_db']:g} dB")


class Twin:
    """One Sionna scene (v1 or v2), reconfigured for each request. Not thread-safe: use it from a single thread.
    v2 has trees: per-UE results get the per-path vegetation loss (twin/vegetation.py); the coverage map, which has no
    per-path geometry, gets the crown loss on the straight line from each antenna to each cell (approximation)."""

    def __init__(self, scene_key="v1"):
        self.key = scene_key
        self.scene = sc.load(sc.SCENES[scene_key])      # campus + the 9 default transmitters (sets the Mitsuba variant)
        self.trees = vegetation.load_trees(sc.SCENES[scene_key])
        self.scene.frequency = sc.FREQUENCY_HZ
        self.freqs = np.linspace(-sc.BANDWIDTH_HZ / 2, sc.BANDWIDTH_HZ / 2, 32).astype(np.float32)   # as sc.trace
        self.grid = dict(x0=sc.AREA_X[0], y0=sc.AREA_Y[0], cell_m=GRID_M,
                         nx=int(round((sc.AREA_X[1] - sc.AREA_X[0]) / GRID_M)),
                         ny=int(round((sc.AREA_Y[1] - sc.AREA_Y[0]) / GRID_M)))
        self._outdoor_cells = None

    # ------------------------------------------------------------------ scene set-up
    def _place(self, sectors):
        """Only these sectors transmit, all with the first one's antenna settings."""
        from sionna.rt import Transmitter
        for name in list(self.scene.transmitters):
            self.scene.remove(name)
        self.scene.tx_array = planar_array(sectors[0])
        for s in sectors:
            x, y = sector_xy(s["name"])
            # orientation = [direction the sector points, downtilt, 0] in radians, as in twin/scene.py
            self.scene.add(Transmitter(s["name"], position=[float(x), float(y), float(s["height_m"])],
                                       power_dbm=float(s["power_dbm"]),
                                       orientation=[float(np.deg2rad(s["azimuth_deg"])),
                                                    float(np.deg2rad(s["downtilt_deg"])), 0.0]))

    def _groups(self, sectors):
        groups = {}
        for i, s in enumerate(sectors):
            groups.setdefault(antenna_key(s), []).append(i)
        return list(groups.values())

    def height_below(self, xy):
        return sc.height_below(self.scene, xy)

    def outdoor(self, xy):
        return sc.outdoor(self.scene, xy)

    # ------------------------------------------------------------------ per-UE measurements
    def trace_ues(self, sectors, ue, xy, rays=INTERACTIVE_RAYS, batch=50):
        """
        Per UE and sector (arrays [U, S]):
          rsrp_dbm       best beam, strongest UE receive branch (TS 38.215: not lower than any single branch)
          avg_beam_dbm   the same, averaged (as power) over the sector's beams: what the sector sends towards this
                         UE while serving other UEs, used as interference
          best_beam      index of the best beam
          los            straight line from the antenna to the UE not blocked by a building
        """
        import mitsuba as mi
        from sionna.rt import Receiver, PathSolver

        xy = np.atleast_2d(np.asarray(xy, float)).reshape(-1, 2)
        U, S = len(xy), len(sectors)
        out = dict(rsrp_dbm=np.full((U, S), NO_PATH_DB), avg_beam_dbm=np.full((U, S), NO_PATH_DB),
                   best_beam=np.zeros((U, S), int), los=np.zeros((U, S), bool))
        if U == 0:
            return out
        points = np.c_[xy, np.full(U, float(ue["height_m"]))]
        self.scene.rx_array = planar_array(ue)
        for group in self._groups(sectors):
            gs = [sectors[i] for i in group]
            self._place(gs)
            W = beams.codebook(self.scene.tx_array, gs[0]["num_beams"])           # [B, tx_ant]
            p_dbm = np.array([s["power_dbm"] for s in gs])
            for b in range(0, U, batch):
                for name in list(self.scene.receivers):
                    self.scene.remove(name)
                for j, p in enumerate(points[b:b + batch]):
                    self.scene.add(Receiver(f"ue{j}", position=[float(v) for v in p]))
                paths = PathSolver()(self.scene, max_depth=sc.MAX_BOUNCES, max_num_paths_per_src=int(3e5),
                                     samples_per_src=int(rays), synthetic_array=True,
                                     diffraction=sc.DIFFRACTION, edge_diffraction=sc.DIFFRACTION,
                                     diffuse_reflection=False, refraction=False, seed=sc.SEED)
                if self.trees is None:
                    h = paths.cfr(frequencies=mi.Float(self.freqs), out_type="numpy")   # [ue, rx_ant, tx, tx_ant, 1, f]
                else:
                    h = vegetation.cfr(paths, self.freqs, self.trees)                    # same, with vegetation loss
                g = np.einsum("urstf,bt->ursbf", h[:, :, :, :, 0, :], W)            # each beam (transpose product)
                pw = (np.abs(g) ** 2).mean(-1)                                       # [ue, rx_ant, tx, beam]
                best_per_beam = pw.max(1)                                            # strongest receive branch
                best = best_per_beam.max(-1)
                avg = pw.mean(-1).max(1)
                sl = slice(b, b + len(h))
                out["rsrp_dbm"][sl, group] = p_dbm - 10 * np.log10(RE_PER_CARRIER) + 10 * np.log10(best + 1e-30)
                out["avg_beam_dbm"][sl, group] = p_dbm - 10 * np.log10(RE_PER_CARRIER) + 10 * np.log10(avg + 1e-30)
                out["best_beam"][sl, group] = best_per_beam.argmax(-1)
        for name in list(self.scene.receivers):
            self.scene.remove(name)
        out["rsrp_dbm"] = np.maximum(out["rsrp_dbm"], NO_PATH_DB)
        out["avg_beam_dbm"] = np.maximum(out["avg_beam_dbm"], NO_PATH_DB)
        out["los"] = self.line_of_sight(sectors, points)
        out["los_clear"] = out["los"].copy()                                     # LOS that also misses every crown
        if self.trees is not None:
            ant = np.array([[*sector_xy(s["name"]), s["height_m"]] for s in sectors], float)
            a = np.repeat(ant[None], U, 0).reshape(-1, 3); b = np.repeat(points[:, None], S, 1).reshape(-1, 3)
            out["los_clear"] &= (vegetation.length_in_crowns(a, b, self.trees) == 0).reshape(U, S)
        return out

    def line_of_sight(self, sectors, points):
        """As in twin/scene.py: a ray from each antenna to each UE; blocked if it hits a building first."""
        import mitsuba as mi
        ant = np.array([[*sector_xy(s["name"]), s["height_m"]] for s in sectors], float)
        U, S = len(points), len(ant)
        start = np.repeat(ant[None], U, 0).reshape(-1, 3).astype(np.float32)
        d = (np.repeat(points[:, None], S, 1).reshape(-1, 3) - start).astype(np.float32)
        dist = np.linalg.norm(d, axis=1)
        ray = mi.Ray3f(mi.Point3f(*start.T), mi.Vector3f(*(d / dist[:, None]).T))
        ray.maxt = mi.Float((dist - 0.2).astype(np.float32))
        return ~np.array(self.scene.mi_scene.ray_test(ray)).reshape(U, S)

    # ------------------------------------------------------------------ coverage map
    def outdoor_cells(self):
        if self._outdoor_cells is None:
            g = self.grid
            xs = g["x0"] + GRID_M * (np.arange(g["nx"]) + 0.5)
            ys = g["y0"] + GRID_M * (np.arange(g["ny"]) + 0.5)
            X, Y = np.meshgrid(xs, ys)                                               # [ny, nx], y ascending
            self._outdoor_cells = self.outdoor(np.c_[X.ravel(), Y.ravel()]).reshape(g["ny"], g["nx"])
        return self._outdoor_cells

    def coverage(self, sectors, ue_height_m, rays=INTERACTIVE_RAYS):
        """
        Best-server RSRP [ny, nx] (dBm) and serving sector index on a 5 m grid at UE height, from Sionna's
        RadioMapSolver: one run per distinct beam, then the best beam per sector and cell, then the best sector.
        Row 0 is the southernmost row (y ascending), column 0 the westernmost.
        """
        import mitsuba as mi
        from sionna.rt import RadioMapSolver

        g = self.grid
        center = [g["x0"] + g["nx"] * GRID_M / 2, g["y0"] + g["ny"] * GRID_M / 2, float(ue_height_m)]
        size = [g["nx"] * GRID_M, g["ny"] * GRID_M]
        per_sector = np.full((len(sectors), g["ny"], g["nx"]), NO_PATH_DB)
        solver = RadioMapSolver()
        for group in self._groups(sectors):
            gs = [sectors[i] for i in group]
            self._place(gs)
            W = beams.unique_beams(self.scene.tx_array, gs[0]["num_beams"])
            best = None
            for w in W:
                pre = np.repeat(w[None], len(gs), 0)                                 # [tx, tx_ant], same codebook
                rm = solver(self.scene, center=center, orientation=[0.0, 0.0, 0.0], size=size,
                            cell_size=[GRID_M, GRID_M],
                            precoding_vec=(mi.TensorXf(pre.real.astype(np.float32)),
                                           mi.TensorXf(pre.imag.astype(np.float32))),
                            samples_per_tx=int(rays), max_depth=sc.MAX_BOUNCES,
                            diffraction=sc.DIFFRACTION, edge_diffraction=sc.DIFFRACTION,
                            diffuse_reflection=False, refraction=False, seed=sc.SEED)
                pg = np.array(rm.path_gain)                                          # [tx, ny, nx], precoder included
                best = pg if best is None else np.maximum(best, pg)
            if self.trees is not None:                                               # straight-line crown loss
                X, Y = np.meshgrid(g["x0"] + GRID_M * (np.arange(g["nx"]) + 0.5), g["y0"] + GRID_M * (np.arange(g["ny"]) + 0.5))
                cells = np.c_[X.ravel(), Y.ravel(), np.full(X.size, float(ue_height_m))]
                for j, s in enumerate(gs):
                    a = np.repeat(np.array([[*sector_xy(s["name"]), s["height_m"]]], float), len(cells), 0)
                    L = vegetation.length_in_crowns(a, cells, self.trees)
                    best[j] *= 10 ** (-vegetation.loss_db(L).reshape(g["ny"], g["nx"]) / 10)
            p_dbm = np.array([s["power_dbm"] for s in gs])[:, None, None]
            per_sector[group] = p_dbm - 10 * np.log10(RE_PER_CARRIER) + 10 * np.log10(best + 1e-30)
        per_sector = np.maximum(per_sector, NO_PATH_DB)
        return per_sector.max(0), per_sector.argmax(0)

    def random_ues(self, n, seed):
        return sc.random_ue_positions(self.scene, n, np.random.default_rng(seed))


# ---------------------------------------------------------------------- SINR (pure numpy, from the traced numbers)
def noise_dbm_per_prb(nf_db):
    """Thermal noise (-174 dBm/Hz) over one PRB (360 kHz), plus the UE noise figure; as twin/radio.noise_mw."""
    return -174 + 10 * np.log10(PRB_HZ) + nf_db


def serving_and_sinr(rsrp_dbm, avg_beam_dbm, nf_db):
    """
    Serving sector = strongest RSRP. SINR with every sector transmitting on every PRB (full load, as
    twin/radio.sinr_all_on_db): the serving sector's best beam against every other sector's beam-averaged power.
    RSRP is per resource element, so 10 log10(12) converts both to per-PRB power; with 1x1 arrays this is exactly
    the existing model.
    """
    to_mw = lambda d: 10 ** (np.asarray(d) / 10)                                  # noqa: E731
    serving = rsrp_dbm.argmax(1)
    u = np.arange(len(serving))
    signal = to_mw(rsrp_dbm[u, serving] + 10 * np.log10(12))
    interference = to_mw(avg_beam_dbm + 10 * np.log10(12)).sum(1) - to_mw(avg_beam_dbm[u, serving] + 10 * np.log10(12))
    sinr = 10 * np.log10(np.maximum(signal, 1e-30) / (np.maximum(interference, 0) + to_mw(noise_dbm_per_prb(nf_db))))
    return serving, sinr
