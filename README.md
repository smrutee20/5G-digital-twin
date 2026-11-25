# 5G RAN Digital Twin for Channel-Aware Resource Allocation and Network What-If Analysis

## Live demo

**https://smrutee20.github.io/5G-digital-twin/**: the twin in the browser, nothing to install.

- **Works there:** Twin & 5G core (the walking person and every 5G message, with the study's handover rule of 3 dB /
  2 steps), Strategies and What-if. All of their results are precomputed and built into the page.
- **Needs the server on your computer:** Configure (antenna settings, gNB positions, UE placement) and handover rules
  other than 3 dB / 2 steps. Both re-run the simulation. Start the server with Docker (below); the live site finds it
  at http://localhost:8765 and uses it. Without it, the Configure tab shows the `docker run` command.

The site is `docs/index.html`, made by `.venv/bin/python tools/build_site.py` (runs `run.py`, then copies `twin.html`
with `STATIC_SITE = true`: the page then calls no server except http://localhost:8765). GitHub Pages: Settings →
Pages → branch `main`, folder `/docs`.

## Run with Docker

The whole twin, including Configure, on your own computer (Windows, macOS on Intel or Apple silicon, Linux). No
Python and no GPU are needed: Sionna RT runs on the CPU.

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and start it.
2. Run:
   ```
   docker run -p 8765:8765 ghcr.io/smrutee20/5g-digital-twin
   ```
3. Open http://localhost:8765 (or reload https://smrutee20.github.io/5G-digital-twin/, which then uses it).
   Stop with Ctrl+C.

| | Live site, no Docker | Live site + Docker, or http://localhost:8765 |
|---|---|---|
| Twin & 5G core (study rule 3 dB / 2 steps), Strategies, What-if | yes | yes |
| Other handover rules | no | yes |
| Configure (antennas, gNB positions, UEs, coverage map) | shows the `docker run` command | yes |

- **Size:** about 280 MB to download, 1.3 GB on disk (most of it is Mitsuba, Dr.Jit and LLVM).
- **First run:** the download, then the server is ready in about 5 s and pre-computes the default coverage map
  (about 2 s on an Apple M4; give a slower laptop about a minute). A Configure run at the default 1e6 rays then takes
  a few seconds (about 20 s for 200 UEs on the M4). Repeated settings come from the cache.
- **Limits** (the server can be reached by any page on your computer): at most 1e6 rays per sector, 50 UEs per
  request, one simulation at a time (another request gets "try again"). Raise them with `-e TWIN_MAX_RAYS=4e6` or
  `-e TWIN_MAX_UES=200` on `docker run`.
- **Safari:** it may block an https page from calling http://localhost. Open http://localhost:8765 instead.
- **Check it:** http://localhost:8765/health. Run the Configure tests inside it:
  `docker exec <container> python server/test_configure.py`.
- **Build it yourself:** `docker build -t 5g-digital-twin .`. `.github/workflows/docker.yml` builds linux/amd64 and
  linux/arm64 on every push to `main` and pushes `ghcr.io/smrutee20/5g-digital-twin:latest`. The image's page is
  `viewer.html` + the data inside `docs/index.html` (`tools/build_site.py --twin-only`), so a local build and the
  CI build show the same twin as the website. (`data/study_v2/` is not in the repository.)
- **One-time step after the first CI push:** a new GitHub package is private. Make it public: github.com/smrutee20 →
  Packages → 5g-digital-twin → Package settings → Change visibility → Public. (`GITHUB_TOKEN` cannot do this.)

## 1. Problem Statement

Evaluating alternative channel/resource allocations directly on a physical 5G network can be expensive and difficult to reproduce because performance depends on UE locations, propagation conditions and traffic load. A digital twin can provide a physics-aware representation of the radio environment and allow alternative allocations and network configurations to be evaluated before applying them to the network.


1. Deploy or use any of the digital-twin framework for eg. NVIDIA AODT and generate a scenario containing a RUs/gNBs and UEs and understand the available radio/environment configuration parameters.
2. Obtain site-specific channel information and relevant RAN measurements for different UE locations and links.
3. Define a simple baseline resource/channel-allocation strategy, such as fixed or random allocation.
4. Implement a channel-aware allocation strategy that uses digital-twin-derived channel information to select an appropriate channel/resource or serving radio for each UE.
5. Move or reconfigure UEs and evaluate how changes in the physical environment affect received signal/channel conditions and the selected allocation.
6. Compare baseline and twin-assisted strategies using relevant 5G KPIs such as SINR/channel quality, throughput, interference and resource utilization where available.
7. Use the same digital twin for a small what-if analysis, such as increasing UE density, changing UE positions or modifying resource allocation, and predict the resulting network performance before applying the configuration.
8. Document the capabilities, computational requirements and limitations of the chosen digital-twin framework as a 5G/6G network digital-twin platform and identify the research problems for which it is suitable.


---

## 2. What We Implemented

To address the above requirements, we developed a ray-traced digital twin of the IIT Gandhinagar campus. The implementation combines a realistic campus environment, 5G radio propagation modelling, resource allocation strategies, user mobility simulation, and 5G core network signalling.

Instead of deploying a physical 5G network, we used Sionna RT to model radio propagation within the campus environment and evaluate different network configurations through simulation.

The digital twin consists of three 5G sites, each containing three sectors, operating at 3.5 GHz. The campus environment includes 74 buildings obtained from OpenStreetMap.

The implementation is divided into the following stages.

### 2.1 Campus Environment and 5G Network Setup

We first created a 3D representation of the IIT Gandhinagar campus and placed the 5G infrastructure within it.

The network consists of:
- 3 base station sites.
- 3 sectors per site.
- 9 sectors in total.
- Operating frequency of 3.5 GHz.
- 100 simulated User Equipments (UEs) per network placement.

The campus geometry was obtained from OpenStreetMap and loaded into Sionna RT to create the environment for radio propagation simulation.

The network configuration, including site positions, sector parameters, handover conditions and 5G identities, is maintained in `config.py`.

The campus scene and placement of the network sectors are implemented in `twin/scene.py`.

### 2.2 Ray Tracing and Radio Channel Measurements

After constructing the campus environment, we used Sionna RT to study how radio signals travel between the base station sectors and mobile users.

We generated 20 random network placements, with 100 UEs in each placement.

For every UE and sector combination, the ray tracer estimates the radio propagation characteristics, including:

- **RSRP (Reference Signal Received Power):** The strength of the signal received by a UE from a particular sector.
- **SINR (Signal-to-Interference-plus-Noise Ratio):** How strong the desired signal is compared with unwanted interference and background noise.
- **Line of Sight (LOS):** Whether there is a direct path between the transmitter and receiver.
- **Path Loss:** How much signal power is lost while travelling from the base station to the UE.

These measurements are stored in the `data/` directory and used by the resource allocation strategies.

The radio calculations, including transmission power, noise, SINR and throughput estimation, are implemented in `twin/radio.py`.

### 2.3 Baseline Resource Allocation Strategies

To evaluate the benefit of using channel information from the digital twin, we implemented two baseline strategies.

**Baseline 1 (B1): Nearest Site with Fixed PRB Allocation**

Each UE connects to its nearest base station. Radio resources are assigned using fixed PRB blocks.

This strategy does not consider the actual channel quality between a UE and the available sectors.

**Baseline 2 (B2): Nearest Site with Random PRB Allocation**

Each UE again connects to its nearest base station, but the PRBs are assigned randomly.

This allows us to compare fixed resource allocation against a simple random allocation approach.

Each UE is assumed to require 12 Physical Resource Blocks (PRBs).

These two strategies serve as reference points for evaluating the digital-twin-driven approach.

### 2.4 Channel-Aware Resource Allocation Using the Digital Twin

We then implemented a resource allocation strategy that uses the radio measurements obtained from ray tracing.

Unlike the two baseline approaches, this strategy considers the actual radio propagation conditions between UEs and the available sectors.

The approach works as follows:

1. For each UE, examine the ray-traced signal measurements from the available sectors.
2. Identify the sector providing the strongest received signal.
3. Consider interference between neighbouring sectors.
4. Assign different PRBs to sectors expected to cause strong interference with one another.

This allows the network to make resource allocation decisions using information about the actual simulated radio environment rather than relying only on geographical distance or random assignment.

The allocation strategies are implemented in `twin/allocation.py`.

### 2.5 Performance Comparison of Allocation Strategies

After implementing all three strategies, we evaluated their performance across the 20 randomly generated placements.

We considered four network performance metrics:

- **SINR:** Measures the quality of the received signal compared with interference and noise.
- **Throughput:** Measures how much data a user can receive per second.
- **Interference:** Measures the unwanted radio signal affecting users.
- **PRB Utilization:** Measures how radio resources are being allocated across the network.

The results are calculated across the different placements and presented using mean values and 95% confidence intervals.

The comparison is implemented in `tasks/task6_compare.py`, which generates result tables and plots in the `results/` directory.

### 2.6 UE Mobility and Handover Simulation

We also studied how the network behaves when a mobile user moves across the IIT Gandhinagar campus.

For this, we simulated three different walking routes.

As the UE moves, the radio channel conditions are evaluated again using ray tracing. The network then determines whether the UE should switch from its current serving sector to another sector.

We implemented an A3-based handover condition with:
- 3 dB handover threshold.
- Two-step time-to-trigger condition.

The simulation records the number of handovers and evaluates the throughput experienced by the moving UE under B1 and the Twin strategy.

This helps us understand whether channel-aware resource allocation can maintain better connectivity as users move through different parts of the campus.

The mobility simulation is implemented in `tasks/task5_mobility.py`.

### 2.7 5G Core Network Signalling Demonstration

Apart from radio propagation and resource allocation, we also developed a message-by-message model of important 5G core network procedures.

The demonstration follows a mobile phone as it moves along a campus route and illustrates the communication between the UE, gNBs and core network.

The following procedures are demonstrated:

- **Registration:** The process through which a UE registers with the 5G network.
- **PDU Session Establishment:** The process through which a UE establishes a data connection.
- **Xn Handover:** The transfer of a UE's connection from one gNB to another.
- **Paging:** The process through which the network attempts to reach an idle UE.

The network model is implemented in the `net/` directory. It includes the UE and gNB models, core network components, network identities and message timing.

The `run.py` script executes the network flow and generates the interactive HTML demonstration using `viewer.html`.

The `test_flows.py` script checks whether the simulated procedures follow the expected message sequence.

### 2.8 What-If Analysis and Network Configuration Changes

We used the same digital twin to investigate how changes in network conditions could affect performance.

Three hypothetical scenarios were considered:

1. **Increased UE density:** Doubling the number of UEs in the network.
2. **Site failure:** Switching off Site B and evaluating the resulting network performance.
3. **UE position changes:** Moving UEs approximately 30 metres from their original positions.

For each scenario, the digital twin predicts the expected network performance. These predictions are then compared with a new simulation that incorporates random shadowing.

The difference between the predicted and simulated mean throughput is within 0.85 Mbps.

This demonstrates how a digital twin can be used to estimate the effects of network changes before running a new simulation.

The implementation is available in `tasks/task7_whatif.py`.

### 2.9 Computational Requirements and Platform Evaluation

Finally, we evaluated the computational requirements of the digital-twin platform.

The project uses the following technologies:

| Technology | Purpose |
|---|---|
| Sionna RT 2.2.0 | Radio propagation and ray tracing |
| Mitsuba 3.9.1 | Rendering and scene processing |
| Dr.Jit 1.5.0 | Accelerated computation |
| Python 3.14.7 | Simulation and experiment execution |
| NumPy 2.5.4 | Numerical computations |
| Matplotlib 3.11.2 | Result visualization |
| three.js r128 | Interactive 3D campus visualization |
| FastAPI 0.165 + uvicorn 0.54 | Local server for the Configure tab (section 2.10) |
| OpenStreetMap | Campus building geometry |

The ray-tracing benchmark was performed on an Apple M4 CPU.

The measured computational requirements are:

- Approximately 20–30 ms per UE-sector link at 1 million rays.
- Memory consumption below 1.1 GB.

The complete experimental study takes approximately 25 minutes from scratch, including ray tracing and performance benchmarking.

The platform evaluation is implemented in `tasks/task8_platform.py`.

### 2.10 Configure: Antenna Settings and UE Placement

**A predictive digital twin of the IITGN campus 5G radio network.**

The Configure tab lets a user choose the antenna settings of every sector and place UEs on the 3D campus; the twin then
re-runs Sionna RT and shows, for each UE, the RSRP from every sector, the serving sector, the SINR and line of sight,
plus a coverage map. Unlike the other tabs, nothing here is precomputed: a small local server (`server/`) does the
ray tracing.

**Starting it**

```
.venv/bin/python -m pip install -r requirements.txt   # once (adds fastapi and uvicorn)
.venv/bin/python run.py                               # builds twin.html
.venv/bin/python -m server                            # http://127.0.0.1:8765 (or: Docker, see Run with Docker)
```

Open http://127.0.0.1:8765 and choose the **Configure** tab. (Opening `twin.html` directly also works while the server
runs.) In the tab: click the campus to add a UE, drag a UE to move it, select it and press Delete to remove it, or
place N random outdoor UEs. Change sector settings (one sector, or "apply to all" except azimuth) and UE settings, then
press **Run**.

