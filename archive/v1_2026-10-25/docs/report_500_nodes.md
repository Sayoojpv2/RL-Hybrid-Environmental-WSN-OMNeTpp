# Stage E – 500 nodes

## What was run
| Test | Status |
|---|---|
| `Periyar500_Smoke`, seed 42, 20 rounds | done, 11/11 checks |
| `Periyar500_RelayScaling`, **seed 42, full 1000 rounds** | **done**: 1000 of 1000 rounds, 10/10 checks (`logs/stageE_Periyar500_RelayScaling_checks.txt`) |
| Seed-42 re-run with the channel export: original 50×51 block, 1000 rounds | done, all 2,550,000 bits identical to MATLAB (11/11 checks, `logs/stageDE_full1000_channel_block_checks.txt`) |
| Seeds 43–46 at 500 nodes | **not run.** The task asked for seed 42. The 500-node result is therefore a single seed, with no spread, and must not be presented as a five-seed mean. |

There was no technical blocker: 4.2 s wall time, 28.6 MiB peak working set, about 146,000 events.

## Seed-42 result (500 nodes: 10 sources + 490 relay-only)
| Metric | N = 50 (seed 42) | N = 500 (seed 42) |
|---|---|---|
| Scheduled / valid-data slots | 10000 / 9825 | 10000 / 9825 |
| Emitted | 9220 | 9471 |
| Delivered | 3877 | 3214 |
| PDR (delivered / scheduled) | 38.77 % | **32.14 %** |
| Delivered / emitted | 42.05 % | 33.94 % |
| Losses: channel / energy / no candidate / TTL | 5340 / 3 / 0 / 0 | 6256 / 0 / 0 / 1 |
| FND | 450 | 741 |
| Operational nodes at end | 45 of 50 | 498 of 500 |
| Residual energy | 52.47 of 100 J | 934.10 of 1000 J |
| Energy per delivered report | 12.3 mJ | 20.5 mJ |
| Mean delivered hops | 4.64 | 5.87 (max route hop 15 = TTL reached once) |
| Q-updates / exploratory decisions | 33736 / 4252 | 36325 / 4630 |
| Added relays used as cluster head or next hop | – | 450 of 450 |

The trend continues from 250 nodes: longer routes, more channel losses, lower PDR.
For seed 42 the PDR falls from 38.77 % (50) to 35.84 % (100), 33.70 % (250) and 32.14 % (500).
