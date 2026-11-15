PASS seed 42: every report has one fate, BS count = delivered, energy/slot/invariant checks OK (both runs)
PASS seed 42: 889 of 1181 retries decoded (must be <= sent); expected 894.7 from the link qualities (z = -0.41)
PASS seed 43: every report has one fate, BS count = delivered, energy/slot/invariant checks OK (both runs)
PASS seed 43: 918 of 1202 retries decoded (must be <= sent); expected 904.8 from the link qualities (z = +0.92)
PASS seed 44: every report has one fate, BS count = delivered, energy/slot/invariant checks OK (both runs)
PASS seed 44: 868 of 1134 retries decoded (must be <= sent); expected 845.0 from the link qualities (z = +1.62)
PASS seed 45: every report has one fate, BS count = delivered, energy/slot/invariant checks OK (both runs)
PASS seed 45: 848 of 1083 retries decoded (must be <= sent); expected 825.0 from the link qualities (z = +1.70)
PASS seed 46: every report has one fate, BS count = delivered, energy/slot/invariant checks OK (both runs)
PASS seed 46: 980 of 1244 retries decoded (must be <= sent); expected 950.1 from the link qualities (z = +2.08)

10 checks, 0 failed

| Metric | seed 42 (base / var / diff) | seed 43 (base / var / diff) | seed 44 (base / var / diff) | seed 45 (base / var / diff) | seed 46 (base / var / diff) | mean base | mean variant | paired diff mean ± sd | seeds improved* |
|---|---|---|---|---|---|---|---|---|---|
| generated | 4408 / 3703 / -705 | 4436 / 3926 / -510 | 4220 / 3986 / -234 | 4110 / 3890 / -220 | 4460 / 3990 / -470 | 4327 | 3899 | -428 ± 204 | 0/5 |
| delivered | 810 / 1752 / +942 | 1495 / 1808 / +313 | 1824 / 2213 / +389 | 1478 / 1446 / -32 | 1462 / 1867 / +405 | 1414 | 1817 | +403 ± 349 | 4/5 |
| validPDR | 16.79 / 36.31 / +19.52 | 30.98 / 37.47 / +6.49 | 37.80 / 45.87 / +8.06 | 30.63 / 29.97 / -0.66 | 30.30 / 38.69 / +8.39 | 29.30 | 37.66 | +8.36 ± 7.24 | 4/5 |
| schedPDR | 16.20 / 35.04 / +18.84 | 29.90 / 36.16 / +6.26 | 36.48 / 44.26 / +7.78 | 29.56 / 28.92 / -0.64 | 29.24 / 37.34 / +8.10 | 28.28 | 36.34 | +8.07 ± 6.99 | 4/5 |
| sourcePDR | 18.38 / 47.31 / +28.94 | 33.70 / 46.05 / +12.35 | 43.22 / 55.52 / +12.30 | 35.96 / 37.17 / +1.21 | 32.78 / 46.79 / +14.01 | 32.81 | 46.57 | +13.76 ± 9.90 | 5/5 |
| residualJ | 7.716 / 5.376 / -2.341 | 10.124 / 7.055 / -3.069 | 8.554 / 6.069 / -2.485 | 7.048 / 6.979 / -0.069 | 9.550 / 6.564 / -2.987 | 8.598 | 6.408 | -2.190 ± 1.226 | 0/5 |
| eprMJ | 15.165 / 8.347 / -6.818 | 6.606 / 7.160 / +0.554 | 6.275 / 6.295 / +0.020 | 8.763 / 9.005 / +0.242 | 7.147 / 7.197 / +0.049 | 8.791 | 7.601 | -1.191 ± 3.153 | 1/5 |
| FND | 342 / 66 / -276 | 132 / 90 / -42 | 192 / 53 / -139 | 161 / 30 / -131 | 135 / 114 / -21 | 192 | 71 | -122 ± 101 | 0/5 |
| alive | 7 / 7 / +0 | 8 / 6 / -2 | 7 / 7 / +0 | 7 / 8 / +1 | 9 / 7 / -2 | 8 | 7 | -1 ± 1 | 1/5 |
| delayPacketMs | 46.90 / 66.04 / +19.14 | 39.01 / 53.46 / +14.45 | 46.16 / 52.14 / +5.98 | 68.77 / 42.16 / -26.61 | 41.34 / 58.13 / +16.79 | 48.44 | 54.39 | +5.95 ± 18.87 | 1/5 |
| delayRoundMs | 42.07 / 49.60 / +7.53 | 34.90 / 49.47 / +14.57 | 41.32 / 49.18 / +7.86 | 55.73 / 41.44 / -14.29 | 35.84 / 47.80 / +11.96 | 41.97 | 47.50 | +5.52 ± 11.46 | 1/5 |
| frames | 5734 / 8344 / +2610 | 7061 / 8096 / +1035 | 6862 / 7423 / +561 | 8348 / 7000 / -1348 | 7399 / 8626 / +1227 | 7081 | 7898 | +817 ± 1430 | – |
| retxSent | 0 / 1181 / +1181 | 0 / 1202 / +1202 | 0 / 1134 / +1134 | 0 / 1083 / +1083 | 0 / 1244 / +1244 | 0 | 1169 | +1169 ± 62 | – |
| lossChannel | 1498 / 333 / -1165 | 1384 / 347 / -1037 | 1438 / 311 / -1127 | 1846 / 285 / -1561 | 1405 / 315 / -1090 | 1514 | 318 | -1196 ± 209 | 5/5 |
| lossNoCand | 1116 / 1516 / +400 | 1179 / 1677 / +498 | 713 / 1227 / +514 | 594 / 2054 / +1460 | 1287 / 1660 / +373 | 978 | 1627 | +649 ± 457 | 0/5 |
| unattempted | 982 / 98 / -884 | 375 / 86 / -289 | 241 / 231 / -10 | 189 / 101 / -88 | 304 / 142 / -162 | 418 | 132 | -287 ± 349 | 5/5 |
| sourceDown | 417 / 1122 / +705 | 389 / 899 / +510 | 605 / 839 / +234 | 715 / 935 / +220 | 365 / 835 / +470 | 498 | 926 | +428 ± 204 | 0/5 |

* seeds where the variant is better (higher for delivery/energy left/FND/alive, lower for energy per report, delay, losses)