| Endpoint | What it does |
|---|---|
| `GET /defaults` | default gNB and UE settings, the 9 sectors, ray-count choices |
| `GET /random_ues?n=20&seed=1` | n random outdoor UE positions |
| `GET /check_position?x=..&y=..` | is (x, y) inside a building? (used when a gNB is moved) |
| `POST /simulate` | sector settings + UE settings + UE list → per-UE RSRP from every sector, best beam, serving sector, SINR, LOS, and (optionally) the coverage map with its assumptions |

**Defaults (today's model)**

| | Setting | Default |
|---|---|---|
| gNB (every sector) | array | 1x1 (0.5 λ spacing for larger arrays: 4x4, 8x8, 16x16) |
| | element pattern | tr38901 (also: iso, dipole) |
| | polarization | V (also: H, cross = ±45°) |
| | transmit power | 46 dBm per sector, total over all elements |
| | height | 30 m |
| | downtilt | 8° |
| | azimuths | as in `config.py` |
| | SSB beams | 8 |
| UE | array, pattern, polarization | 1x1, iso, V (arrays 1x2, 2x2, 4x4 available) |
| | height | 1.5 m |
| | noise figure | 9 dB |
| Ray tracing | rays per sector | 1e6; 2e5 (fast) selectable; 4e6 only with `TWIN_MAX_RAYS=4e6` (limit, see Run with Docker) |
| | bounces | 3 + diffraction |
| Coverage | grid, threshold | 5 m, RSRP > −110 dBm (editable) |

With these defaults the twin reproduces the study's RSRP values (section 2.2): at 1e6 rays, at least 99.5 % of the
1 782 route links are within 0.1 dB (99.5–99.9 % in our runs) and every route point has the same serving sector. The rest differ because Sionna's
path search is not bit-for-bit repeatable: the original ray-tracing code itself varies by up to 8.5 dB on the same few
links from run to run.

**Beam model and power**

Each sector sweeps an SSB-style codebook of N fixed beams (default 8): DFT-style steering vectors spread evenly in
sin(φ) across the 120° sector; every element in a column gets the same phase, so in elevation the beam follows the
mechanical downtilt. The UE measures every beam and reports the strongest: **RSRP = best beam**, from the strongest
UE receive branch (TS 38.215). Cross-polarized arrays use the same weights on both slants (one co-phased port).
RSRP is the power of one of the 273 × 12 resource elements, as in section 2.2. SINR assumes every sector transmits on
every PRB: the serving sector's best beam against every other sector's beam-averaged power, plus noise.

The transmit power is the **total per sector, split evenly across the elements** (each beam vector has unit norm). A
larger array therefore only focuses the same power more (array gain up to 10·log10(N) in the beam direction); it never
radiates more. Scaling power with the number of elements would mix a second effect into every comparison (+24 dB for
a 16x16 array just from more amplifiers) and break the per-sector power limit. For example, at a line-of-sight UE on
the boresight of sector A60, 8x8 gives −53.1 dBm against −66.2 dBm for 1x1: +13.2 dB, the 18.1 dB ideal array gain
less the loss of the nearest of 8 beams not pointing exactly at the UE.

**Coverage and ray count**

The coverage map comes from Sionna's radio-map solver on a 5 m grid at UE height, one run per distinct beam; the
coverage % counts outdoor cells only (cells inside buildings are excluded). Every coverage number is shown with its
assumptions, e.g. "Coverage (RSRP > −110 dBm): 76.4 % of outdoor area with 1x1 tr38901 V, 46 dBm, 8° tilt, 30 m;
2e5 rays per sector". Results are cached by a hash of the settings, so a repeated configuration returns at once, and
moving one UE re-traces only that UE.

The interactive ray count (2e5) is fast but **under-counts coverage**: with too few rays, distant and diffraction-only
cells get no ray at all and count as uncovered. Measured with the default settings (RSRP > −110 dBm):

| Rays per sector | 2e5 | 5e5 | 1e6 | 2e6 | 4e6 | 8e6 |
|---|---|---|---|---|---|---|
| Coverage | 76.4 % | 86.6 % | 91.1 % | 94.3 % | 95.6 % | 96.5 % |
| Time for one map (M4 CPU) | 0.4 s | 1.4 s | 1.8 s | 3.9 s | 7.4 s | – |

At 2e5 rays 28 % of UEs can also get a different serving sector than at 1e6. Use 2e5 to explore and 1e6 or more for
numbers you report; for comparison, at 1e6 rays an 8x8 array gives 96.9 % against 91.2 % for 1x1.

**Limitations**

- Sionna's radio-map solver ignores the UE antenna array: the coverage map always assumes a single isotropic UE
  antenna. The per-UE numbers do use the chosen UE antenna; the tab says so when they differ.
- In Sionna RT 2.2 every transmitter shares one antenna array, so sectors with different array settings are traced in
  separate passes (slower when many different settings are mixed).
- Only mechanical tilt is modelled; the beams steer in azimuth only.

**Tests**: `.venv/bin/python server/test_configure.py` (about a minute) checks that the defaults reproduce today's
RSRP, that 8x8 with the codebook beats 1x1 at boresight, that the total power is the same for every array size, that
the coverage map and the per-UE trace agree (median 1.1 dB), and that repeated configurations come from the cache.

### 2.11 Twin v2: Buildings from the Campus Drawings, Lal Minar, and Trees

`scenes/iitgn_v2/` is a second version of the twin; `scenes/iitgn/` (v1, used for every result above and in the
report) is unchanged, as are all v1 results. The web page shows v2 only.

In v2:

- 9 of the buildings take their outline from IITGN's architectural drawings (academic Blocks 4–8, Firpeal hostel, the
  dining hall, the student mess, Panchayat Circle; chosen one by one in a review); the others keep their OpenStreetMap
  outline. The drawings themselves are not part of the repository.
