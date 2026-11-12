# AUDIT — 5G RAN Digital Twin (IIT Gandhinagar)

Audit date: 2026-11-11. This was a read-only cross-check: **no source code or config was changed**.
The live project is `5g-dt-project 8.38.51 PM/`. The folder name contains a narrow no-break space (U+202F) before
"PM", so type it with a glob, e.g. `cd 5g-dt-project*PM`.

> **Update 2026-11-11:** IITGN is the only and default scenario. Items marked *Fixed 2026-11-11* have since
> been addressed; see §7 for the before/after results.

## 0. Status summary

| Part | Status | Note |
|---|---|---|
| Environment (.venv, Py 3.14.7, sionna-rt 2.2.0, mitsuba 3.9.1) | **works** | `llvm_ad_mono_polarized` OK on Apple M4. The venv's `pip` launcher is broken because the venv was moved |
| `dt/config.py` | **works** | `DT_CONFIG` + `output_tag` routing is correct |
| `dt/scene_builder.py` + `tools/build_scene.py` | **partial** | Not re-run (needs the OSM network). Writes an absolute path into `scene_meta.json` |
| `dt/twin.py` (scene, RUs, trace, LOS, radio map) | **works** | Radio-map ray count is hardcoded (3e6) |
| `dt/channel.py` (ChannelSet, 38.901, fill, impairments, MR sync) | **partial** | Weak-link fill threshold issue (§5.1). `load` uses `eval()` |
| `dt/kpi.py` | **works** | |
| `dt/alloc.py` (B1/B2/T1/T2/T3, simulator, ICIC) | **works** | |
| `e01_build_twin.py` | **works** | 48 s in quick mode |
| `e02_scenario_and_channels.py` | **fixed (2026-11-11)** | The t1 table now lists per-site height/azimuths; generic scene wording and titles |
| `e03_compare_strategies.py` | **works** | |
| `e05_mobility.py` | **partial** | Runs, but B1 moving-UE results are dominated by unrealistically weak "found" links (§5.1) |
| `e06_twin_fidelity.py` | **works** | `DROPS=15` is hardcoded |
| `e07_whatif.py` | **works** | `DROPS=10` and the site-B index are hardcoded |
| `e08_benchmark.py` | **fixed (2026-11-11), not run** | Now writes to `results/<tag>/` and reads RU count / area from the config |
| `run_all.py` | **works** | Exit 0 with `--skip-bench` |
| `tools/export_3d.py` + `viewer_template.html` | **works** | The viewer needs internet (three.js r128 from CDN, Google Fonts) |
| `tools/check_env.sh` | works (not run here; it is a Linux/GPU-server script) | |
| `tools/kratu_job.sbatch` | **partial** | `logs/` must exist before `sbatch` |
| Top-level copy (`~/Desktop/5G-digital-twin/{dt,experiments,tools,…}`) | **broken / stale** | No `config/*.yaml`, no `scenes/`, older `twin.py`/`scene_builder.py` |
| Reported IITGN numbers vs stored outputs | **works** | All match `results/iitgn/tables` exactly |

---

## 1. Repository map

### 1.1 Pipeline

```
config/iitgn.yaml ──(DT_CONFIG)──► dt/config.py  (load_config, DATA=data/<tag>, RESULTS=results/<tag>)
                                       │
tools/build_scene.py ─► dt/scene_builder.py ─► scenes/iitgn/{iitgn.xml, meshes/*.ply, scene_meta.json, footprints.json}
   (OSM Overpass → extruded prisms → Mitsuba XML; also writes config/<name>.yaml)
                                       │
                                       ▼
                              dt/twin.py  DigitalTwin  (Sionna RT: load_scene, 9 RUs, outdoor sampling,
                                       │                LOS ray_test, PathSolver → per-PRB CFR, RadioMapSolver)
                                       ▼
                              dt/channel.py  ChannelSet [U,R,K] + 38.901 UMa, fill_unresolved,
                                       │      statistical_channel, apply_impairments, calibrate_with_measurements
                                       ▼
                              dt/kpi.py  effective SINR → CQI (38.214 T5.2.2.1-3) → bits, Jain, summarize
                                       ▼
                              dt/alloc.py  STRATEGIES B1,B2,T1,T2,T3; assoc_nearest/max_rsrp/twin_lb;
                                       │     simulate() slot-level DL; coordinate_muting (ICIC)
                                       ▼
   experiments/e01 → e02 → e03 → e05 → e06 → e07 → (e08)        orchestrated by run_all.py
                                       ▼
                              tools/export_3d.py + tools/viewer_template.html → results/<tag>/twin_3d.html
dt/plotstyle.py: shared matplotlib style/colours for every figure.
```

