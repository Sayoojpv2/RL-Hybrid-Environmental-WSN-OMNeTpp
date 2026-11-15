# First node unavailable (FND), corrected reporting

FND = first round in which fewer than N nodes are operational (MATLAB definition). A run in which no node became unavailable within the 1000-round horizon is **right-censored**: its FND is only known to be > 1000. No run is dropped. The aggregate states how many runs were censored; any mean is explicitly the **conditional mean over runs with an observed failure** and is not an unconditional estimate.

## Controlled design (v2)

| N | seed 42 | seed 43 | seed 44 | seed 45 | seed 46 | runs censored | conditional mean (observed only) | median over all 5 |
|---|---|---|---|---|---|---|---|---|
| 50 | 500 | 638 | 702 | 503 | 564 | 0 of 5 | 581.4 ± 87.8 (n = 5) | 564 |
| 100 | 811 | 846 | 950 | 720 | 697 | 0 of 5 | 804.8 ± 102.0 (n = 5) | 811 |
| 250 | 755 | 968 | 904 | 867 | 579 | 0 of 5 | 814.6 ± 152.7 (n = 5) | 867 |
| 500 | 811 | 684 | 835 | 778 | 963 | 0 of 5 | 814.2 ± 101.1 (n = 5) | 811 |

The median over all five runs is well defined even with censoring as long as fewer than half the runs are censored.

## v1 relay-scaling runs (topology varied with the seed), re-reported with the corrected rule

| Config | seed 42 | seed 43 | seed 44 | seed 45 | seed 46 | runs censored | conditional mean (observed only) | median over all 5 |
|---|---|---|---|---|---|---|---|---|
| Periyar50_Baseline | 450 | 591 | 386 | 472 | 241 | 0 of 5 | 428.0 ± 128.2 (n = 5) | 450 |
| Periyar100_RelayScaling | 653 | 799 | No node became unavailable within 1,000 rounds | 548 | 658 | 1 of 5 | 664.5 ± 103.0 (n = 4) | 658 |
| Periyar250_RelayScaling | 594 | 932 | No node became unavailable within 1,000 rounds | 804 | 821 | 1 of 5 | 787.8 ± 141.1 (n = 4) | 821 |
| Periyar500_RelayScaling | 741 | not run | not run | not run | not run | 0 of 1 | 741.0 (n = 1) | n/a (1 run) |

**Correction to the v1 report:** v1 printed “664.5 ± 103.0 (+1 seed with none)” (100 nodes) and “787.8 ± 141.1 (+1 seed with none)” (250 nodes). Those numbers were conditional means over 4 runs; they must not be read as five-run means.