- Heights: every building is G+3 = 4 floors × 3.5 m = 14 m, whatever its v1 height; kiosks and shops under 100 m²
  are 1 floor (3.5 m); Panchayat Circle, open seating rather than a building, is 1 m.
- Lal Minar is added next to the Block 8 canteen: its OpenStreetMap outline (way 693494161, about 12.5 m × 13 m),
  concrete like the other buildings, 24 m tall (OpenStreetMap `building:levels=6` × 4 m, estimated; OSM has no
  height tag).
- 123 trees (`scenes/iitgn_v2/trees.csv`, positions from the hostel drawing, 6 m crown and 8 m height by default).
  Trees are not ray-traced as objects: after tracing, each path loses `min(1 dB/m × length inside crowns, 20 dB)`
  (`twin/vegetation.py`). **These values are placeholders to be calibrated.**

`scenes/iitgn_v2/buildings.csv` records the outline and height source of every building.

Select the scene for the tasks with `TWIN_SCENE=v2` (results go to `data/study_v2`, `results/study_v2`); the
Configure tab computes on v2. `python tasks/task9_scene_v2.py` re-traces task 2's 2,000 UEs on v2 (same positions),
runs task 6 on v2 and writes `results/study_v2/before_after.md`:

| | v1 | v2 |
|---|---|---|
| Coverage, RSRP > −110 dBm (outdoor 5 m cells, 1e6 rays) | 91.1 % | 89.9 % (±0.1 between runs) |
| LOS to the serving sector (all UEs) | 77.3 % | 77.5 % (77.2 % also clear of tree crowns) |
| Median best-sector RSRP (UEs) | −75.0 dBm | −75.0 dBm |
| B1 / B2 / Twin: mean throughput | 6.48 / 8.67 / 10.92 Mbps | 7.07 / 9.28 / 12.15 Mbps |
| Twin: 5th-percentile throughput | 1.33 Mbps | 0.82 Mbps |
| UEs near a drawn outline, Lal Minar or a tree (112): LOS to serving sector | 64.3 % | 58.9 % (54.5 % clear of crowns) |
| Serving sector changed: near those / elsewhere | – | 32.1 % / 16.3 % |

