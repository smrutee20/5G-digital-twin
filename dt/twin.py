"""
The digital twin: a 3D scene (buildings from OpenStreetMap), gNB sectors (RUs) and UEs, ray-traced with Sionna RT.

Everything the rest of the project needs from the twin goes through `DigitalTwin.trace()`,
which returns a `ChannelSet` (per UE x RU x PRB channel power). To use NVIDIA AODT instead,
write a loader that fills the same ChannelSet from AODT's CFR/raypath tables -- nothing
downstream has to change.
"""
import time
import numpy as np
import mitsuba as mi

try:                                   # GPU if available, otherwise CPU (LLVM)
    mi.set_variant("cuda_ad_mono_polarized")
    BACKEND = "cuda"
except Exception:
    mi.set_variant("llvm_ad_mono_polarized")
    BACKEND = "llvm-cpu"

from sionna.rt import (load_scene, Transmitter, Receiver, PlanarArray,
                       PathSolver, RadioMapSolver)

from .config import prb_offsets_hz
from .channel import ChannelSet, sector_gain_db


class DigitalTwin:
    def __init__(self, cfg):
        self.cfg = cfg
        sc = cfg["scene"]
        # a scene XML built by tools/build_scene.py
        if not sc.get("xml"):
            raise ValueError("config scene.xml is missing: build a scene with tools/build_scene.py first")
        self.scene = load_scene(sc["xml"], merge_shapes=True)
        self.scene.frequency = cfg["carrier"]["frequency_hz"]
        self.scene.bandwidth = cfg["carrier"]["bandwidth_hz"]
        self.scene.tx_array = PlanarArray(num_rows=1, num_cols=1,
                                          pattern=cfg["ran"]["antenna_pattern"], polarization="V")
        self.scene.rx_array = PlanarArray(num_rows=1, num_cols=1,
                                          pattern=cfg["ue"]["antenna_pattern"], polarization="V")
        self._build_rus()

    def perturb_materials(self, eps_scale=1.0, sigma_scale=1.0):
        """Make the scene's materials differ from the ITU defaults (used for the 'physical' network)."""
        for name, m in self.scene.radio_materials.items():
            if name == "metal":
                continue
            m.relative_permittivity = m.relative_permittivity * eps_scale
            m.conductivity = m.conductivity * sigma_scale

    # ------------------------------------------------------------------ RAN layout
    def _build_rus(self, active=None):
        r = self.cfg["ran"]
        for name in list(self.scene.transmitters):
            self.scene.remove(name)
        self.rus = []
        for s_i, site in enumerate(r["sites"]):
            for az in site.get("sector_azimuths_deg", r["sector_azimuths_deg"]):   # per-site override
                ru = dict(name=f"{site['name']}{int(az)}", site=site["name"], site_idx=s_i,
                          pos=np.array([*site["xy"], site.get("height_m", r["height_m"])], float),
                          az_deg=float(az), tilt_deg=float(r["downtilt_deg"]))
                self.rus.append(ru)
                self.scene.add(Transmitter(
                    ru["name"], position=[float(v) for v in ru["pos"]],
                    orientation=[float(np.deg2rad(az)), float(np.deg2rad(r["downtilt_deg"])), 0.0],
                    power_dbm=float(r["tx_power_dbm"])))
        self.ru_pos = np.array([ru["pos"] for ru in self.rus])
        self.ru_az = np.array([ru["az_deg"] for ru in self.rus])
        self.ru_tilt = np.array([ru["tilt_deg"] for ru in self.rus])
        self.ru_site = np.array([ru["site_idx"] for ru in self.rus])
        self.ru_names = [ru["name"] for ru in self.rus]

    # ------------------------------------------------------------------ geometry helpers
    def ground_height(self, xy):
        """Height of the first surface below (x, y): ~0 on streets, roof height on buildings."""
        xy = np.atleast_2d(xy).astype(np.float32)
        o = mi.Point3f(xy[:, 0], xy[:, 1], np.full(len(xy), 1000.0, np.float32))
        si = self.scene.mi_scene.ray_intersect(mi.Ray3f(o, mi.Vector3f(0, 0, -1)))
        t = np.array(si.t)
        return np.where(np.isfinite(t), 1000.0 - t, 0.0)

    def is_outdoor(self, xy, clearance=1.5):
        """Street-level point with no building within `clearance` metres."""
        xy = np.atleast_2d(xy)
        ok = self.ground_height(xy) < 0.5
        for dx, dy in [(clearance, 0), (-clearance, 0), (0, clearance), (0, -clearance)]:
            ok &= self.ground_height(xy + [dx, dy]) < 0.5
        return ok

    def sample_outdoor(self, n, rng, center=None, radius=None):
        lo, hi = self.cfg["scene"]["area_xy"]
        out = []
        while sum(len(o) for o in out) < n:
            if center is None:
                cand = rng.uniform(lo, hi, size=(4 * n, 2))
            else:
                r = radius * np.sqrt(rng.uniform(size=4 * n))
                a = rng.uniform(0, 2 * np.pi, size=4 * n)
                cand = np.c_[center[0] + r * np.cos(a), center[1] + r * np.sin(a)]
            out.append(cand[self.is_outdoor(cand)])
        xy = np.concatenate(out)[:n]
        return np.c_[xy, np.full(n, self.cfg["ue"]["height_m"])]

    def los_mask(self, ue_pos):
        """True where the straight line RU -> UE is not blocked by a building."""
        U, R = len(ue_pos), len(self.ru_pos)
        o = np.repeat(self.ru_pos[None], U, 0).reshape(-1, 3).astype(np.float32)
        d = (np.repeat(ue_pos[:, None], R, 1).reshape(-1, 3) - o).astype(np.float32)
        dist = np.linalg.norm(d, axis=1)
        d /= dist[:, None]
        ray = mi.Ray3f(mi.Point3f(*o.T), mi.Vector3f(*d.T))
        ray.maxt = mi.Float((dist - 0.2).astype(np.float32))
        hit = np.array(self.scene.mi_scene.ray_test(ray))
        return ~hit.reshape(U, R)

    # ------------------------------------------------------------------ ray tracing
    def trace(self, ue_pos, profile="twin", batch=200, label=None):
        """Ray-trace every RU -> UE link and return per-PRB channel power."""
        rt = self.cfg["raytracing"][profile]
        freqs = mi.Float(prb_offsets_hz(self.cfg).astype(np.float32))
        H2, DS, NP = [], [], []
        t0 = time.time()
        for b in range(0, len(ue_pos), batch):
            P = ue_pos[b:b + batch]
            for name in list(self.scene.receivers):
                self.scene.remove(name)
            for j, p in enumerate(P):
                self.scene.add(Receiver(f"ue{j}", position=[float(v) for v in p]))
            paths = PathSolver()(self.scene, max_depth=rt["max_depth"],
                                 samples_per_src=int(rt["samples_per_src"]),
                                 max_num_paths_per_src=int(3e5),
                                 diffraction=rt["diffraction"], edge_diffraction=rt["edge_diffraction"],
                                 diffuse_reflection=rt["diffuse_reflection"], refraction=False,
                                 seed=self.cfg["scene"]["seed"])
            h = paths.cfr(frequencies=freqs, out_type="numpy")        # [U,1,R,1,1,K]
            H2.append((np.abs(h[:, 0, :, 0, 0, :]) ** 2).astype(np.float32))
            a, tau = paths.cir(out_type="numpy", normalize_delays=False)
            p = np.abs(a[:, 0, :, 0, :, 0]) ** 2                         # [U,R,P]
            tau = np.asarray(tau).reshape(p.shape)
            w = p.sum(-1, keepdims=True)
            with np.errstate(invalid="ignore", divide="ignore"):
                m1 = (p * tau).sum(-1) / w[..., 0]
                m2 = (p * tau ** 2).sum(-1) / w[..., 0]
            DS.append(np.sqrt(np.maximum(m2 - m1 ** 2, 0)) * 1e9)       # ns
            NP.append((p > 0).sum(-1))
        for name in list(self.scene.receivers):
            self.scene.remove(name)
        runtime = time.time() - t0
        ch = ChannelSet(pos=np.asarray(ue_pos, float), H2=np.concatenate(H2),
                        los=self.los_mask(ue_pos), ru_pos=self.ru_pos, ru_az=self.ru_az,
                        ru_tilt=self.ru_tilt, ru_site=self.ru_site, ru_names=self.ru_names,
                        delay_spread_ns=np.nan_to_num(np.concatenate(DS)),
                        num_paths=np.concatenate(NP), profile=label or profile)
        ch.meta["runtime_s"] = runtime
        ch.meta["backend"] = BACKEND
        return ch

    def coverage_map(self, profile="twin", cell=5.0):
        """Path-gain radio map for every RU on a horizontal plane at UE height."""
        rt = self.cfg["raytracing"][profile]
        lo, hi = self.cfg["scene"]["area_xy"]
        size = hi - lo + 100
        rm = RadioMapSolver()(self.scene, center=mi.Point3f(0, 0, self.cfg["ue"]["height_m"]),
                              orientation=mi.Point3f(0, 0, 0), size=mi.Point2f(size, size),
                              cell_size=mi.Point2f(cell, cell), samples_per_tx=int(3e6),
                              max_depth=rt["max_depth"], diffraction=rt["diffraction"],
                              edge_diffraction=rt["edge_diffraction"])
        pg = np.array(rm.path_gain)                                        # [R, ny, nx]
        centers = np.array(rm.cell_centers)                                # [ny, nx, 3]
        return pg, centers