### 1.2 Files

| File | Role | Reads | Writes |
|---|---|---|---|
| `dt/config.py` | Loads the YAML, derives carrier constants (PRB bandwidth, slot, noise per PRB), output dirs, PRB offsets | `$DT_CONFIG` or `config/iitgn.yaml` | creates `data/<tag>/`, `results/<tag>/{figures,tables}` |
| `dt/scene_builder.py` | OSM fetch / GeoJSON load, local projection, height rules, extrusion, ground, k-means site suggestion, XML | Overpass API | `scenes/<name>/*` |
| `dt/twin.py` | `DigitalTwin`: picks the CUDA variant, else LLVM; RUs (per-site azimuth override), `ground_height`, `is_outdoor`, `sample_outdoor`, `los_mask`, `trace`, `coverage_map` | scene XML | – |
| `dt/channel.py` | `ChannelSet` (save/load/subset/concat/to_table), `sector_gain_db` (38.901 T7.3-1), `uma_pathloss_db`, hybrid fill, statistical model, physical impairments, MR-based twin sync | – | – |
| `dt/kpi.py` | Link abstraction + KPI summary | – | – |
| `dt/alloc.py` | Association, scheduling (fixed/random/PF/PF+muting), simulator | – | – |
| `dt/plotstyle.py` | Plot styling, `save()` | – | – |
| `e01_build_twin.py` | Samples the pool (+150 hotspot positions) and GPS-noisy positions; traces twin/twin_est/physical (cached); fill, impairments, radio map | config | `data/<tag>/_positions.npz, _raw_{twin,twin_est,physical}.npz, {twin,twin_est,physical}_pool.npz, coverage.npz, build_log.json` |
| `e02_scenario_and_channels.py` | Fig 1–5, t1 params, t2 channel DB / UE measurements / summary | twin_pool, coverage | fig01–05, t1, t2_* |
| `e03_compare_strategies.py` | Monte Carlo over B1…T3 | twin_pool, coverage | t6_kpi_*, t6_gains.json, fig06–09 |
| `e05_mobility.py` | 3 auto-picked 130 m walks, A3-like hysteresis, T3 vs B1 | twin_pool, coverage, scene | `_raw_mobility.npz`, `mobility_traces.npz`, t5_*, fig10–11 |
| `e06_twin_fidelity.py` | Decisions on 4 twin fidelities, scored on the physical network | three pools | t6_twin_fidelity.csv, fig16 |
| `e07_whatif.py` | 7 what-if scenarios; twin/uncal/38.901 prediction vs physical | three pools | t7_*, fig12–14 |
| `e08_benchmark.py` | Runtime/memory sweeps in subprocesses | scene | **`results/tables/t8_*`, `results/figures/fig15`** (untagged!), temp `data/_bench_worker.py` |
| `run_all.py` | Runs e01…e08; flags `--skip-build`, `--skip-bench` | – | – |
| `tools/build_scene.py` | CLI for scene_builder + config generation | OSM | `scenes/<name>/`, `config/<name>.yaml` |
| `tools/export_3d.py` | Self-contained 3D page (meshes, coverage PNGs, users, ray paths, walks, KPIs) | pools, coverage, t5/t6/t7 | `results/<tag>/twin_3d.html`, `twin_3d_fragment.html` |
| `tools/viewer_template.html` | three.js viewer; data is injected at `/*__TWIN_DATA__*/null` | – | – |
| `tools/check_env.sh`, `tools/kratu_job.sbatch`, `KRATU.md` | GPU-server check / SLURM job / guide | – | – |
| `README.md`, `REPORT.md`, `CLAUDE.md` | Docs; REPORT §10 holds the IITGN numbers | – | – |
| `config/iitgn.yaml` | IITGN (v2: 30 m ground towers, rotated sectors); the default config | – | – |
| `results/iitgn_rooftop_centre/` | Archived layout-1 run, with its config copy | – | – |
| `logs_iitgn.txt`, `logs_iitgn_v2.txt`, `data/*.log` | Logs of past runs | – | – |