The uniform G+3 heights change every building (most v1 heights were a 12 m default, some 20–24 m): throughput and
SINR rise for all three strategies and 16 % of UEs far from the other changes get a new serving sector (ray-tracing
noise alone is about 3 %). Near the drawn outlines, Lal Minar and the trees, LOS drops by 5–10 points. In the coverage
map, vegetation is applied along the straight line from each antenna (the radio-map solver gives no per-path
geometry); per-UE results use every path.

The 3D view (offline) shows the campus on grass, with roads and paths, the river, sports fields (the football ground
inside the red running track; the track's shape is approximated from its OpenStreetMap bounds), trees, building zones
coloured with the campus master plan's legend, Lal Minar in terracotta, and labels of the main buildings. **Show radio
heat map** switches the ground to the RSRP map (its colour bar appears only then); **Info** holds the scenario, the
v1-vs-v2 numbers and the legend. The Strategies and What-if tabs still show the study's (v1) results; the Mobility
tab walks the v2 routes of section 2.12.
`twin.html#heat=1&info=1&off=labels&cam=-336,279,120` opens a given view. Screenshots: `docs/screenshots/`.

### 2.12 A Person Walking the Campus Roads (Twin v2 Demo)

`tasks/task10_walk_v2.py` (run after task 9) gives the Mobility tab three walks along real campus roads, on twin v2.
v1's task 5 results and `data/twin.json` are not changed (the report's section 3.2 uses them).

