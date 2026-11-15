# Performance and scalability

## Measured cost (Cmdenv, release build, Windows 11 laptop; `logs/performance.txt`)
| N | Rounds × seeds | Wall | ≈ per 1000-round seed | Peak working set |
|---|---|---|---|---|
| 50 | 1000 × 5 | 9.8 s | 2.0 s | 23.4 MiB |
| 100 | 1000 × 5 | 11.4 s | 2.3 s | 23.8 MiB |
| 250 | 1000 × 5 | 15.1 s | 3.0 s | 24.9 MiB |
| 500 | 1000 × 1 | 4.2 s | 4.2 s | 28.6 MiB |

Wall time includes writing the per-decision CSV traces. Qtenv with the 250-node preview loaded used 126 MiB RSS.
Runtime grows sub-linearly with N because the number of events (about 140–146 k per run) is set by the
10 sources, not by N. The per-decision cost is O(N): candidate scan over all nodes.

## Data structures that had to change
| Item | Before (50 only) | Now |
|---|---|---|
| BS action index / action count | `static const 51` | member `N + 1`, set from `numNodes` |
| Q-table | `unordered_map` keyed by (state−1)·51 + (action−1) | same map, key stride N+1 (identical at N = 50) |
| Topology | 50 MATLAB nodes | 50 MATLAB nodes plus N−50 from a separate stream |
| Channel table | 50×51 bits per round (MATLAB stream) | the same 50×51 block; added-relay links drawn lazily per frame by a counter hash; **no N×N×rounds array** |
| Distance prior | 50×51 | N×(N+1) doubles (500 nodes: about 2 MB) |
| NED | n1..n50, BS, controller | plus `relay[numNodes−50]` |

## Why sparse Q storage is needed
A dense table of 6561 states × (N+1) actions × 8 bytes, for each of N nodes, would need:

| N | Dense Q (all nodes) | Distinct (node, state, action) pairs actually decided (seed 42) |
|---|---|---|
| 50 | 128 MiB | 5,666 |
| 100 | 506 MiB | 9,588 |
| 250 | 3.1 GiB | 16,893 |
| 500 | 12.2 GiB | 21,774 |

The hash map stores only the pairs that were touched, a few tens of thousands at most, so memory stays
under 30 MiB. The algorithm is unaffected: an absent entry reads as 0, exactly as MATLAB's zero-initialised table.
The count of pairs is the number of distinct decisions taken. Each Q-update touches one of them,
and bootstrap reads do not insert entries.

## Learning-signal dilution (observation, not a tested cause)
Q-updates per distinct decided pair at seed 42: 33,736 / 5,666 ≈ 6.0 (N = 50) versus
36,325 / 21,774 ≈ 1.7 (N = 500). With a fixed 1000-round budget, each action value is learned from fewer samples.

## Limitations
* Added-relay links use a hash stream with MATLAB's distance law, not MATLAB's generator. MATLAB has no
  reference for N > 50, so those links cannot be compared with MATLAB bit for bit.
* All the original model abstractions remain: no MAC/PHY or contention, a centralised round controller that
  sequences decisions, free and lossless control/feedback information, idealised neighbour knowledge
  (every node may try any node closer to the BS; no radio range limit). Contention would grow with density in reality.
* There is one topology realisation per seed for the added relays (`extraTopologySeed = 900000 + seed`).
  Sensitivity to that stream was not tested.
* 500 nodes: one seed only. 100 and 250 nodes: five seeds.
* At 250+ nodes the Qtenv view is too dense to read labels. It is useful only as a picture of density.