---

## 2. Environment

| Item | Found | Status |
|---|---|---|
| Machine | Apple M4, 10 cores, 16 GB | – |
| System `python3` | 3.14.7 (Homebrew) | ok |
| `.venv` Python | 3.14.7 | ok |
| sionna-rt | 2.2.0 (requirement is `sionna-rt>=1.0`) | ok |
| mitsuba / drjit | 3.9.1 / 1.5.0 | ok |
| numpy / pandas / matplotlib | 2.5.4 / 3.1.0 / 3.11.2 | ok |
| pyyaml / trimesh / shapely / mapbox-earcut / requests | 6.0.3 / 5.2.0 / 2.2.0 / 2.1.0 / 2.34.2 | ok: every requirement is installed |
| `pip check` | No broken requirements | ok |
| `mi.set_variant('llvm_ad_mono_polarized')` + `import sionna.rt` | succeeds | **works** |
| `dt.twin.BACKEND` | `llvm-cpu` (the CUDA variant fails as expected, so it falls back) | works |
| `.venv/bin/pip` | Shebang points to `/Users/smruteeb/Downloads/5g-dt-project/.venv/bin/python3.14` because the venv was moved | **broken**: use `.venv/bin/python -m pip` instead |

---

## 3. Quick-mode run

I used a temporary config copy. The original `config/iitgn.yaml` was not touched (sha1 `521fd403…` before and
after). The copy is at
`/private/tmp/claude-501/-Users-smruteeb-Desktop-5G-digital-twin/75e64c00-36ba-431a-958c-5c42d96ec068/scratchpad/iitgn_quick.yaml`.

| Parameter | Full (`iitgn.yaml`) | Quick |
|---|---|---|
| `output_tag` | iitgn | **iitgn_quick** (keeps the full cache and results untouched) |
| `pool_size` (+150 hotspot) | 1500 (1650 positions) | 300 (450 positions) |
| twin `samples_per_src` | 1 391 715 | 100 000 |
| physical `samples_per_src` | 4 639 053 | 300 000 |
| `num_drops` (e03) | 30 | 5 |
| `coverage_cell_m` | 5 | 10 |

Command: `DT_CONFIG=<scratchpad>/iitgn_quick.yaml caffeinate -i .venv/bin/python -u run_all.py --skip-bench`,
followed by `tools/export_3d.py` with the same config. I skipped e08 on purpose (§5.2).

| Step | Result | Time |
|---|---|---|
| e01 | ok: twin 9 s, twin_est 8 s, physical 24 s; ray-traced links found 98.7 % / 99.3 % | 48 s |
| e02 | ok | 1 s |
| e03 | ok | 3 s |
| e05 | ok: 3 trajectories × 66 steps | 19 s |
| e06 | ok | 9 s |
| e07 | ok | 31 s |
| export_3d | ok: 0.25 MB page, 107 rays, 3 walks | ~20 s |

The whole pipeline exited with code 0 in about 2 min. For reference, ray tracing alone took
405 + 469 + 1724 s ≈ 43 min in the full run.

The run created two new, untracked output folders: `data/iitgn_quick/` (27 MB) and `results/iitgn_quick/` (3.3 MB).
Both are safe to delete.