- **Walking network:** OpenStreetMap highways = footway, path, pedestrian, service, residential, tertiary (113 ways).
  Ways are densified to 4 m; points of different ways within 3 m are joined (crossings without a shared OSM node), and
  4 dangling way ends within 8 m of another way are joined to it. 99.6 % of the network is one connected piece.
- **Routes** (shortest paths through waypoints, a point every 2 m). No route point is inside a v2 building (footprint
  and Sionna ray-cast both checked) or in water (OSM water areas, river drawn 30 m wide); the closest point to a wall
  is 5.8 / 5.8 / 6.3 m. Each route crosses a sector border on the v2 serving-sector map (1e6 rays, 5 m):

| Route | Length | Map: best sector along it | A3 handovers on the traced route (3 dB, 2 steps) | Xn |
|---|---|---|---|---|
| Hostels → Lal Minar (via the academic area) | 391 m | B225 → A180 | B225→A180 at 262 m | 1 |
| Hostels → Sports complex | 329 m | B225 → C53 | B225→C53 at 60 m, C53→A180 at 94 m, A180→C53 at 130 m | 3 |
| Academic area → Guest house | 578 m | A180 → B225 → B345 → A60 → A300 → C53 → A300 | 8 (A180→B225, B225→B345, B345→A60, A60→A300, A300→B345, B345→A300, A300→C53, C53→A300) | 6 |

