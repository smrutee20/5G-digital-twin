"""
Task 8: computational requirements of the digital twin on the machine it runs on.
Each configuration runs in a fresh process so peak memory is measured cleanly.
"""
import sys, json, subprocess, resource, platform, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from dt.config import load_config, DATA, FIG, TAB

cfg = load_config()
NUM_RUS = sum(len(s.get("sector_azimuths_deg", cfg["ran"]["sector_azimuths_deg"])) for s in cfg["ran"]["sites"])
lo, hi = cfg["scene"]["area_xy"]

WORKER = r'''
import sys, time, json, resource, numpy as np
sys.path.insert(0, sys.argv[1])
from dt.config import load_config
from dt.twin import DigitalTwin, BACKEND
cfg = load_config()
n, depth, samples, diff, mode = int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), sys.argv[5] == "1", sys.argv[6]
cfg["raytracing"]["bench"] = dict(max_depth=depth, samples_per_src=samples, diffraction=diff,
                                  edge_diffraction=diff, diffuse_reflection=False)
t0 = time.time(); tw = DigitalTwin(cfg); t_load = time.time() - t0
pos = tw.sample_outdoor(n, np.random.default_rng(0)) if n else None
t0 = time.time()
if mode == "paths":
    tw.trace(pos, "bench")
else:
    tw.cfg["raytracing"]["twin"] = cfg["raytracing"]["bench"]; tw.coverage_map("twin", 5.0)
print(json.dumps(dict(backend=BACKEND, load_s=t_load, run_s=time.time() - t0,
                      # ru_maxrss is in bytes on macOS, kilobytes on Linux
                      peak_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 ** 2 if sys.platform == "darwin" else 1024))))
'''

configs = []
for n in [25, 100, 300, 600]:
    configs.append(("UEs", n, 3, 3e5, 1, "paths"))
for s in [1e5, 3e5, 1e6]:
    configs.append(("rays per RU", 100, 3, s, 1, "paths"))
for d in [1, 2, 3, 4]:
    configs.append(("max depth", 100, d, 3e5, 0, "paths"))
configs.append(("diffraction on (vs depth-3 row above)", 100, 3, 3e5, 1, "paths"))
configs.append((f"radio map {hi - lo}x{hi - lo} m @5 m", 0, 3, 3e5, 1, "map"))

wf = DATA / "_bench_worker.py"
wf.write_text(WORKER)
rows = []
for sweep, n, d, s, diff, mode in configs:
    out = subprocess.run([sys.executable, str(wf), str(ROOT), str(n), str(d), str(s), str(diff), mode],
                         capture_output=True, text=True)
    try:
        r = json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        print(out.stderr[-2000:]); continue
    rows.append(dict(sweep=sweep, num_ues=n, num_rus=NUM_RUS, links=n * NUM_RUS, max_depth=d, rays_per_ru=int(s),
                     diffraction=bool(diff), mode=mode, runtime_s=round(r["run_s"], 1),
                     scene_load_s=round(r["load_s"], 1), peak_memory_mb=round(r["peak_mb"]),
                     backend=r["backend"]))
    print(rows[-1])
wf.unlink()
df = pd.DataFrame(rows)
df.to_csv(TAB / "t8_benchmark.csv", index=False)
hw = dict(cpu=platform.processor() or platform.machine(), cores=os.cpu_count(),
          ram_gb=round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1),
          python=platform.python_version(), backend=rows[0]["backend"] if rows else None)
json.dump(hw, open(TAB / "t8_hardware.json", "w"), indent=2)

from dt.plotstyle import plt, save, CAT, INK2
fig, axs = plt.subplots(1, 3, figsize=(15, 4))
for ax, sweep, x, xl in [(axs[0], "UEs", "num_ues", f"Number of UEs (x {NUM_RUS} RUs)"),
                         (axs[1], "rays per RU", "rays_per_ru", "Rays launched per RU"),
                         (axs[2], "max depth", "max_depth", "Max interactions per path")]:
    d = df[df.sweep == sweep]
    ax.plot(d[x], d.runtime_s, "o-", color=CAT[0], ms=8)
    for _, r in d.iterrows():
        ax.annotate(f"{r.runtime_s:.0f} s", (r[x], r.runtime_s), xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=8, color=INK2)
    ax.set_xlabel(xl); ax.set_ylabel("Ray-tracing time [s]")
    if sweep == "rays per RU":
        ax.set_xscale("log")
fig.suptitle(f"Twin runtime on this machine ({hw['cores']} CPU cores, no GPU, {hw['backend']})",
             x=0.02, ha="left", weight="bold")
fig.tight_layout()
save(fig, FIG / "fig15_runtime_scaling.png")
print(df.to_string())