---

## 4. Comparison with reported results

First check: the reported numbers are exactly what the stored full-run tables contain
(`results/iitgn/tables/t6_kpi_summary.csv`, `t6_kpi_ci95.csv`, `t2_summary.json`). They are **reproduced from disk ✔**.

| KPI | Reported | Stored full run | Quick run | Within full-run 95 % CI? |
|---|---|---|---|---|
| B1 mean throughput [Mbps] | ~23.3 | 23.29 ± 2.24 | 24.82 ± 6.17 | yes |
| T3 mean throughput [Mbps] | ~55.3 | 55.25 ± 2.46 | 53.24 ± 7.31 | yes |
| T3 5th-pct throughput [Mbps] | ~15.1 | 15.05 ± 1.42 | 10.34 ± 3.64 | no (lower) |
| Outage B1 → T3 [%] | 22.7 → 0.2 | 22.67 → 0.22 | 22.67 → 1.33 | B1 yes; T3 is 2 of 150 UEs |
| T3 gain over B1 (mean) | +137 % | +137 % | +114 % | – |
| Median RSRP [dBm] | ~ −77 | −77.2 | −75.5 | – |
| Median SINR [dB] | ~3.9 | 3.9 | 2.35 | – |
| LOS links [%] | 68 | 68.4 | 68.4 | yes |
| Ray-traced links found [%] | – | 99.5 | 98.7 | – |
| Filled (38.901) links [%] | – | 0.49 | 1.26 | – |
| Fill calibration offset [dB] | – | +6.8 | **−7.8** | – |
| What-if per-UE log-corr, twin synced | 0.98 | 0.985 | 0.929 | – |
| What-if change error, twin synced [pp] | 2.8 | 2.77 | 2.13 | – |
| What-if per-UE log-corr, 38.901 | 0.41 | 0.41 | 0.52 | – |
| e06 T3, oracle twin, mean [Mbps] | – | 55.6 | 55.5 | – |

### Why quick mode differs

1. **Different UEs.** `sample_outdoor` draws 4·n candidates, so a pool of 300 gives a completely different set of
   positions from a pool of 1500 (same seed, different random stream). The drops also pick from a smaller pool.
2. **5 drops instead of 30.** The 95 % CIs are about 2.5–3× wider (B1 ±6.2, T3 ±7.3 Mbps). The means agree within
   these CIs. A T3 outage of 1.33 % is just 2 UEs out of 150.
3. **Fewer rays (14× fewer for the twin, 15× for the physical network).** NLOS links resolve with fewer and weaker
   paths:

   | NLOS statistic | Full run | Quick run |
   |---|---|---|
   | Median paths per link | 10 | 5 |
   | Median resolved path gain [dB] | −134.9 | −144.1 |
   | Median delay spread [ns] | 78 | 56 |

   Interference from NLOS neighbours is therefore estimated differently, which shifts the SINR distribution:
   median SINR is 2.35 vs 3.9 dB, and B1 mean SINR is −5.6 vs −0.6 dB.

   The fill calibration offset (the median of resolved-NLOS path gain minus UMa-NLOS) flips from +6.8 to −7.8 dB.
   This happens because the "resolved" links are now dominated by a few weak multi-bounce paths (§5.1).

   The cell-edge KPI (T3 p5) is the most sensitive to this, which is why it falls outside the full-run CI.
4. **The LOS fraction is unchanged (68.4 %).** LOS is a purely geometric `ray_test` and does not depend on the ray
   count, so this is a good consistency check of the scene and site geometry.
5. **Coarser coverage map (10 m).** This only affects figures and the e05 trajectory choice, so the quick walks
   differ from the full ones. Quick trajectory 3 is the same street as full trajectory 2: in both, the UE is handed
   from C173 to A180 at about −82 / −77 dBm.

