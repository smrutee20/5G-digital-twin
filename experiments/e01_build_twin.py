"""
Tasks 1-2: build the scenario, ray-trace the channel database, and build the
'physical network' stand-in used later for the what-if validation.

Outputs (data/):
  twin_pool.npz        twin channels at the true UE positions   (Tasks 2-6)
  twin_est_pool.npz    twin channels at GPS-noisy UE positions  (what the twin 'believes', Task 7)
  physical_pool.npz    high-fidelity trace + impairments        (ground truth, Task 7)
  coverage.npz         per-RU path-gain radio map + building height map
"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from dt.config import load_config, DATA
from dt.twin import DigitalTwin, BACKEND
from dt.channel import apply_impairments

cfg = load_config()
rng = np.random.default_rng(cfg["scene"]["seed"])
twin = DigitalTwin(cfg)
print("backend:", BACKEND, "| RUs:", twin.ru_names)

# ---------------- candidate UE positions: uniform pool + a hotspot cluster (for what-if)
n = cfg["experiments"]["pool_size"]
uniform = twin.sample_outdoor(n, rng)
hot_center = uniform[np.argmin(np.linalg.norm(uniform[:, :2] - cfg["scene"].get("hotspot_xy", [0, 0]), axis=1)), :2]
hotspot = twin.sample_outdoor(150, rng, center=hot_center, radius=45)
pos = np.vstack([uniform, hotspot])
is_hot = np.r_[np.zeros(len(uniform), bool), np.ones(len(hotspot), bool)]

# GPS-like position error: what the operator *thinks* the UE positions are
err = cfg["physical_impairments"]["ue_position_error_m"]
pos_est = pos.copy()
todo = np.ones(len(pos), bool)
for _ in range(20):
    cand = pos[todo] + np.c_[rng.normal(0, err, (todo.sum(), 2)), np.zeros(todo.sum())]
    ok = twin.is_outdoor(cand[:, :2], clearance=0.5)
    idx = np.where(todo)[0][ok]
    pos_est[idx] = cand[ok]
    todo[idx] = False
    if not todo.any():
        break

log = {}
fc = cfg["carrier"]["frequency_hz"]


def cached(name, fn):
    """Ray tracing is the slow step: keep every finished trace on disk."""
    f = DATA / f"_raw_{name}.npz"
    if f.exists():
        from dt.channel import ChannelSet
        c = ChannelSet.load(f); print(f"{name}: loaded cached trace"); return c
    t = time.time(); c = fn(); c.meta["runtime_s"] = time.time() - t
    c.save(f); print(f"{name}: traced in {c.meta['runtime_s']:.0f}s, rt links found {c.rt_found.mean():.1%}")
    return c


np.savez(DATA / "_positions.npz", pos=pos, pos_est=pos_est, is_hot=is_hot) if not (DATA / "_positions.npz").exists() else None
z = np.load(DATA / "_positions.npz"); pos, pos_est, is_hot = z["pos"], z["pos_est"], z["is_hot"]

twin_ch = cached("twin", lambda: twin.trace(pos, "twin"))
est_ch = cached("twin_est", lambda: twin.trace(pos_est, "twin", label="twin@noisy-pos"))
imp = cfg["physical_impairments"]
twin.perturb_materials(imp["permittivity_scale"], imp["conductivity_scale"])
phys_raw = cached("physical", lambda: twin.trace(pos, "physical"))
twin.perturb_materials(1 / imp["permittivity_scale"], 1 / imp["conductivity_scale"])
log.update(trace_twin_s=twin_ch.meta["runtime_s"], trace_twin_est_s=est_ch.meta["runtime_s"],
           trace_physical_s=phys_raw.meta["runtime_s"])

fill = cfg["raytracing"].get("fill", {})
fopt = dict(weak_db=fill.get("weak_db", 18.0), shadow_db=fill.get("shadow_db", 6.0))
calib = twin_ch.fill_unresolved(fc, **fopt)
est_ch.fill_unresolved(fc, calib, **fopt)
phys_raw.fill_unresolved(fc, seed=1, **fopt)          # own shadowing draw: the twin must not know it
print(f"fill calibration {calib:.1f} dB, filled {twin_ch.meta['filled_frac']:.1%} of links "
      f"({twin_ch.meta['filled_missing_frac']:.1%} no path, {twin_ch.meta['filled_weak_frac']:.1%} "
      f"> {fopt['weak_db']} dB below 38.901 NLOS)")
phys = apply_impairments(phys_raw, cfg, np.random.default_rng(99))

for c, name in [(twin_ch, "twin_pool"), (est_ch, "twin_est_pool"), (phys, "physical_pool")]:
    c.meta["is_hotspot"] = is_hot.tolist()
    c.save(DATA / f"{name}.npz")

# ---------------- coverage map + building height map (for figures)
t = time.time(); pg, centers = twin.coverage_map("twin", cfg["experiments"]["coverage_cell_m"])
log["coverage_map_s"] = time.time() - t
H = cfg["scene"]["half"] + 50
xs = np.arange(-H, H, 2.0)
gx, gy = np.meshgrid(xs, xs)
hmap = twin.ground_height(np.c_[gx.ravel(), gy.ravel()]).reshape(gx.shape)
np.savez_compressed(DATA / "coverage.npz", pg=pg, centers=centers, hmap=hmap, hx=xs,
                    hot_center=hot_center)
log.update(backend=BACKEND, num_positions=len(pos), num_rus=len(twin.ru_names),
           rt_found_twin=float(1 - twin_ch.meta["filled_missing_frac"]),
           rt_found_physical=float(1 - phys_raw.meta["filled_missing_frac"]),
           fill_calib_db=calib, filled_frac=twin_ch.meta["filled_frac"],
           filled_weak_frac=twin_ch.meta["filled_weak_frac"], fill_weak_db=fopt["weak_db"])
json.dump(log, open(DATA / "build_log.json", "w"), indent=2)
print(json.dumps(log, indent=2))
