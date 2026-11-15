# 200-node RL-Hybrid, final stage (seeds 47-66), extended OMNeT++ simulation

Integrity (500 rounds, one fate per report, BS count = delivered, energy/slot/invariant checks, retries decoded <= sent): Baseline: 20/20, C energy guard 0.8 (selected): 20/20, C+A guard 0.8 + retry reserve 0.5: 20/20

## Mean ± sample sd

| Metric | Baseline | C energy guard 0.8 (selected) | C+A guard 0.8 + retry reserve 0.5 |
|---|---|---|---|
| Generated reports | 75546 ± 1528 | 77098 ± 2375 | 68394 ± 1823 |
| Delivered reports | 33436 ± 2405 | 34277 ± 2997 | 38853 ± 2783 |
| Valid-report delivery ratio (%) | 34.65 ± 2.49 | 35.52 ± 3.11 | 40.26 ± 2.88 |
| Scheduled-slot delivery ratio (%) | 33.44 ± 2.41 | 34.28 ± 3.00 | 38.85 ± 2.78 |
| Source-packet PDR (%) | 44.23 ± 2.56 | 44.41 ± 2.87 | 56.76 ± 2.90 |
|   real KSPCB stations: valid-report ratio (%) | 32.98 ± 5.07 | 33.92 ± 5.55 | 38.16 ± 5.07 |
|   virtual replay nodes: valid-report ratio (%) | 34.74 ± 2.48 | 35.61 ± 3.08 | 40.37 ± 2.90 |
|   real KSPCB stations: delivered | 1591 ± 245 | 1636 ± 268 | 1841 ± 245 |
|   virtual replay nodes: delivered | 31845 ± 2278 | 32641 ± 2826 | 37012 ± 2662 |
| Channel losses (reports) | 36024 ± 1750 | 37852 ± 1990 | 23646 ± 1860 |
| No-eligible-next-hop losses | 5848 ± 2361 | 4843 ± 2180 | 5733 ± 2148 |
| Dead-source losses (valid slots, source unavailable) | 20954 ± 1528 | 19402 ± 2375 | 28106 ± 1823 |
| Unattempted (stranded) | 8 ± 3 | 17 ± 28 | 19 ± 28 |
| Energy losses | 222 ± 29 | 90 ± 25 | 121 ± 36 |
| Total residual energy (J of 400) | 68.60 ± 18.44 | 60.51 ± 22.23 | 45.35 ± 18.88 |
| Usable residual energy (J) | 68.05 ± 18.43 | 59.98 ± 22.20 | 44.51 ± 19.01 |
| TX energy (J) | 281.30 ± 18.33 | 287.18 ± 21.52 | 301.99 ± 20.31 |
| RX energy (J) | 45.54 ± 1.64 | 47.54 ± 2.12 | 47.87 ± 2.56 |
| Aggregation energy (J) | 4.558 ± 0.164 | 4.764 ± 0.213 | 4.797 ± 0.256 |
| Retry TX energy (J) | 0.00 ± 0.00 | 0.00 ± 0.00 | 36.14 ± 2.66 |
| Energy per delivered report (mJ) | 9.943 ± 0.676 | 9.960 ± 0.947 | 9.176 ± 0.871 |
| First node failure (round) | 152.6 ± 24.2 | 251.3 ± 36.2 | 176.9 ± 23.7 |
| Half of nodes failed (round) | 445.7 ± 46.2 | 444.4 ± 44.0 | 411.1 ± 46.5 |
| Last node failed (round) | – | – | – |
| Operational nodes at round 500 | 93.0 ± 12.1 | 97.2 ± 19.3 | 80.7 ± 26.0 |
| Mean delivered hops | 4.60 ± 0.23 | 4.76 ± 0.32 | 4.80 ± 0.27 |
| Link (frame) success rate | 0.8730 ± 0.0050 | 0.8699 ± 0.0053 | 0.8638 ± 0.0056 |
| Physical frames | 227599 ± 5738 | 219072 ± 6220 | 217692 ± 7022 |
| Retries sent | 0 ± 0 | 0 ± 0 | 12643 ± 689 |
| Q-learning updates | 227861 ± 5731 | 219548 ± 6278 | 205540 ± 6639 |
| Exploratory decisions (%) | 18.32 ± 0.12 | 18.33 ± 0.15 | 18.84 ± 0.23 |
| Forwarding: share of the 10 busiest nodes (%) | 16.25 ± 0.82 | 14.55 ± 0.65 | 14.81 ± 0.76 |
| End-to-end delay per report (ms) | 96.56 ± 4.90 | 99.88 ± 6.63 | 106.23 ± 5.62 |
| Delay, round-weighted (ms) | 90.53 ± 4.18 | 96.50 ± 6.77 | 98.08 ± 7.07 |
| Runtime per run (s) | 3.73 ± 0.21 | 3.57 ± 0.22 | 3.49 ± 0.27 |
| Peak memory (MiB) | 43.7 ± 0.2 | 43.8 ± 0.2 | 43.5 ± 0.2 |