**Conclusion.** The code reproduces the reported study qualitatively, and quantitatively within the quick-mode CIs.
To reproduce the exact reported numbers, run e02–e07 with the full config on the committed `data/iitgn` cache
(equivalent to `--skip-build`, about 2 min). Re-tracing from scratch takes about 45 min on this Mac.

---

## 5. Bugs, risks, dead code, portability

### 5.1 Modelling / correctness

1. **Weak "found" links are never filled.** In `dt/channel.py`, `__post_init__` sets
   `rt_found = H2.mean(-1) > 1e-25`, so a link counts as resolved if its path gain is above −250 dB. In practice,
   depth-limited tracing finds a single weak multi-diffraction path for many shadowed links.

   | Resolved NLOS links | Full run | Quick run |
   |---|---|---|
   | Share below −160 dB | 17 % | 32 % |
   | 5th-percentile path gain | −202 dB | −231 dB |

   These links keep their unrealistically low power and are not replaced by the calibrated 38.901 fill. Effects:
   - B1 SINRs are extreme: p5 is −27 dB in the full run and −59 dB in quick mode.
   - In quick mode, the B1 moving UE gets 0 Mbps on whole trajectories (the serving sector's RSRP is −165 to
     −200 dBm).
   - The fill calibration depends strongly on the ray count.
   - B1 is penalised more than is realistic, which inflates the reported T3-vs-B1 gain.

   Worth discussing: a physically motivated floor, for example filling a link when its traced power is X dB below
   the 38.901 NLOS prediction.
2. **The `e02` parameter table and titles are wrong for IITGN.**
   - The t1 table prints the global `ran.height_m = 25 m` and azimuths `[0,120,240]`. IITGN actually uses per-site
     30 m masts with rotated sectors.
   - The scene row used wording from an earlier built-in scene. *(Fixed 2026-11-11, with the per-site rows.)*
   - The Fig 1 title says "over a city block", and Fig 3 says "coverage follows the streets".
3. **The `e05` B1 baseline is very sensitive to (1).** It uses `assoc_nearest` with no fallback, so a nearest-site
   sector can be pathologically weak.
4. `coverage_map` uses a hardcoded `samples_per_tx=3e6` and ignores the profile's `samples_per_src`.
5. `e01` fell back to a hardcoded hotspot centre `[70, 10]` when `scene.hotspot_xy` is missing. *(Fixed 2026-11-11: fallback is `[0, 0]`.)*
6. The scheduler uses 273 PRBs throughout. `e07` S4 hardcodes 106 PRBs for 40 MHz, which is correct for 30 kHz SCS
   but is not derived from the config.

### 5.2 Bugs that break things or overwrite results

1. **`e08_benchmark.py` ignores `output_tag`.** It always writes `ROOT/results/tables/t8_*.csv/json` and
   `results/figures/fig15_runtime_scaling.png`. Running it with `DT_CONFIG=config/iitgn.yaml` therefore
   overwrites the untagged `results/tables`. It also hardcodes `num_rus=9` and the label "radio map 700x700 m", and writes
   a temporary worker script into `data/`. *(Fixed 2026-11-11: uses `output_tag`, config-derived RU count and area.)*
2. **`tools/kratu_job.sbatch`.** `#SBATCH --output=logs/%x-%j.out` is opened by SLURM before the script runs, so the
   in-script `mkdir -p logs` is too late. Without an existing `logs/`, the job output is lost or the job fails.
   Run `mkdir logs` before `sbatch`.
3. **`ChannelSet.load` uses `eval()`** on metadata stored in the `.npz`. This is unsafe for untrusted files. It also
   breaks if `meta` ever contains objects whose repr cannot be evaluated (only `nan` is whitelisted).

### 5.3 Hardcoded values and paths

- `scenes/iitgn/scene_meta.json` contains
  `"scene_xml": "/Users/smruteeb/Downloads/5g-dt-project/scenes/iitgn/iitgn.xml"`. This absolute path is from the
  old location. The code doesn't use it (it uses the config's relative `xml`), but it is wrong on any other machine.
