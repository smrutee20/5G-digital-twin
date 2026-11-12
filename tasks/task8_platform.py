"""
Task 8: the platform. Print the computer and software the twin runs on, and measure how ray-tracing time and
memory grow with the number of UEs and of rays. Each measurement runs 3 times, each in a fresh Python process
(so its peak memory is its own), and the median of the 3 is reported.        Run:  python tasks/task8_platform.py   (--quick: two small measurements each)
"""
import csv
import json
import os
import platform
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from twin import scene as sc


def measure_once(n_ues, rays):
    """Run inside the fresh process: load the scene, place the UEs, ray-trace, report time and peak memory."""
    import resource
    import numpy as np
    t0 = time.time()
    scene = sc.load()
    t1 = time.time()
    xy = sc.random_ue_positions(scene, n_ues, np.random.default_rng(3))
    t2 = time.time()
    sc.trace(scene, xy, rays)
    t3 = time.time()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss          # bytes on macOS, kB on Linux
    peak_mb = peak / 1e6 if sys.platform == "darwin" else peak / 1e3
    print(json.dumps(dict(load_s=t1 - t0, trace_s=t3 - t2, peak_mb=peak_mb)))


if "--one" in sys.argv:                                                  # this is the fresh process
    i = sys.argv.index("--one")
    measure_once(int(sys.argv[i + 1]), int(sys.argv[i + 2]))
    sys.exit()

data, results = sc.folders()

# 1. the platform facts
ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
cpu = platform.processor()
if sys.platform == "darwin":
    cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
facts = {"CPU": cpu, "CPU cores": os.cpu_count(), "memory (GB)": round(ram, 1),
         "operating system": f"macOS {platform.mac_ver()[0]}" if sys.platform == "darwin" else platform.platform(),
         "Python": platform.python_version(),
         **{p: version(p) for p in ["sionna-rt", "mitsuba", "drjit", "numpy", "matplotlib"]}}
import mitsuba as mi
try:
    mi.set_variant("cuda_ad_mono_polarized"); facts["ray tracer runs on"] = "NVIDIA GPU (CUDA)"
except Exception:
    facts["ray tracer runs on"] = "CPU (LLVM), no GPU"
for k, v in facts.items():
    print(f"{k:22s} {v}")

# 2. the measurements: more UEs at a fixed number of rays, then more rays at a fixed number of UEs
if sc.quick():
    runs = [("UEs", n, 100_000) for n in (10, 25)] + [("rays", 25, r) for r in (50_000, 200_000)]
else:
    runs = [("UEs", n, 1_000_000) for n in (25, 50, 100, 200, 400)] + \
           [("rays", 100, r) for r in (200_000, 1_000_000, 3_000_000)]
REPEATS = 3
rows = []
print(f"\nmedian of {REPEATS} runs each")
print(f"{'vary':6s}{'UEs':>6s}{'rays/sector':>13s}{'links':>7s}{'load scene (s)':>16s}{'trace (s)':>11s}"
      f"{'(min-max)':>14s}{'per link (ms)':>15s}{'peak memory (MB)':>18s}")
for vary, n, rays in runs:
    tries = []
    for _ in range(REPEATS):                                             # the same measurement, 3 times
        out = subprocess.run([sys.executable, __file__, "--one", str(n), str(rays)], capture_output=True, text=True)
        tries.append(json.loads(out.stdout.strip().splitlines()[-1]))
    median = {k: float(np.median([t[k] for t in tries])) for k in tries[0]}
    spread = f"{min(t['trace_s'] for t in tries):.1f}-{max(t['trace_s'] for t in tries):.1f}"
    links = n * len(sc.sector_names())
    rows.append([vary, n, rays, links, round(median["load_s"], 2), round(median["trace_s"], 2), spread,
                 round(1000 * median["trace_s"] / links, 2), round(median["peak_mb"])])
    print(f"{vary:6s}{n:6d}{rays:13,d}{links:7d}{median['load_s']:16.2f}{median['trace_s']:11.2f}{spread:>14s}"
          f"{1000 * median['trace_s'] / links:15.2f}{median['peak_mb']:18.0f}")

# 3. save for the report
(results / "task8_platform.json").write_text(json.dumps(facts, indent=2))
with open(results / "task8_benchmark.csv", "w", newline="") as f:
    csv.writer(f).writerows([["vary", "ues", "rays_per_sector", "links", "scene_load_s", "trace_s", "trace_min_max_s", "ms_per_link",
                                "peak_memory_mb"]] + rows)
print(f"saved task8_platform.json and task8_benchmark.csv in {results}")
