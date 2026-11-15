# Stages B/C – node-count checks and smoke tests (seed 42, 20 rounds)

Configs `Periyar100_Smoke`, `Periyar250_Smoke`, `Periyar500_Smoke` (20 rounds = 200 of the 10,000 slots;
channel export on). Measured with `tools/run_measured.ps1`. Machine: Windows 11 laptop, release build.

| N | Wall time | Peak working set | Events (last status line) | Delivered | Network losses | PDR (of 200 slots) | Q-updates | Added relays chosen |
|---|---|---|---|---|---|---|---|---|
| 100 | 0.4–0.6 s | 23 MiB | 1681 | 51 | 70 | 25.5 % | 415 | 43 of 50 |
| 250 | 0.6 s | 23.5 MiB | 1989 | 59 | 62 | 29.5 % | 492 | 118 of 200 |
| 500 | 0.6 s | 27.2 MiB | 1977 | 39 | 82 | 19.5 % | 489 | 207 of 450 |

The 20-round PDR values only show that traffic flows; they are not results.

`tools/verify_scaling.py`: **11/11 checks at each size** (`logs/stageBC_Periyar{100,250,500}_Smoke_checks.txt`):
S1 exactly N battery-node modules plus one BS · S2 nodes 1..50 bit-identical to MATLAB, extras inside the
area and all distinct · S3 workload identical to MATLAB · S4 relays never originate · S5 action targets in
1..N+1, to-BS actions = N+1, states in 1..6561 · S6 added relays are actually used · S7 original 50×51 channel
block identical to MATLAB · S8 per-node energy closure (2 J × N) · S9 slot accounting · S10 no action by or
towards an unavailable node, TTL ≤ 15 · S11 every round inside its 10 s slot.

The Cmdenv run of `Periyar250_GuiPreview` produced the same 20-round PDR as `Periyar250_Smoke` (29.5 %),
as expected. The preview was also opened in Qtenv (set up only, not run): 502 modules created
(`docs/qtenv_250_preview_loaded.png`). At 250 nodes the labels overlap heavily. The preview is for
looking only, and Qtenv animation was not run.
