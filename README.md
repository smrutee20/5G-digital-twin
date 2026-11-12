# 5G RAN Digital Twin for Channel-Aware Resource Allocation and What-If Analysis

Course project, *5G and Beyond* (Semester I, 2026). A site-specific digital twin of a
3-site / 9-sector NR n78 network on the IIT Gandhinagar campus, built on **NVIDIA Sionna RT**
(the open-source ray tracer from NVIDIA's Aerial/Sionna stack). The twin is used to

1. obtain per-link, per-PRB channel information for every UE location,
2. drive a channel-aware cell association + PRB scheduler,
3. compare it against fixed / random baselines on 5G KPIs,
4. follow moving UEs through LOS/NLOS transitions, and
5. predict the effect of network changes (what-if) **before** applying them, with the
   prediction checked against a higher-fidelity "physical network" stand-in.

## How to run

Everything below is typed in a terminal (on a Mac: the *Terminal* app). Lines starting with `#` are comments.

### 1. Requirements

| | Tested with |
|---|---|
| OS | macOS 26.5 on an Apple M4 (CPU only). Linux with an NVIDIA GPU also works (see [Running on another site or on a GPU server](#running-on-another-site-or-on-a-gpu-server)). |
| Python | 3.14.7 (`python3 --version`). The pinned versions in `requirements.txt` are for this Python. On a Mac, get it with `brew install python@3.14` or from python.org. |
| Disk | ~1 GB for the virtual environment, ~150 MB for a full run's data and results |
| Other | `git`. On a Mac, the ray tracer's CPU back end needs LLVM: `brew install llvm` (see step 3) |

No GPU is needed. When an NVIDIA GPU is present, Mitsuba's `cuda_ad_*` variant is used automatically. Otherwise the CPU (LLVM) variant is used.

### 2. Set up (once)

```bash
git clone https://github.com/smrutee20/5G-digital-twin.git
cd 5G-digital-twin
python3 -m venv .venv                 # a private Python environment inside the project folder
source .venv/bin/activate             # the prompt now starts with (.venv); repeat this in every new terminal
python -m pip install --upgrade pip
python -m pip install -r requirements.txt     # exact versions, ~2-3 min
```

All later commands assume you are in the `5G-digital-twin` folder with the venv activated. To skip the
activation step, write `.venv/bin/python3` instead of `python`.

### 3. Check the ray tracer

```bash
python -c "import mitsuba as mi; mi.set_variant('llvm_ad_mono_polarized'); import sionna.rt; print('ok', mi.__version__, sionna.rt.__version__)"
```

You should see `ok 3.9.1 2.2.0`. If you get an error that mentions **LLVM** (for example
`jit_llvm_init(): LLVM API initialization failed`), install LLVM and tell Dr.Jit where it is:

```bash
brew install llvm
export DRJIT_LIBLLVM_PATH="$(brew --prefix llvm)/lib/libLLVM.dylib"
# then run the check again. To make this permanent, add the export line to ~/.zshrc
```

Optional: `python tests/test_e2e_procedures.py` checks UE registration and PDU session set-up in the end-to-end
layer. It needs a run's data first, so run it after step 4 with
`DT_CONFIG=config/iitgn_quick.yaml python tests/test_e2e_procedures.py` (or without `DT_CONFIG` after the full run).

### 4. Run

**Quick run (~5 min on an M4).** Same campus, sites and code, but fewer UE positions (450 instead of 1500),
10 instead of 30 Monte Carlo drops, fewer rays and a 10 m instead of 5 m coverage grid (`config/iitgn_quick.yaml`).
Use it to check that everything works. It writes to `data/iitgn_quick/` and `results/iitgn_quick/` and never touches the
full results.

```bash
python run_all.py --quick --skip-bench
```

**Full run (~45 min on an M4, most of it ray tracing).** This reproduces the numbers in `REPORT.md` and writes
`data/iitgn/` and `results/iitgn/`. It overwrites the result tables and figures that come with the repository, but with
the same numbers. On a Mac, `caffeinate -i` stops the computer from sleeping during the run:

```bash
caffeinate -i python run_all.py --skip-bench
```

Other options: `--skip-build` reuses the ray traces already in `data/<tag>/` (skips e01, so a re-run takes a few
minutes). Leaving out `--skip-bench` adds the Task 8 benchmark (e08, a few extra minutes). You can also run a single
step after e01, e.g. `python experiments/e07_whatif.py` (add `DT_CONFIG=config/iitgn_quick.yaml` in front for quick mode).

What each step produces (figures in `results/<tag>/figures/`, tables in `results/<tag>/tables/`):

| Step | Task | Produces |
|---|---|---|
| `e01_build_twin.py` | 1-2 | Ray traces of every UE position from all 9 RUs: the twin, the twin at noisy UE positions, and the higher-fidelity "physical network"; coverage map; `data/<tag>/build_log.json` |
| `e02_scenario_and_channels.py` | 1-2 | `fig01`-`fig05` (scenario, RSRP/SINR coverage, best server, RSRP vs distance, frequency selectivity); `t1_parameters`, `t2_channel_database`, `t2_ue_measurements`, `t2_summary` |
| `e03_compare_strategies.py` | 3, 4, 6 | Baselines B1/B2 vs twin-assisted T1/T2/T3 over the drops: `fig06`-`fig09`; `t6_kpi_summary`, `t6_kpi_ci95`, `t6_kpi_per_drop`, `t6_gains` |
| `e05_mobility.py` | 5 | Three walks traced every 2 m, re-association events: `fig10`, `fig11`; `t5_*` |
| `e06_twin_fidelity.py` | 6 | How position, material and sync errors in the twin reduce the gain: `fig16`; `t6_twin_fidelity` |
| `e07_whatif.py` | 7 | What-if scenarios predicted by the twin vs the "physical network": `fig12`-`fig14`; `t7_*` |
| `e08_benchmark.py` | 8 | Ray-tracing runtime and memory scaling: `fig15`; `t8_benchmark`, `t8_hardware` (only without `--skip-bench`) |
| `e09_e2e_flow.py` | E2E | Every RAN + 5G core message for 30 UEs attaching and streaming: `results/<tag>/e2e_trace.json`; `t9_*` (with built-in checks) |
| `e10_userplane.py` | E2E | Downlink packet latency, B1 vs T3: `fig18`-`fig20`; `t10_*` |
| `e11_mobility_e2e.py` | E2E | Xn handovers on the e05 walks and the "site B off" what-if: `fig21`-`fig23`; `t11_*`; `e2e_trace_mobility.json`, `e2e_trace_siteoff.json`, `e2e_kpis_*.json` |
| `e12_full_buffer.py` | E2E | Full-buffer end-to-end throughput, checked against e03: `fig24`; `t12_*` |
| `tools/build_e2e_viewer.py` | E2E | `results/<tag>/e2e_viewer.html` (last step of `run_all.py`) |

There is no `e04`: Task 4 (channel-aware allocation) is part of e03.

### 5. Viewers

**End-to-end flow viewer** (built automatically at the end of `run_all.py`). It is one self-contained HTML file and
works offline:

```bash
python tools/build_e2e_viewer.py                                        # full run -> results/iitgn/e2e_viewer.html
DT_CONFIG=config/iitgn_quick.yaml python tools/build_e2e_viewer.py      # quick run -> results/iitgn_quick/e2e_viewer.html
open results/iitgn/e2e_viewer.html                                      # macOS; on Linux use xdg-open
```

The repository already includes `results/iitgn/e2e_viewer.html`, so you can open it straight after cloning. It shows
the network topology with animated messages, sequence diagrams, the campus map and live KPIs, for three
scenarios: attach, mobility with handovers, and site B off.

**3D twin viewer** (not part of `run_all.py`; run it after a run). It needs internet the first time it opens,
to load three.js from a CDN:

```bash
python tools/export_3d.py                                               # -> results/iitgn/twin_3d.html (a few seconds)
DT_CONFIG=config/iitgn_quick.yaml python tools/export_3d.py             # -> results/iitgn_quick/twin_3d.html
open results/iitgn/twin_3d.html
```

### 6. Outputs and expected numbers

| Where | What |
|---|---|
| `results/<tag>/figures/` | All figures, PNG |
| `results/<tag>/tables/` | All tables, CSV / JSON |
| `results/<tag>/*.html` | Viewers |
| `results/<tag>/e2e_trace*.json` | End-to-end message traces |
| `data/<tag>/` | Ray-trace caches (`_raw_*.npz`) and channel pools. Delete them to force a re-trace. Not in git. |

`<tag>` is `iitgn` for the full run and `iitgn_quick` for the quick run. Both runs use fixed seeds, so on the same
package versions they should give these numbers to within rounding. The quick run uses fewer positions and
drops, so its numbers differ, but the trends should be the same: T3 > T2 ≈ T1 > B1 ≈ B2.

| Check | File | Full run | Quick run |
|---|---|---|---|
| LOS fraction of all links | `e02` → `t2_summary.json` | 0.68 | 0.68 |
| Median RSRP / SINR | `e02` → `t2_summary.json` | -77.2 dBm / 4.0 dB | -76.8 dBm / 3.0 dB |
| Mean UE throughput B1 → T3 | `e03` → `t6_kpi_summary.csv` | 23.9 → 54.6 Mbps | 25.6 → 54.2 Mbps |
| T3 vs B1 mean throughput | `e03` → `t6_gains.json` | +129 % | +112 % |
| Outage (<1 Mbps) B1 → T3 | `e03` → `t6_kpi_summary.csv` | 19.2 → 0.0 % | 17.7 → 0.0 % |
| Mean SINR B1 → T3 | `e03` → `t6_kpi_summary.csv` | 1.5 → 16.0 dB | 3.0 → 16.6 dB |
| What-if change error, twin (sync) vs 38.901 | `e07` → `t7_accuracy.json` | 2.7 vs 18.0 pp | 2.6 vs 19.3 pp |
| Messages total / control msgs per attach | `e09` → `t9_e2e_summary.json` | 10084 / 103.1 | 10084 / 103.1 |
| Registration median | `e09` → `t9_e2e_summary.json` | 70.8 ms | 70.8 ms |
| DL packets delivered B1 vs T3 | `e10` → `t10_userplane_kpis.csv` | 61.5 vs 98.9 % | 69.3 vs 98.9 % |
| T3 e2e latency p50 / p95 | `e10` → `t10_userplane_kpis.csv` | 8.0 / 10.1 ms | 8.0 / 10.0 ms |
| Xn handovers / packets lost by handover | `e11` → `t11_summary.json` | 6 / 0 | 8 / 0 |
| Site B off: affected UEs, mean interruption | `e11` → `t11_summary.json` | 9, 470 ms | 5, 471 ms |
| Full-buffer e2e mean B1 / T3 | `e12` → `t12_full_buffer.csv` | 27.8 / 50.0 Mbps | 22.3 / 55.9 Mbps |

All e09-e12 checks print `[PASS]`; a `[FAIL]` line in the run's output means something is wrong.
The quick-run column was measured on a fresh clone (macOS 26.5, Apple M4, the pinned packages).

Small differences in the last digit are normal across machines (CPU vs GPU ray tracing, different BLAS). A different
*ranking* of the strategies means something is wrong.

### 7. Troubleshooting

| Problem | Fix |
|---|---|
| `jit_llvm_init(): LLVM API initialization failed` or another error mentioning LLVM / `libLLVM` | `brew install llvm`, then `export DRJIT_LIBLLVM_PATH="$(brew --prefix llvm)/lib/libLLVM.dylib"` and retry (step 3). On Linux, install `llvm` with your package manager and point the variable to `libLLVM.so`. |
| `command not found: python`, or `ModuleNotFoundError: No module named 'sionna'` / `'yaml'` | The venv is not active. Run `source .venv/bin/activate`, or call `.venv/bin/python3` directly. If `python` is *still* not found after activating, see the next row. |
| **After moving or renaming the project folder**: `pip` gives `bad interpreter: .../old-folder/.venv/bin/python3...: no such file or directory`, or `python` gives `command not found` even after `source .venv/bin/activate` (`echo $VIRTUAL_ENV` shows the old path) | A venv only works where it was created, because its scripts store the old path. Delete it and make a new one (~1 min): `deactivate; rm -rf .venv && python3 -m venv .venv && source .venv/bin/activate && python -m pip install -r requirements.txt`. Your data and results are not affected. |
| `pip install` fails to find a version | Your Python is not 3.14. Check with `python3 --version` and create the venv with `python3.14 -m venv .venv`. |
| `FileNotFoundError: .../data/iitgn/twin_pool.npz` | You used `--skip-build` or ran a single step before e01 had run for this config. Run `python run_all.py` (or with `--quick`) without `--skip-build` first. |
| The 3D viewer (`twin_3d.html`) is blank or grey | It loads three.js from cdnjs / jsDelivr. Connect to the internet once, and make sure nothing blocks those CDNs. Open the file directly in Chrome, Safari or Firefox. |
| The e2e viewer (`e2e_viewer.html`) is blank or stuck loading | It is self-contained (~13 MB) and can take a few seconds to start. If it stays blank, open the browser's developer console (Cmd+Option+J in Chrome) to see the error. If the file is much smaller than ~10 MB, e11 did not finish: re-run `python experiments/e11_mobility_e2e.py`, then `python tools/build_e2e_viewer.py`. |
| The Mac went to sleep or the run stopped part-way | Re-run the **same** command with `caffeinate -i` in front. e01 saves each finished ray trace (`data/<tag>/_raw_*.npz`) and reloads it, so only the unfinished traces are redone. Use `--skip-build` only if e01 had finished (it printed `--- finished in`). |
| Ray tracing is very slow | Normal on a CPU: about 45 min on an M4 for the full run. Use `--quick` to test. |

Note: the ray-trace caches in `data/` and the large end-to-end traces (`e2e_trace_mobility.json`,
`e2e_kpis_mobility.json`, `e2e_trace_siteoff.json`) are too large for git and are not in this repository. A fresh
clone regenerates them with the full run. The tables, figures and `results/iitgn/e2e_viewer.html` are included.

## Running on another site or on a GPU server

```bash
python tools/build_scene.py --name <site> --lat <lat> --lon <lon> --size 1400   # OSM -> scenes/<site>/ + config/<site>.yaml
DT_CONFIG=config/<site>.yaml python run_all.py                                 # results/<site>/
```

`build_scene.py` refuses to overwrite an existing config (such as the hand-tuned `config/iitgn.yaml`) unless you pass `--force`.

For a SLURM GPU server, see `tools/kratu_job.sbatch` and `tools/check_env.sh`.

## Repository layout

| Path | What it is |
|---|---|
| `config/iitgn.yaml` | **All** scenario parameters (IIT Gandhinagar campus): carrier, sites, power, antennas, ray-tracing fidelity, impairments, experiment sizes |
| `dt/twin.py` | The digital twin: scene, RUs, outdoor UE sampling, LOS test, ray tracing -> `ChannelSet` |
| `dt/channel.py` | Channel database (`ChannelSet`), 3GPP TR 38.901 helpers, statistical model, physical-network impairments |
| `dt/kpi.py` | KPI engine: effective SINR, CQI (TS 38.214 Table 5.2.2.1-3), throughput, fairness |
| `dt/alloc.py` | Association + scheduling strategies (B1, B2, T1, T2, T3) and the slot-level DL simulator |
| `experiments/e01_build_twin.py` | Tasks 1-2: ray-trace the channel database (twin, twin at noisy positions, physical) |
| `experiments/e02_scenario_and_channels.py` | Tasks 1-2: scenario/coverage figures, channel table, RAN measurements |
| `experiments/e03_compare_strategies.py` | Tasks 3, 4, 6: Monte Carlo comparison of all strategies |
| `experiments/e05_mobility.py` | Task 5: moving UEs, re-association events |
| `experiments/e06_twin_fidelity.py` | Task 6: how twin accuracy (positions, materials, sync) changes the gain |
| `experiments/e07_whatif.py` | Task 7: what-if prediction vs "actual" |
| `experiments/e08_benchmark.py` | Task 8: runtime / memory scaling of the twin |
| `dt/e2e/`, `experiments/e09_e2e_flow.py` | End-to-end flow layer on top of the radio twin: discrete-event model of UE, RU, DU (T3 scheduler), CU-CP, CU-UP, AMF, SMF, UPF, AUSF, UDM, NRF, PCF and a DN server over Uu, fronthaul, F1, E1, N2, N3, N4, N6 and SBI; every message in `results/iitgn/e2e_trace.json` |
| `dt/e2e/userplane.py`, `experiments/e10_userplane.py` | Downlink packets server -> UPF -> GTP-U -> CU-UP -> DU scheduler -> RU -> UE; air-interface rate and delay from the twin's SINR and B1/T3 PRB allocation; per-hop latency budget and E2E latency, B1 vs T3 (Figs 18-20, `t10_*`) |
| `scenes/iitgn/` | Campus scene built from OpenStreetMap (XML, meshes, footprints, layout plots) |
| `data/iitgn/` | Cached ray traces and channel database |
| `results/iitgn/figures/`, `results/iitgn/tables/` | All figures (`fig01` ... `fig16`) and tables (`t1` ... `t7`; `t8` after running e08) |
| `results/iitgn_rooftop_centre/` | Results of site layout 1 (rooftop masts), REPORT §10 |
| `REPORT.md` | Full project report |
| `dt/scene_builder.py`, `tools/build_scene.py` | Build a scene of any real site from OpenStreetMap, place rooftop gNBs, write its config |
| `tools/export_3d.py` | Interactive 3D web view of the twin (`results/iitgn/twin_3d.html`) |
| `tools/check_env.sh`, `tools/kratu_job.sbatch` | GPU-server check, SLURM job |

## Strategies compared

| ID | Association | PRB allocation | Uses twin? |
|---|---|---|---|
| B1 | Nearest site, sector by bearing | Fixed equal contiguous blocks | No |
| B2 | Nearest site, sector by bearing | Random every slot | No |
| T1 | Max RSRP from twin | Fixed equal blocks | Association only |
| T2 | Twin load-aware (max sum-log predicted rate) | Frequency-selective proportional fair | Yes |
| T3 | Twin load-aware | PF + twin-predicted inter-cell PRB muting | Yes |

## Swapping in NVIDIA AODT

Everything downstream of `DigitalTwin.trace()` only needs a `ChannelSet`:
UE positions `[U,3]`, per-PRB channel power `H2[U,R,K]`, LOS flags `[U,R]` and RU geometry.
To run the same study on AODT, export the CFRs from AODT's results database for each
RU-UE link, sample them at the PRB centre frequencies, and build a `ChannelSet` from them.