## Paired difference vs Baseline (mean ± sd over seeds; [better seeds / n])

| Metric | C energy guard 0.8 (selected) | C+A guard 0.8 + retry reserve 0.5 |
|---|---|---|
| Generated reports | +1551 ± 1548 [20/20] t=+4.5 | -7152 ± 1397 [0/20] t=-22.9 |
| Delivered reports | +841 ± 1122 [16/20] t=+3.4 | +5417 ± 1617 [20/20] t=+15.0 |
| Valid-report delivery ratio (%) | +0.87 ± 1.16 [16/20] t=+3.4 | +5.61 ± 1.68 [20/20] t=+15.0 |
| Scheduled-slot delivery ratio (%) | +0.84 ± 1.12 [16/20] t=+3.4 | +5.42 ± 1.62 [20/20] t=+15.0 |
| Source-packet PDR (%) | +0.18 ± 0.98 [12/20] t=+0.8 | +12.53 ± 1.81 [20/20] t=+30.9 |
|   real KSPCB stations: valid-report ratio (%) | +0.94 ± 2.96 [13/20] t=+1.4 | +5.19 ± 4.02 [18/20] t=+5.8 |
|   virtual replay nodes: valid-report ratio (%) | +0.87 ± 1.18 [17/20] t=+3.3 | +5.64 ± 1.59 [20/20] t=+15.8 |
|   real KSPCB stations: delivered | +45 ± 143 [13/20] t=+1.4 | +250 ± 194 [18/20] t=+5.8 |
|   virtual replay nodes: delivered | +796 ± 1079 [17/20] t=+3.3 | +5167 ± 1460 [20/20] t=+15.8 |
| Channel losses (reports) | +1828 ± 748 [0/20] t=+10.9 | -12378 ± 844 [20/20] t=-65.6 |
| No-eligible-next-hop losses | -1005 ± 729 [19/20] t=-6.2 | -115 ± 939 [9/20] t=-0.5 |
| Dead-source losses (valid slots, source unavailable) | -1551 ± 1548 [20/20] t=-4.5 | +7152 ± 1397 [0/20] t=+22.9 |
| Unattempted (stranded) | +10 ± 27 [5/20] t=+1.6 | +11 ± 27 [3/20] t=+1.9 |
| Energy losses | -132 ± 33 [20/20] t=-17.8 | -101 ± 29 [20/20] t=-15.4 |
| Total residual energy (J of 400) | -8.08 ± 6.72 [3/20] t=-5.4 | -23.25 ± 6.84 [0/20] t=-15.2 |
| Usable residual energy (J) | -8.07 ± 6.75 [3/20] t=-5.3 | -23.54 ± 6.90 [0/20] t=-15.3 |
| TX energy (J) | +5.88 ± 5.78 t=+4.5 | +20.68 ± 6.22 t=+14.9 |
| RX energy (J) | +2.00 ± 1.61 t=+5.6 | +2.33 ± 3.12 t=+3.3 |
| Aggregation energy (J) | +0.205 ± 0.162 t=+5.7 | +0.238 ± 0.312 t=+3.4 |
| Retry TX energy (J) | +0.00 ± 0.00 | +36.14 ± 2.66 t=+60.8 |
| Energy per delivered report (mJ) | +0.017 ± 0.431 [11/20] t=+0.2 | -0.767 ± 0.446 [18/20] t=-7.7 |
| First node failure (round) | +98.8 ± 27.9 [20/20] t=+15.8 | +24.4 ± 22.2 [18/20] t=+4.9 |
| Half of nodes failed (round) | +32.8 ± 39.1 [5/6] t=+2.1 | -38.4 ± 27.2 [0/14] t=-5.3 |
| Last node failed (round) | – | – |
| Operational nodes at round 500 | +4.2 ± 14.7 [15/20] t=+1.3 | -12.3 ± 15.4 [3/20] t=-3.6 |
| Mean delivered hops | +0.16 ± 0.21 t=+3.4 | +0.20 ± 0.27 t=+3.4 |
| Link (frame) success rate | -0.0030 ± 0.0029 [2/20] t=-4.6 | -0.0091 ± 0.0037 [0/20] t=-10.9 |
| Physical frames | -8528 ± 5154 t=-7.4 | -9908 ± 11050 t=-4.0 |
| Retries sent | +0 ± 0 | +12643 ± 689 t=+82.1 |
| Q-learning updates | -8313 ± 5178 t=-7.2 | -22321 ± 10539 t=-9.5 |
| Exploratory decisions (%) | +0.01 ± 0.09 t=+0.4 | +0.52 ± 0.20 t=+11.7 |
| Forwarding: share of the 10 busiest nodes (%) | -1.70 ± 0.96 t=-7.9 | -1.45 ± 1.32 t=-4.9 |
| End-to-end delay per report (ms) | +3.32 ± 4.41 [4/20] t=+3.4 | +9.67 ± 5.61 [1/20] t=+7.7 |
| Delay, round-weighted (ms) | +5.97 ± 4.13 [0/20] t=+6.5 | +7.55 ± 6.04 [1/20] t=+5.6 |
| Runtime per run (s) | -0.16 ± 0.17 t=-4.3 | -0.24 ± 0.33 t=-3.3 |
| Peak memory (MiB) | +0.1 ± 0.1 t=+2.6 | -0.3 ± 0.2 t=-6.3 |