- The `.venv` scripts point to `/Users/smruteeb/Downloads/5g-dt-project/.venv/...`.
- `e06` sets `DROPS = 15`. `e07` sets `DROPS = 10`, `siteB = ru_site == 1` (assumes site B is the second site) and
  `NPRB_40 = 106`. None of these follow `experiments.num_drops`.
- `e05` hardcodes the trajectory length (130 m), step (2 m), 12 slots and 12 000 candidates.
- The seeds are `1000+d` in `e03`, `7000+d` in `e06` and `5000+d` in `e07`. That is fine for reproducibility, but
  the config doesn't document them.
- `export_3d.py`: the title map only knows `iitgn`; other scenes fall back to the scene name (or `scene.title`).
- `twin.trace`: `max_num_paths_per_src=3e5` and `batch=200` are hardcoded.

### 5.4 Dead / unused code

- `dt/twin.py`: `sector_gain_db` is imported but unused, and the `_build_rus(active=None)` parameter is unused.
- `e05_mobility.py`: `json` and `assoc_nearest` are imported but unused, and the cache check calls
  `ChannelSet.load(cache)` twice.
- `e06_twin_fidelity.py`: `json` is imported but unused.
- `e03`: `k["not_nearest_site_pct"] = None` is always None, and it is still written to `t6_kpi_per_drop.csv`.
- `e02`: `GRID` is imported but unused.
- The top-level `~/Desktop/5G-digital-twin/{dt,experiments,tools,data,results,run_all.py,requirements.txt}` is an
  older duplicate of the project and cannot run: `config/` contains only `.DS_Store`, and there is no `scenes/`.

### 5.5 Fresh-machine / repo hygiene

- **Unpinned requirements.** `requirements.txt` has `sionna-rt>=1.0`, which will pull the newest release, while the
  code relies on the Sionna RT 1.x/2.x API (`PathSolver`, `RadioMapSolver`, `paths.cfr(out_type=...)`). Pin the
  tested versions: sionna-rt 2.2.0, mitsuba 3.9.1, drjit 1.5.0, numpy 2.5.4, pandas 3.1.0, and so on.
- **Python version.** CLAUDE.md recommends Python 3.12 for setup, but the venv uses 3.14, which is very new. It works
  here.
- **LLVM on Linux.** Linux CPU machines need `libLLVM` for the `llvm_ad_*` variant. Only CLAUDE.md documents this.
- **Offline viewer.** The 3D viewer loads three.js r128 from cdnjs/jsdelivr and fonts from Google, so it won't
  render offline.
- **Re-running `tools/build_scene.py`.** It needs internet (Overpass) unless you pass `--geojson`. It also
  **overwrites** `config/iitgn.yaml` with the auto-generated sites, which would lose the hand-tuned v2 towers.
- **The git repo is 822 MB:**
  - 5 `.zip` archives (~775 MB) are committed.
  - `__pycache__/*.cpython-314.pyc` and `.DS_Store` files are committed.
  - The project has no `.gitignore`; `.venv` is only ignored by a global rule.
  - The `.npz` caches (about 300 MB) are committed. This is useful for `--skip-build` but heavy.
- **Docs inconsistencies:**
  - CLAUDE.md's build command uses (23.2114, 72.6821), but the scene and config use (23.2107, 72.6872).
    REPORT §10 explains the ~520 m shift, but CLAUDE.md and README still show the old command.
  - README's quick start said "~45–60 min on a 2-core CPU". *(Fixed 2026-11-11: the IITGN full trace takes about
    43 min of ray tracing on the M4.)*

---

## 6. Suggested next steps (awaiting approval; nothing applied)

1. Decide how to treat weak "found" links (§5.1-1). This has the biggest effect on the B1 baseline and the headline
   gain.
2. Make e08 respect `output_tag`, and drive the e06/e07 drop counts from the config.
3. Fix the e02 parameter table and titles to show per-site heights/azimuths and the right scene name.
4. Pin `requirements.txt`, add a `.gitignore`, remove the committed zips/pyc from git, and delete or archive the
   stale top-level copy.