- **Radio:** every point ray-traced on v2 (1e6 rays, vegetation loss); the walker's B1 and Twin throughput exactly as
  task 5 (10 placements of the other UEs, from task 9's v2 drops):

| Route | B1 mean (95 % CI) | B1 at 0 Mbps | Twin mean (95 % CI) | Twin at 0 Mbps | LOS to serving sector |
|---|---|---|---|---|---|
| Hostels → Lal Minar | 4.6 ± 2.1 Mbps | 38.3 % of steps | 12.5 ± 2.3 Mbps | 0.0 % | 99.5 % |
| Hostels → Sports complex | 3.5 ± 1.7 Mbps | 57.0 % | 12.7 ± 2.1 Mbps | 0.2 % | 89.7 % (84.8 % clear of trees) |
| Academic area → Guest house | 8.3 ± 3.5 Mbps | 10.3 % | 15.0 ± 1.9 Mbps | 0.3 % | 91.7 % |

  The guest-house walk passes the Indoor Sports Complex, where A60, A300, B345 and C53 are within a few dB of each
  other; the 3 dB / 2-step rule then hands over back and forth (A300↔B345 within 14 m, C53↔A300). A longer
  time-to-trigger or a larger offset would stop this ping-pong; the study's rule is kept unchanged.
- **5G core:** `run.py` regenerates the message timeline on these routes; it checks that every Xn handover
  (HandoverRequest) happens at exactly the step where task 10's A3 rule changes site (steps 131; 30, 47, 65;
  41, 144, 221, 228, 250, 287). Hand-overs between sectors of one site stay inside the gNB (no core messages).
- **3D:** the UE is a low-poly person (body, head, swinging legs and arm) holding a phone and facing the walking
  direction, drawn 4× real size (about 7 m tall) so it can be seen from the overview; the radio uses the phone at
  1.5 m (noted in Info). The line from the phone to the serving sector has the site's colour and flashes (thicker,
  pulsing, with a ring spreading from the person's feet) at each handover. The route is a dotted line on the road;
  **Follow phone** follows the person from behind. `twin.html#route=1&frame=337&flash=1` shows route 1's Xn
  handover with the flash held. Screenshots: `docs/screenshots/person_overview.png`, `person_handover.png`.
