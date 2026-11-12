"""Run the whole project end to end: python run_all.py [--quick] [--skip-build] [--skip-bench]

  --quick       use config/iitgn_quick.yaml (fewer positions/drops/rays, a few minutes on a laptop CPU)
                -> data/iitgn_quick/, results/iitgn_quick/; never touches the full results/iitgn/
  --skip-build  reuse the ray-traced channel database in data/<tag>/ (skip e01)
  --skip-bench  skip the Task 8 runtime benchmark (e08, slow)
"""
import os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if "--quick" in sys.argv and not os.environ.get("DT_CONFIG"):
    os.environ["DT_CONFIG"] = str(ROOT / "config" / "iitgn_quick.yaml")   # inherited by every step below
print(f"config: {os.environ.get('DT_CONFIG') or ROOT / 'config' / 'iitgn.yaml'}", flush=True)
steps = [
    ("e01_build_twin.py", "Tasks 1-2: ray-trace the channel database"),
    ("e02_scenario_and_channels.py", "Tasks 1-2: scenario, coverage, measurements"),
    ("e03_compare_strategies.py", "Tasks 3, 4, 6: baseline vs twin-assisted allocation"),
    ("e05_mobility.py", "Task 5: mobility"),
    ("e06_twin_fidelity.py", "Task 6: twin fidelity vs allocation gain"),
    ("e07_whatif.py", "Task 7: what-if analysis"),
    ("e09_e2e_flow.py", "End-to-end flow: RAN + 5G core message trace"),
    ("e10_userplane.py", "End-to-end user plane: latency budget, B1 vs T3"),
    ("e11_mobility_e2e.py", "End-to-end mobility: Xn handovers and the site-B-off what-if"),
    ("e12_full_buffer.py", "End-to-end full-buffer throughput vs e03"),
    ("../tools/build_e2e_viewer.py", "Offline HTML viewer of the end-to-end flow (needs e09 + e11)"),
    ("e08_benchmark.py", "Task 8: computational requirements"),
]
if "--skip-build" in sys.argv:
    steps = steps[1:]
if "--skip-bench" in sys.argv:
    steps = steps[:-1]
t0 = time.time()
for script, label in steps:
    print(f"\n=== {label} ({script}) ===", flush=True)
    t = time.time()
    subprocess.run([sys.executable, "-u", str((ROOT / "experiments" / script).resolve())], check=True)
    print(f"--- finished in {time.time() - t:.0f} s", flush=True)
print(f"\nAll steps done in {(time.time() - t0) / 60:.1f} min", flush=True)