## Per seed (valid-report ratio % / source PDR % / FND / alive at 500 / residual J / delay ms)

| Variant | seed 47 | seed 48 | seed 49 | seed 50 | seed 51 | seed 52 | seed 53 | seed 54 | seed 55 | seed 56 | seed 57 | seed 58 | seed 59 | seed 60 | seed 61 | seed 62 | seed 63 | seed 64 | seed 65 | seed 66 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline | 33.60 / 43.92 / 122 / 99 / 78.4 / 95.3 | 34.29 / 44.93 / 151 / 93 / 78.2 / 92.7 | 33.07 / 42.74 / 141 / 84 / 55.1 / 105.0 | 35.99 / 45.64 / 134 / 95 / 64.5 / 95.4 | 31.45 / 40.83 / 154 / 97 / 78.4 / 93.4 | 36.97 / 47.35 / 158 / 98 / 83.9 / 91.7 | 32.92 / 42.39 / 169 / 85 / 52.9 / 105.9 | 34.17 / 43.29 / 146 / 102 / 73.2 / 91.8 | 39.52 / 48.38 / 163 / 67 / 32.2 / 101.3 | 34.21 / 44.02 / 147 / 94 / 67.2 / 97.1 | 36.95 / 46.02 / 141 / 98 / 65.2 / 96.2 | 32.82 / 41.23 / 188 / 72 / 37.3 / 105.3 | 37.90 / 46.89 / 160 / 101 / 61.3 / 97.6 | 36.44 / 46.63 / 163 / 98 / 78.9 / 92.3 | 35.20 / 44.91 / 163 / 97 / 68.7 / 96.6 | 37.21 / 46.51 / 161 / 101 / 73.0 / 94.5 | 32.36 / 42.36 / 165 / 100 / 79.5 / 96.1 | 28.77 / 37.89 / 75 / 111 / 113.2 / 89.6 | 34.01 / 43.31 / 163 / 102 / 86.0 / 91.5 | 35.13 / 45.35 / 187 / 66 / 44.8 / 101.8 |
| C energy guard 0.8 (selected) | 33.59 / 43.32 / 232 / 102 / 70.8 / 97.1 | 35.02 / 44.96 / 232 / 103 / 73.5 / 95.0 | 34.91 / 44.33 / 271 / 93 / 52.5 / 101.6 | 38.16 / 47.14 / 262 / 102 / 61.3 / 95.4 | 32.69 / 41.41 / 238 / 111 / 64.1 / 101.4 | 38.97 / 47.33 / 260 / 108 / 73.7 / 94.3 | 33.39 / 42.27 / 252 / 95 / 37.5 / 109.2 | 35.47 / 44.61 / 239 / 106 / 71.5 / 94.1 | 43.04 / 49.00 / 330 / 91 / 18.2 / 102.2 | 33.54 / 42.65 / 228 / 89 / 56.7 / 104.9 | 37.41 / 46.00 / 248 / 102 / 65.5 / 101.7 | 31.31 / 38.77 / 329 / 22 / 12.3 / 116.6 | 38.13 / 47.08 / 266 / 94 / 48.4 / 111.4 | 37.74 / 47.72 / 252 / 107 / 79.6 / 90.6 | 35.01 / 44.42 / 239 / 105 / 70.6 / 100.1 | 37.59 / 46.97 / 243 / 100 / 65.7 / 99.3 | 33.71 / 43.44 / 234 / 105 / 73.6 / 94.5 | 29.18 / 38.35 / 175 / 110 / 104.3 / 94.1 | 34.07 / 42.81 / 204 / 113 / 80.6 / 94.1 | 37.48 / 45.62 / 292 / 85 / 30.0 / 100.0 |
| C+A guard 0.8 + retry reserve 0.5 | 37.42 / 54.74 / 160 / 89 / 54.5 / 104.8 | 39.88 / 57.72 / 165 / 95 / 61.8 / 98.9 | 38.16 / 55.62 / 184 / 86 / 46.7 / 98.2 | 43.50 / 60.08 / 192 / 93 / 46.4 / 100.2 | 39.89 / 57.18 / 160 / 93 / 55.7 / 101.4 | 44.39 / 59.86 / 178 / 95 / 52.9 / 109.5 | 37.43 / 54.43 / 174 / 58 / 28.5 / 109.7 | 40.57 / 58.11 / 156 / 97 / 56.3 / 100.7 | 42.05 / 57.68 / 230 / 13 / 4.0 / 117.4 | 38.81 / 55.00 / 169 / 75 / 40.1 / 111.8 | 42.31 / 58.50 / 184 / 85 / 46.6 / 113.0 | 34.84 / 50.28 / 206 / 36 / 10.3 / 114.2 | 44.59 / 59.99 / 191 / 89 / 37.6 / 106.8 | 43.94 / 60.78 / 183 / 102 / 58.0 / 102.3 | 40.63 / 57.61 / 159 / 95 / 56.8 / 105.0 | 43.06 / 59.76 / 180 / 96 / 48.5 / 107.7 | 38.31 / 55.49 / 169 / 90 / 53.0 / 101.7 | 35.24 / 50.74 / 134 / 102 / 77.7 / 102.1 | 40.95 / 56.28 / 144 / 97 / 60.6 / 106.3 | 39.30 / 55.33 / 221 / 27 / 10.9 / 112.8 |

Result-file size: Baseline: 374 MiB (folder); C energy guard 0.8 (selected): 374 MiB (folder); C+A guard 0.8 + retry reserve 0.5: 377 MiB (folder)
