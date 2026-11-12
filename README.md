# 5G RAN Digital Twin for Channel-Aware Resource Allocation and Network What-If Analysis

## 1. Problem Statement

Evaluating alternative channel/resource allocations directly on a physical 5G network can be expensive and difficult to reproduce because performance depends on UE locations, propagation conditions and traffic load. A digital twin can provide a physics-aware representation of the radio environment and allow alternative allocations and network configurations to be evaluated before applying them to the network.

### 5G and Beyond Projects 2026 - Semester-I- Final

1. Deploy or use any of the digital-twin framework for eg. NVIDIA AODT and generate a scenario containing a RUs/gNBs and UEs and understand the available radio/environment configuration parameters.
2. Obtain site-specific channel information and relevant RAN measurements for different UE locations and links.
3. Define a simple baseline resource/channel-allocation strategy, such as fixed or random allocation.
4. Implement a channel-aware allocation strategy that uses digital-twin-derived channel information to select an appropriate channel/resource or serving radio for each UE.
5. Move or reconfigure UEs and evaluate how changes in the physical environment affect received signal/channel conditions and the selected allocation.
6. Compare baseline and twin-assisted strategies using relevant 5G KPIs such as SINR/channel quality, throughput, interference and resource utilization where available.
7. Use the same digital twin for a small what-if analysis, such as increasing UE density, changing UE positions or modifying resource allocation, and predict the resulting network performance before applying the configuration.
8. Document the capabilities, computational requirements and limitations of the chosen digital-twin framework as a 5G/6G network digital-twin platform and identify the research problems for which it is suitable.

**3GPP Reference Document:**  
https://www.etsi.org/deliver/etsi_tr/128900_128999/128915/19.00.00_60/tr_128915v190000p.pdf

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
| OpenStreetMap | Campus building geometry |

The ray-tracing benchmark was performed on an Apple M4 CPU.

The measured computational requirements are:

- Approximately 20–30 ms per UE-sector link at 1 million rays.
- Memory consumption below 1.1 GB.

The complete experimental study takes approximately 25 minutes from scratch, including ray tracing and performance benchmarking.

The platform evaluation is implemented in `tasks/task8_platform.py`.

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