- **Default route and handover rule:** the page opens on Hostels → Lal Minar (one clean Xn handover). The Mobility
  tab's **Handover rule** control (A3 offset in dB, time-to-trigger in steps; the study used 3 dB / 2 steps) recomputes
  the serving sector and handovers in the browser from each route's saved ray-traced RSRP (no new ray tracing): route
  dots take the serving site's colour and rings mark handovers. The server's `POST /timeline` re-runs `run.py`'s network
  simulation for the new rule and returns the message timeline (at 3 dB / 2 steps it reproduces the embedded timeline
  exactly). Without the server the colours and counts still follow the new rule, but the messages stay at 3 dB / 2
  steps (the page says so). `twin.html#route=3&a3=6&ttt=2` opens with a given rule. On the guest-house walk, 6 dB gives
  6 handovers (5 Xn) instead of 8 (6 Xn): site B keeps the walker longer, A60 takes over later, and the last C53→A300
  goes away; the A300↔B345 handover pair beside the Indoor Sports Complex stays, because the sectors differ by more than
  6 dB there. Screenshots: `docs/screenshots/guesthouse_3db_vs_6db.png` (side by side), `guesthouse_a3_3db.png`,
  `guesthouse_a3_6db.png`.
- Saved: `data/study_v2/walk_routes.json`, `walk_traces.npz`, `walk_serving_map.npz`; `results/study_v2/task10_walk.png`,
  `task10_walk_routes_map.png`, `task10_walk_routes.csv`, `task10_walk_summary.csv`, `task10_walk_checks.md`.

### 2.13 The 5G Network Visualiser: Click to Look Inside, Live Packet Status

In the **Twin & 5G core** tab everything in the network diagram can be clicked. What it shows opens in an inspector
between the campus and the diagram (the diagram keeps its place and size, so it is never covered; in a narrow window
the inspector lies over the campus, on a phone below the diagram).

| Click | The inspector shows |
|---|---|
| A network element (UE, gNB-A/B/C, AMF, SMF, UPF, AUSF, UDM, SIDF, NSSF, Internet) | Its role; its **live state** at this point of the walk (UE: RRC_IDLE / RRC_CONNECTED, RM, CM, PDU session, serving sector and RSRP; AMF: RM and CM; SMF: session; UPF: uplink and downlink rule, tunnels, buffered packets, NAT; ...); its protocol stacks, one per interface, with the one in use now marked; the identities it holds; its messages in this flow |
| A message (the moving packet, the bottom line, any list row) | **Live packet status**: not sent yet / in flight (%) / delivered; its journey hop by hop (a NAS message crosses Uu and N2, a user packet goes UE → gNB → UPF → Internet and back); what caused it and what it triggers; for Uu, the radio link it used, from the ray-traced twin (sector, RSRP, line of sight, next best sector); its encapsulation; its fields (new identities marked); the real frame from the class capture where there is one |
| An interface label (Uu, N1, N2, N3, N4, N6, N11, SBI, Xn) | Its protocol stack, how many messages have used it so far, every message type on it |
| **Messages** (top right of the diagram) | The message list of this flow or of the whole walk; **to UE** lists every message that reaches the phone |

- The bottom line always tracks the current message: its journey, a progress bar and its status. ◀ ▶ (or the ← → keys)
  step message by message; Space plays and pauses. Clicking the moving packet pauses the walk there.
- The small light on each element shows whether it holds live state for the phone (green: yes; amber: in between, for
  example an idle phone or a paused session).
- "Caused by" and "then" come from the simulation's timing: an element handles a message 0.5 ms after it arrives
  (`config.py`), so the message that made it send the next one can be found exactly. The delays are assumptions; the
  animation is slowed down so it can be followed.
- `twin.html#route=1&frame=40&nf=AMF` opens an element, `&pkt=1` the current message, `&if=N2` an interface,
  `&list=1` the message list. Screenshots: `docs/screenshots/live_packet_to_ue.png`, `nf_panel_ue.png`,
  `nf_panel_amf.png`, `packet_view_ngap.png`, `message_list_to_ue.png`.
- Page-only changes can be published without the study data: `python tools/build_site.py --reuse-data` puts the data
  already inside `docs/index.html` into the current `viewer.html` (it also writes `twin.html` to check locally).

---

## 3. Experimental Results

We evaluated the three resource allocation strategies using 20 random network placements, each containing 100 users.

The following results show how the average user experience, connectivity of poorly served users and radio interference differ across the strategies.

### 3.1 Resource Allocation Results

| Performance Metric | B1: Fixed PRBs | B2: Random PRBs | Twin |
|---|---:|---:|---:|
| Average user throughput (Mbps) | 6.48 ± 0.50 | 8.67 ± 0.35 | **10.92 ± 0.50** |
| Throughput at the 5th percentile (Mbps) | 0.00 | 0.05 | **1.33** |
| Average interference per PRB (dBm) | −66.8 | −69.6 | **−72.0** |

