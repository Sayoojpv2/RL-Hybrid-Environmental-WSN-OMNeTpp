PASS seed 42: every report has one fate, BS count = delivered, energy/slot/invariant checks OK (both runs)
PASS seed 42: 890 of 934 retries decoded; expected 937.5 from the link qualities (z = -3.25)
PASS seed 43: every report has one fate, BS count = delivered, energy/slot/invariant checks OK (both runs)
PASS seed 43: 1235 of 1192 retries decoded; expected 1243.5 from the link qualities (z = -0.54)
PASS seed 44: every report has one fate, BS count = delivered, energy/slot/invariant checks OK (both runs)
PASS seed 44: 1089 of 1149 retries decoded; expected 1067.8 from the link qualities (z = +1.39)
PASS seed 45: every report has one fate, BS count = delivered, energy/slot/invariant checks OK (both runs)
PASS seed 45: 869 of 921 retries decoded; expected 869.7 from the link qualities (z = -0.05)
PASS seed 46: every report has one fate, BS count = delivered, energy/slot/invariant checks OK (both runs)
PASS seed 46: 1313 of 1192 retries decoded; expected 1320.5 from the link qualities (z = -0.46)

10 checks, 0 failed

| Metric | seed 42 (base / var / diff) | seed 43 (base / var / diff) | seed 44 (base / var / diff) | seed 45 (base / var / diff) | seed 46 (base / var / diff) | mean base | mean variant | paired diff mean ± sd | seeds improved* |
|---|---|---|---|---|---|---|---|---|---|
| generated | 4408 / 3501 / -907 | 4436 / 4022 / -414 | 4220 / 4001 / -219 | 4110 / 3180 / -930 | 4460 / 4036 / -424 | 4327 | 3748 | -579 ± 321 | 0/5 |
| delivered | 810 / 763 / -47 | 1495 / 1862 / +367 | 1824 / 2192 / +368 | 1478 / 1340 / -138 | 1462 / 1544 / +82 | 1414 | 1540 | +126 ± 234 | 3/5 |
| validPDR | 16.79 / 15.81 / -0.97 | 30.98 / 38.59 / +7.61 | 37.80 / 45.43 / +7.63 | 30.63 / 27.77 / -2.86 | 30.30 / 32.00 / +1.70 | 29.30 | 31.92 | +2.62 ± 4.84 | 3/5 |
| schedPDR | 16.20 / 15.26 / -0.94 | 29.90 / 37.24 / +7.34 | 36.48 / 43.84 / +7.36 | 29.56 / 26.80 / -2.76 | 29.24 / 30.88 / +1.64 | 28.28 | 30.80 | +2.53 ± 4.67 | 3/5 |
| sourcePDR | 18.38 / 21.79 / +3.42 | 33.70 / 46.30 / +12.59 | 43.22 / 54.79 / +11.56 | 35.96 / 42.14 / +6.18 | 32.78 / 38.26 / +5.48 | 32.81 | 40.65 | +7.85 ± 4.01 | 5/5 |
| residualJ | 7.716 / 7.617 / -0.100 | 10.124 / 7.527 / -2.597 | 8.554 / 6.234 / -2.320 | 7.048 / 7.239 / +0.191 | 9.550 / 7.083 / -2.468 | 8.598 | 7.140 | -1.459 ± 1.381 | 1/5 |
| eprMJ | 15.165 / 16.230 / +1.065 | 6.606 / 6.699 / +0.093 | 6.275 / 6.280 / +0.005 | 8.763 / 9.523 / +0.760 | 7.147 / 8.366 / +1.219 | 8.791 | 9.420 | +0.628 ± 0.555 | 0/5 |
| FND | 342 / 74 / -268 | 132 / 81 / -51 | 192 / 62 / -130 | 161 / 49 / -112 | 135 / 109 / -26 | 192 | 75 | -117 ± 94 | 0/5 |
| alive | 7 / 6 / -1 | 8 / 8 / +0 | 7 / 8 / +1 | 7 / 6 / -1 | 9 / 7 / -2 | 8 | 7 | -1 ± 1 | 1/5 |
| delayPacketMs | 46.90 / 70.43 / +23.53 | 39.01 / 52.84 / +13.83 | 46.16 / 51.93 / +5.77 | 68.77 / 51.14 / -17.63 | 41.34 / 53.66 / +12.32 | 48.44 | 56.00 | +7.56 ± 15.45 | 1/5 |
| delayRoundMs | 42.07 / 54.68 / +12.61 | 34.90 / 48.57 / +13.68 | 41.32 / 49.29 / +7.97 | 55.73 / 44.09 / -11.64 | 35.84 / 43.86 / +8.02 | 41.97 | 48.10 | +6.13 ± 10.27 | 1/5 |
| frames | 5734 / 5713 / -21 | 7061 / 8582 / +1521 | 6862 / 7552 / +690 | 8348 / 6230 / -2118 | 7399 / 8119 / +720 | 7081 | 7239 | +158 ± 1385 | – |
| retxSent | 0 / 934 / +934 | 0 / 1192 / +1192 | 0 / 1149 / +1149 | 0 / 921 / +921 | 0 / 1192 / +1192 | 0 | 1078 | +1078 ± 138 | – |
| lossChannel | 1498 / 377 / -1121 | 1384 / 349 / -1035 | 1438 / 346 / -1092 | 1846 / 285 / -1561 | 1405 / 378 / -1027 | 1514 | 347 | -1167 ± 224 | 5/5 |
| lossNoCand | 1116 / 1516 / +400 | 1179 / 1640 / +461 | 713 / 1175 / +462 | 594 / 1500 / +906 | 1287 / 1855 / +568 | 978 | 1537 | +559 ± 203 | 0/5 |
| unattempted | 982 / 836 / -146 | 375 / 167 / -208 | 241 / 285 / +44 | 189 / 48 / -141 | 304 / 256 / -48 | 418 | 318 | -100 ± 99 | 4/5 |
| sourceDown | 417 / 1324 / +907 | 389 / 803 / +414 | 605 / 824 / +219 | 715 / 1645 / +930 | 365 / 789 / +424 | 498 | 1077 | +579 ± 321 | 0/5 |

* seeds where the variant is better (higher for delivery/energy left/FND/alive, lower for energy per report, delay, losses)
