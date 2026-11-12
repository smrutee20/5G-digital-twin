## Experimental Results

The three resource allocation strategies were evaluated using 20 randomly generated network placements, each containing 100 users (UEs).

We compare their performance using three main metrics:

- **Average user throughput:** How fast the internet is for a user on average.
- **5th-percentile user throughput:** How well the users with the poorest connections are performing.
- **Average interference:** How much unwanted radio signal affects the users. A more negative value indicates lower interference.

The results are reported as mean ± 95% confidence interval where applicable.

### 1. Comparison of Resource Allocation Strategies

| Performance Metric | B1: Fixed PRBs | B2: Random PRBs | Twin |
|---|---:|---:|---:|
| Average user throughput (Mbps) | 6.48 ± 0.50 | 8.67 ± 0.35 | **10.92 ± 0.50** |
| Throughput for the bottom 5% of users (Mbps) | 0.00 | 0.05 | **1.33** |
| Average interference per PRB (dBm) | −66.8 | −69.6 | **−72.0** |

**What do these results tell us?**

- **Average user throughput:** The Twin strategy provides the highest average throughput at 10.92 Mbps, compared with 6.48 Mbps for B1 and 8.67 Mbps for B2.
- **Performance of the bottom 5% of users:** B1 and B2 provide almost no throughput to the most poorly connected users. The Twin strategy improves their 5th-percentile throughput to 1.33 Mbps.
- **Average interference:** The Twin strategy has the lowest interference power at −72.0 dBm per PRB, compared with −66.8 dBm for B1 and −69.6 dBm for B2.

Overall, the results show that the digital-twin-driven strategy improves average user throughput, provides better connectivity to poorly served users, and reduces interference.

### 2. Performance During User Mobility

The project also evaluates how the network performs when a user moves along three walking routes across the campus.

The simulation records how many times the phone switches between neighbouring base stations (Xn handovers).

| Walking Route | Number of Xn Handovers |
|---|---:|
| Route 1 | 0 |
| Route 2 | 2 |
| Route 3 | 1 |

We also measure how often the walking phone experiences zero internet throughput during its journey.

- **Twin:** The phone experiences zero throughput on only 0–6.5% of the simulated steps.
- **B1:** The phone experiences zero throughput on 50–76% of the simulated steps.

This indicates that the Twin strategy provides more consistent connectivity while the user moves across campus.

### 3. What-If Prediction

The digital twin is also used to predict how network performance changes under different conditions.

Three scenarios are evaluated:

1. Doubling the number of users.
2. Switching off Site B.
3. Moving users approximately 30 metres from their original positions.

The predictions are compared against new simulations that include random shadowing.

The predicted average throughput differs from the simulated result by no more than 0.85 Mbps.

This demonstrates how the digital twin can help estimate the impact of network changes before running a new simulation.

### 4. Computational Performance

The ray-tracing component is benchmarked on an Apple M4 CPU.

- Each UE-sector link takes approximately 20–30 milliseconds to trace at 1 million rays.
- The simulation uses less than 1.1 GB of memory.

These measurements provide an indication of the computational cost of generating radio measurements for the campus environment.
