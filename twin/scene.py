"""
The IITGN scene in Sionna RT: the OpenStreetMap campus, 3 sites x 3 sectors, the radio settings, and ray tracing.
Used by the tasks that ray-trace (tasks 1, 2, 7 and 8).
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config                                   # the 3 sites and 9 sectors (the same ones the viewer uses)

# ---- radio settings (the same as the earlier study)
FREQUENCY_HZ = 3.5e9                            # band n78
BANDWIDTH_HZ = 100e6
SCS_HZ = 30e3                                   # subcarrier spacing
NUM_PRB = 273                                   # 100 MHz at 30 kHz = 273 PRBs
TX_POWER_DBM = 46.0                             # per sector
DOWNTILT_DEG = 8.0
SECTOR_ANTENNA = "tr38901"                      # 3GPP TR 38.901 sector antenna, 8 dBi
UE_ANTENNA = "iso"                              # the phone: same gain in every direction
UE_HEIGHT_M = 1.5
NOISE_FIGURE_DB = 9.0                           # of the phone's receiver

# ---- ray-tracing settings
MAX_BOUNCES = 3                                 # up to 3 reflections
DIFFRACTION = True                              # rays also bend around building edges
RAYS_PER_SECTOR = 1_000_000                     # quick mode uses 200 000
SEED = 7

# ---- where UEs are placed: outdoors, in the area around the three sites (metres, x = east, y = north)
AREA_X = (-400.0, 450.0)
AREA_Y = (-450.0, 650.0)
SCENE_XML = ROOT / "scenes" / "iitgn" / "iitgn.xml"


def quick():
    """Quick mode (python tasks/taskN.py --quick): fewer UEs and rays, results kept apart."""
    return "--quick" in sys.argv


def folders():
    """Where a task saves its data and its tables/plots (quick mode uses separate files)."""
    data = ROOT / "data" / ("quick" if quick() else "study")
    results = ROOT / "results" / ("quick" if quick() else "study")
    data.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)
    return data, results


def sector_names():
    return [s["name"] for s in config.sectors()]


def load():
    """Load the campus into Sionna RT and put one transmitter on each of the 9 sectors."""
    import mitsuba as mi
    try:
        mi.set_variant("cuda_ad_mono_polarized")    # an NVIDIA GPU, if there is one
    except Exception:
        mi.set_variant("llvm_ad_mono_polarized")    # otherwise the CPU
    from sionna.rt import load_scene, Transmitter, PlanarArray

    scene = load_scene(str(SCENE_XML), merge_shapes=True)
    scene.frequency = FREQUENCY_HZ
    scene.bandwidth = BANDWIDTH_HZ
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern=SECTOR_ANTENNA, polarization="V")
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern=UE_ANTENNA, polarization="V")
    for s in config.sectors():
        # orientation = [direction the sector points, downtilt, 0], in radians
        scene.add(Transmitter(s["name"], position=[float(v) for v in s["pos"]], power_dbm=TX_POWER_DBM,
                              orientation=[float(np.deg2rad(s["az"])), float(np.deg2rad(DOWNTILT_DEG)), 0.0]))
    return scene


def height_below(scene, xy):
    """Height of the first surface under each (x, y): about 0 on the ground, the roof height on a building."""
    import mitsuba as mi
    xy = np.atleast_2d(xy).astype(np.float32)
    start = mi.Point3f(xy[:, 0], xy[:, 1], np.full(len(xy), 1000.0, np.float32))     # 1 km up, looking down
    hit = scene.mi_scene.ray_intersect(mi.Ray3f(start, mi.Vector3f(0, 0, -1)))
    t = np.array(hit.t)
    return np.where(np.isfinite(t), 1000.0 - t, 0.0)


def outdoor(scene, xy):
    """True where the point and the ground 2 m around it are not inside a building."""
    ok = height_below(scene, xy) < 0.5
    for dx, dy in [(2, 0), (-2, 0), (0, 2), (0, -2)]:
        ok &= height_below(scene, np.atleast_2d(xy) + [dx, dy]) < 0.5
    return ok


def random_ue_positions(scene, n, rng):
    """n random outdoor points in the area around the sites."""
    found = []
    while len(found) < n:
        xy = np.c_[rng.uniform(*AREA_X, 4 * n), rng.uniform(*AREA_Y, 4 * n)]
        found += list(xy[outdoor(scene, xy)])
    return np.array(found[:n])


def trace(scene, ue_xy, rays=RAYS_PER_SECTOR, batch=100):
    """
    Ray-trace every sector -> every UE. Returns, per UE and sector:
      path_gain_db  received power / transmitted power, antenna gains included, averaged over the 100 MHz
      los           True if the straight line from the antenna to the UE is not blocked by a building
    """
    import mitsuba as mi
    from sionna.rt import Receiver, PathSolver

    points = np.c_[ue_xy, np.full(len(ue_xy), UE_HEIGHT_M)]
    freqs = np.linspace(-BANDWIDTH_HZ / 2, BANDWIDTH_HZ / 2, 32)    # 32 frequencies across the band
    gains = []
    for b in range(0, len(points), batch):                          # a batch of UEs at a time
        for name in list(scene.receivers):
            scene.remove(name)
        for j, p in enumerate(points[b:b + batch]):
            scene.add(Receiver(f"ue{j}", position=[float(v) for v in p]))
        paths = PathSolver()(scene, max_depth=MAX_BOUNCES, samples_per_src=int(rays), max_num_paths_per_src=int(3e5),
                             diffraction=DIFFRACTION, edge_diffraction=DIFFRACTION, diffuse_reflection=False,
                             refraction=False, seed=SEED)
        h = paths.cfr(frequencies=mi.Float(freqs.astype(np.float32)), out_type="numpy")    # [UE, 1, sector, 1, 1, freq]
        gains.append((np.abs(h[:, 0, :, 0, 0, :]) ** 2).mean(-1))                       # mean |H|^2 over the band
    for name in list(scene.receivers):
        scene.remove(name)
    path_gain_db = 10 * np.log10(np.concatenate(gains) + 1e-30)                          # -300 dB = no path found

    # line of sight: send a ray from each antenna to each UE and see if a building is hit first
    ant = np.array([s["pos"] for s in config.sectors()], float)
    U, S = len(points), len(ant)
    start = np.repeat(ant[None], U, 0).reshape(-1, 3).astype(np.float32)
    d = (np.repeat(points[:, None], S, 1).reshape(-1, 3) - start).astype(np.float32)
    dist = np.linalg.norm(d, axis=1)
    ray = mi.Ray3f(mi.Point3f(*start.T), mi.Vector3f(*(d / dist[:, None]).T))
    ray.maxt = mi.Float((dist - 0.2).astype(np.float32))
    los = ~np.array(scene.mi_scene.ray_test(ray)).reshape(U, S)
    return path_gain_db, los
