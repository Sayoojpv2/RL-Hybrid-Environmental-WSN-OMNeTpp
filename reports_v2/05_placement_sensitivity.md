# 250-node relay-placement sensitivity (separate experiment)

Run seed fixed at 42 (channel stream rng(1000000·42 + r), agent stream rng(42)); nodes 1..50 fixed at the MATLAB layout of seed 42; only the 200 added relays are re-placed, from the documented extraTopologySeed values below. Everything else is identical. These five values are **not** part of the five-run-seed standard deviation in `02_controlled_results.md`; they describe how much a single run changes when only the relay placement changes. Placement 900042 is the placement of the controlled design (byte-identical to Ctrl250 run seed 42). 

| Metric | topo 900042 | topo 910001 | topo 910002 | topo 910003 | topo 910004 | range (max − min) |
|---|---|---|---|---|---|---|
| PDR (%) | 33.07 | 29.65 | 33.15 | 32.70 | 34.40 | 4.75 |
| Delivered / emitted (%) | 34.52 | 32.04 | 35.22 | 34.91 | 35.01 | 3.188 |
| Delivered | 3307 | 2965 | 3315 | 3270 | 3440 | 475 |
| Emitted | 9580 | 9255 | 9411 | 9367 | 9825 | 570 |
| Mean delivered hops | 5.83 | 5.39 | 5.36 | 5.61 | 5.55 | 0.472 |
| Energy per delivered report (mJ) | 19.13 | 20.62 | 18.80 | 19.36 | 19.24 | 1.82 |
| Transmission success rate | 0.8327 | 0.8271 | 0.8278 | 0.8302 | 0.8305 | 0.00562 |
| Mean true LQ of chosen hops | 0.8326 | 0.8302 | 0.8304 | 0.8307 | 0.8302 | 0.002393 |
| Mean progress per route hop (m) | 66.2 | 68.9 | 68.6 | 67.3 | 67.6 | 2.716 |
| Mean feasible candidates per route decision | 55.7 | 56.8 | 55.7 | 56.5 | 56.2 | 1.112 |
| FND (first node unavailable) | 755 | 595 | 679 | 722 | none within 1000 rounds | 1 of 5 censored |
| Operational at end | 249 | 248 | 248 | 248 | 250 | 2 |
| Topology: mean nearest-neighbour distance, all 250 nodes (m) | 5.75 | 5.54 | 5.68 | 6.09 | 5.32 | 0.7748 |
| Topology: largest gap along the river, incl. BS at x = 600 (m) | 9.57 | 12.93 | 15.41 | 16.71 | 15.69 | 7.138 |
| Topology: nodes within 100 m of the BS | 42 | 43 | 34 | 44 | 49 | 15 |
| Topology: mean distance of added relays to the BS (m) | 301.1 | 305.7 | 317.4 | 292.5 | 286.0 | 31.39 |
| Topology: mean distance from a station to its nearest node (m) | 6.94 | 7.57 | 6.55 | 7.01 | 5.19 | 2.375 |
| Wall time (s) | 4.07 | 3.81 | 3.72 | 3.78 | 4.05 | 0.35 |

PDR spread: placement-only sd over 5 placements (run seed 42) = 1.77 pp; run-seed-only sd over 5 run seeds (placement 900042) = 0.90 pp.

Observation (5 placements only, not a tested relationship): the PDR rank order coincides exactly with the inverse rank of the mean station-to-nearest-node distance (5.19 → 7.57 m). Part of the PDR spread comes from emission (node failures of sources); compare the delivered/emitted row.