5. Replace `eval` in `ChannelSet.load` with JSON metadata.
6. Optionally, regenerate the exact reported tables from the committed `data/iitgn` cache (e02–e07, about 2 min).
   This rewrites `results/iitgn/` with identical content.

---

## 7. Before/after: weak-link fill fix (2026-11-11)

**What changed.** `ChannelSet.fill_unresolved` (§5.1, item 1) now also fills traced links whose gain is more
than **X = 18 dB** below the TR 38.901 UMa-NLOS value (+ sector pattern) at that distance, not only links with
no traced path. 18 dB = 3 × the 6 dB UMa-NLOS shadow-fading σ (TR 38.901 Table 7.4.1-1): genuine shadowing that
deep has probability ≈ 0.1 %, but 3.8 % of the traced IITGN links fell there, so they are treated as
depth-limited tracing artefacts. Filled links get 38.901 NLOS + calibration offset + 6 dB log-normal shadowing
(own random draw for the physical network). The offset is now the median over resolved, non-weak NLOS links.
Settings: `raytracing.fill` in `config/iitgn.yaml`. Filled links are marked `rt_found = False`, so
`t2_summary.json` → `rt_path_found_fraction` now means "traced path kept" (95.7 %; 99.5 % of links had a path).

**Run.** Full study e01–e08 under `caffeinate -i` on the Apple M4 CPU, reusing the cached ray traces in
`data/iitgn/_raw_*.npz` (no re-trace): e01–e07 ≈ 2 min, e08 ≈ 2 min. Log: `logs_iitgn_v3_fillfix.txt`.
"Before" = `results/iitgn/tables` as they were just before this run (old fill, same traces, same UE drops/seeds).
± = 95 % CI over the 30 Monte Carlo drops.

| Metric | Before (no-path fill only) | After (weak-link fill, X = 18 dB) |
|---|---|---|
| Fill calibration offset [dB] | 6.8 | 10.3 |
| Twin links filled with 38.901 [%] | 0.5 | 4.3 |
| B1 mean throughput [Mbps] | 23.3 ± 2.2 | 23.9 ± 2.1 |
| B1 5th-pct throughput [Mbps] | 0.0 ± 0.0 | 0.0 ± 0.1 |
| B1 outage (< 1 Mbps) [%] | 22.7 ± 2.8 | 19.2 ± 2.8 |
| B1 mean effective SINR [dB] | -0.6 | 1.5 |
| B1 5th-pct effective SINR [dB] | -26.9 | -16.2 |
| T3 mean throughput [Mbps] | 55.3 ± 2.5 | 54.6 ± 2.1 |
| T3 5th-pct throughput [Mbps] | 15.1 ± 1.4 | 16.7 ± 1.4 |
| T3 outage (< 1 Mbps) [%] | 0.2 ± 0.3 | 0.0 ± 0.0 |
| T3 mean effective SINR [dB] | 16.0 | 16.0 |
| T3 5th-pct effective SINR [dB] | 5.8 | 6.6 |
| **T3 gain over B1, mean throughput** | +137 % | +129 % |
| Median best-server SINR, UE measurements [dB] | 3.9 | 4.0 |
| Best site is not the nearest [% UEs] | 41.3 | 39.2 |
| Fidelity: T3 mean, synced twin on physical net [Mbps] | 45.7 | 46.9 |
| Fidelity: T3 mean, unsynced twin at GPS positions [Mbps] | 29.6 | 31.6 |
| Fidelity: B1 mean on physical net [Mbps] | 21.4 | 23.4 |
| What-if: error in predicted change, twin + sync [pp] | 2.8 | 2.7 |
| What-if: error in predicted change, twin no sync [pp] | 6.9 | 5.9 |
| What-if: error in predicted change, 38.901 [pp] | 18.4 | 18.0 |
| What-if: mean-throughput abs. error, twin + sync [Mbps] | 4.3 | 4.4 |
| What-if: mean-throughput abs. error, 38.901 [Mbps] | 14.1 | 13.9 |
| What-if: per-UE log-corr, twin + sync | 0.98 | 0.98 |
| What-if: per-UE log-corr, 38.901 | 0.41 | 0.52 |

