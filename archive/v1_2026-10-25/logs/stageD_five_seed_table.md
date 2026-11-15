| Metric | OMNeT++ (5 seeds) | MATLAB frozen (5 seeds) | Identical per seed? |
|---|---|---|---|
| Scheduled report slots | 10000 ± 0 | 10000 ± 0 | yes |
| Slots with valid data | 9825 ± 0 | 9825 ± 0 | yes |
| Reports emitted (source available) | 9275.0 ± 183.7 | 9275.0 ± 183.7 | yes |
| Reports delivered | 4102.4 ± 316.9 | 4102.4 ± 316.9 | yes |
| PDR = delivered / scheduled (%) | 41.024 ± 3.169 | 41.024 ± 3.169 | yes |
| Network losses (all causes) | 5172.6 ± 258.2 | 5172.6 ± 258.2 | yes |
|   - channel | 5163.4 ± 249.7 | 5163.4 ± 249.7 | yes |
|   - energy | 3.2 ± 2.4 | 3.2 ± 2.4 | yes |
|   - no feasible candidate | 5.4 ± 12.1 | 5.4 ± 12.1 | yes |
|   - TTL (15 hops) | 0.6 ± 1.3 | 0.6 ± 1.3 | yes |
| Unattempted reports | 0.0 ± 0.0 | 0.0 ± 0.0 | yes |
| First node unavailable, FND (round) | 428.0 ± 128.2 | 428.0 ± 128.2 | yes |
| Final operational nodes | 44.40 ± 1.14 | 44.40 ± 1.14 | yes |
| Residual energy (J) | 55.55 ± 2.86 | 55.55 ± 2.86 | yes |
| Energy per delivered report (J) | 0.01092 ± 0.00145 | 0.01092 ± 0.00145 | yes |
| Mean delivered hops | 4.34 ± 0.23 | 4.34 ± 0.23 | yes |
| Mean path delay (s, MATLAB definition) | 0.09106 ± 0.00488 | 0.09106 ± 0.00488 | yes |
| Q-table updates | 32837.8 ± 1539.7 | 32837.8 ± 1539.7 | yes |
| Exploratory decisions | 4165.8 ± 169.2 | 4165.8 ± 169.2 | yes |
| Mean latency round-start→BS (s, OMNeT++ only, not comparable) | 0.558 ± 0.031 | – | n/a |

Per seed (OMNeT++): seed 42: PDR 38.77 %, delivered 3877, FND 450, final nodes 45, residual 52.467 J; seed 43: PDR 44.84 %, delivered 4484, FND 591, final nodes 44, residual 57.363 J; seed 44: PDR 44.09 %, delivered 4409, FND 386, final nodes 46, residual 58.601 J; seed 45: PDR 38.25 %, delivered 3825, FND 472, final nodes 44, residual 52.528 J; seed 46: PDR 39.17 %, delivered 3917, FND 241, final nodes 43, residual 56.768 J