**Observations:**

- **Average user throughput:** The Twin strategy provides the highest average internet speed of 10.92 Mbps, compared with 6.48 Mbps for B1 and 8.67 Mbps for B2.
- **Throughput for poorly served users:** The 5th-percentile throughput is 0 Mbps for B1 and 0.05 Mbps for B2. The Twin strategy improves it to 1.33 Mbps, indicating better connectivity for users with the weakest performance.
- **Average interference:** The Twin strategy records the lowest interference at −72.0 dBm per PRB. This indicates that its channel-aware resource allocation helps reduce interference between neighbouring sectors.

Overall, the Twin strategy performs better across all three reported metrics.

### 3.2 Mobility Results

The number of Xn handovers recorded across the three walking routes is:

| Walking Route | Number of Handovers |
|---|---:|
| Route 1 | 0 |
| Route 2 | 2 |
| Route 3 | 1 |

We also measured how frequently the moving phone experienced zero throughput.

- Under the Twin strategy, zero throughput occurs on only 0–6.5% of the walking steps.
- Under B1, zero throughput occurs on 50–76% of the walking steps.

This indicates that the Twin strategy provides more consistent connectivity during the simulated walks.

### 3.3 What-If Analysis Results

The digital twin was used to predict network performance under three changes: doubling the number of UEs, switching off Site B and moving UEs approximately 30 metres.

The predicted mean throughput was within 0.85 Mbps of the corresponding simulation results.

This shows the potential of the digital twin to evaluate network changes without requiring a physical network deployment.

### 3.4 Computational Performance Results

On an Apple M4 CPU:

- Ray tracing takes approximately 20–30 ms per UE-sector link at 1 million rays.
- Memory consumption remains below 1.1 GB.
- The complete study takes approximately 25 minutes from scratch.

---

## 4. Limitations and Assumptions

The current implementation has some limitations that should be considered when interpreting the results.

**Campus Environment**
- The OpenStreetMap model does not include trees or terrain.
- Building heights are assumed for some structures.

**Radio Channel and Traffic Model**
- Each UE-sector link is represented by a single channel gain across the frequency band.
- Fast fading is not modelled.
- Every UE is assumed to require the same 12 PRBs.

**Network and Experimental Model**
- The what-if actual results come from the digital twin with additional random shadowing, not from a real 5G deployment.
- The 5G core message timings and security-related values are illustrative rather than measurements from a production network.

## 5. Conclusion

This project demonstrates the use of a ray-traced digital twin for studying 5G radio resource allocation and network behaviour in a realistic campus environment.

By combining campus geometry, radio propagation modelling, channel-aware resource allocation, UE mobility and 5G core signalling, we developed a simulation environment that can be used to evaluate alternative network configurations.

The experimental results show that the digital-twin-driven strategy achieves higher average user throughput, improves connectivity for poorly served users and reduces interference compared with the two baseline strategies.

The what-if experiments further demonstrate how the digital twin can help estimate the impact of network changes before applying them to a physical network.

---

## SetuCity: learn telecoms in a 3D city

`tools/signal_city/` is a self-contained 3D learning tool, a companion to the 2D 5G Core Explorer in `tools/understand_5g/`.
Open `tools/signal_city/index.html` in a browser (no build step, no server).
The IIT Gandhinagar logo in `tools/signal_city/assets/` is the institute's own mark, taken from Wikipedia.

- **Study mode**: seven paths (The Technologies, Accessing the Internet, Making a Call, Mobile Coverage, 4G and 5G Use Cases,
  Private Wireless Networks, Network Deployment). Each is a row of short lessons that unlock in order and ends with a quiz
  (multiple choice and drag-to-reorder). Progress is saved in the browser.
- **Explore mode**: free roam with clickable markers for use cases, concepts and quick facts, plus switchable network layers
  (coverage cells, radio waves, signal heat map, small cells, fibre, X-ray view, IoT traffic, core diagram).
- **Scenes**: every step moves the camera and animates the network. Several buildings open up as cutaways: data centre,
  hospital ward, office floor, smart home and factory.

Files: `js/world.js` (renderer, camera, day/night), `js/city.js` (the generated city), `js/fx.js` (network effects),
`js/content.js` (all lesson text, scenes, quizzes and diagrams), `js/app.js` (interface). It uses the three.js copy in `vendor/`.
To add or edit a lesson, change `js/content.js` only.