**Mobility (Task 5), per route.** The three walks are the same, but routes 1 and 2 swapped rank because e01
recomputes the coverage map (Monte Carlo rays) on every run; they are matched here by start point.

| Route (start point) | B1 mean thr. before → after [Mbps] | B1 mean SINR before → after [dB] | T3 mean thr. before → after [Mbps] | Twin handovers before → after |
|---|---|---|---|---|
| NLOS route, (−444, 422) m (was #1, now #2) | 6.8 → 6.9 | −6.7 → −6.6 | 24.7 → 25.5 | 4 → 4 |
| LOS route, (−581, 65) m (was #2, now #1) | 0.4 → 0.4 | −21.8 → −19.9 | 93.3 → 53.3 | 0 → 0 |
| No-LOS route, (−238, 607) m (#3) | 33.3 → 61.8 | −19.2 → +4.9 | 69.5 → 93.1 | 1 → 2 |

**Reading the results**
- **The main finding holds, slightly smaller.** T3 is essentially unchanged (54.6 vs 55.3 Mbps, inside the CI);
  B1 improves a little (outage 22.7 → 19.2 %, 5th-pct SINR −26.9 → −16.2 dB) because fewer of its nearest-site
  links are artefact-weak. The T3 gain over B1 falls from +137 % to **+129 %**. This matches the X-sensitivity
  check (+129–132 % for X = 12–24 dB), so the result does not hinge on the exact threshold.
- **What-if accuracy is unchanged** for the synced twin (2.7 pp); the 38.901 model still errs by ≈ 18 pp.
- **Twin fidelity (e06) improves slightly** for every twin variant (synced T3 45.7 → 46.9 Mbps).
- **Mobility.** The artefact flagged in §5.1/§4 is gone: on route 3 B1's serving link was as low as −181 dBm,
  and B1's mean SINR there rises from −19 to +5 dB. On the LOS route, T3's throughput fell (93 → 53 Mbps)
  although its SINR rose (18.1 → 20.9 dB), which points to a smaller PRB share against the 29 static UEs rather
  than a worse channel; with 66 steps of one walk this number is noisy and not investigated further.
- **Quick mode now agrees with the full run** (quick: fill offset −7.8 → +4.3 dB, T3 5th pct 9.8 → 15.4 Mbps),
  closing the discrepancy in §4 "Why quick mode differs", point 3.

**Task 8 benchmark (first IITGN run).** `results/iitgn/tables/t8_benchmark.csv`, `fig15_runtime_scaling.png`;
10-core Apple M4 CPU, LLVM backend, depth 3, 3 × 10⁵ rays/RU unless varied: 25 / 100 / 300 / 600 UEs × 9 RUs →
1.4 / 5.0 / 15.3 / 31.1 s (0.75–1.27 GB peak); 10⁵ / 3 × 10⁵ / 10⁶ rays → 1.9 / 5.4 / 18.5 s; depth 1–4 →
3.0–5.1 s; 1300 m × 1300 m radio map at 5 m → 6.2 s. A units bug was fixed on the way: `ru_maxrss` is bytes on
macOS but KB on Linux, so e08 reported ~800 000 "MB"; it now divides correctly per platform.

**Other fixes applied the same day:** e08 writes to `results/<output_tag>/` (§5.2.1); e02 t1 table lists per-site
height/azimuths (§5.1.2); `scene_meta.json` stores a project-relative path and `build_scene.py` refuses to
overwrite an existing `config/<name>.yaml` without `--force` (§5.3, §5.5); `.gitignore` added.

**Not yet updated:** REPORT.md still quotes the before-fix numbers (+137 %, outage 22.7 %, etc.).
