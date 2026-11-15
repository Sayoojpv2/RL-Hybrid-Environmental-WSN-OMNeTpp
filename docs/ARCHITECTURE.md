# Architecture

## Two executables, one model

| Part | Files | Notes |
|---|---|---|
| Main simulator (no INET) | `SensorNode.*`, `BaseStation.*`, `Controller.*`, `PeriyarModel.*`, `MatlabRng.h`, `Messages.msg`, `PeriyarValidation.ned`, `Makefile` | built by `build.cmd` / `build.sh`; runs every abstract configuration |
| Wireless plugin (INET 4.7.0) | `wireless/RadioAdapter.cc`, `wireless/Makefile`, `PeriyarWireless.ned`, `wireless/cc2420.ini`, `wireless/pilot.ini` | built by `build_wireless.cmd` / `build_wireless.sh` into `wireless/libRLHybridWireless.dll`, loaded with `-l` by `run_wireless.sh` |

`communicationModel = "abstract"` (default) uses the MATLAB channel and energy model in `PeriyarModel`.
`communicationModel = "ieee802154"` sends every routing frame through `RadioAdapter` to INET's
`Ieee802154NarrowbandMac` and `Ieee802154NarrowbandScalarRadioMedium`; the routing logic is the same code.

## Modules

* **Controller**: owns the round clock, loads the scenario workload (`data/scenarios/<profile>_<N>/`), schedules one
  slot per report, keeps the slot and loss accounting, enforces the per-round MATLAB invariants, writes the
  per-round, per-report, metrics, summary and sensing-ledger outputs.
* **SensorNode**: the RL-Hybrid agent. State = 8 ternary features (6,561 states); actions = neighbours or the BS;
  ε-greedy tabular Q-learning (α 0.1, γ 0.9) with a sinkward rule, cluster heads and aggregation, TTL 15, variant C
  energy guard 0.8. In the wireless mode it also keeps a send queue, waits for the routing answer of each frame
  (matched by `txSeq`) and counts a hop as lost after `wirelessAckTimeout` (MAC fault handling).
* **BaseStation**: receives reports, answers frames, records delivery and delay.
* **PeriyarModel**: MATLAB-equivalent topology, link-quality draw and first-order energy model.
* **MatlabRng.h**: reproduces MATLAB random streams so the abstract model matches the MATLAB reference exactly.
* **RadioAdapter** (plugin): wraps routing frames for the INET MAC, reports each started MAC transmission and its
  outcome to the node, and measures CC2420 radio-state energy.

## Round and data flow

1. Round start (100 s simulated = 1 h environmental): the controller releases the scheduled reports of the round.
2. Cluster window (2 s) and route phase: each node chooses a next hop from its Q-table, sends, and learns from the
   outcome (delivered, lost, energy, next-hop value).
3. The BS records deliveries; the controller closes the round, checks energy closure and slot accounting, and writes
   the per-round row.
4. Event-aware option (`W_EventAware`): reports are classed routine / warning / critical from
   `data/events/<profile>_<N>.csv` (deadlines 100 / 10 / 2 s) and critical reports get priority.

## Configurations (`omnetpp.ini`)

* MATLAB validation: `ReferenceCheck`, `SmokeSeed42`, `FiveSeeds`, `Check_MatlabModeSeed42`, `Audit_*`.
* Scaling: `Periyar*_RelayScaling`, `Ctrl50/100/250/500`, `Place250`.
* V2 and 200-node development: `V2_*`, `V2_200Node_*`.
* Environmental (abstract): `V2_200Node_Environmental` (N = 200 or 500; scenario water, effluent, air, soil, mixed).
* Wireless: `W_Common`, `W10_Smoke`, `W_Environmental`, `W_EventAware`, `W_ScenarioPlacement`, `W_FixedDensity`,
  `W_FeedbackAck`; pilot tests in `wireless/pilot.ini`.

## Energy accounting

Abstract-model energy, the 2 J reference ledger, CC2420 radio-state energy and sensing energy are kept separate; see
`PROJECT_REPORT.md` section 7.

## Tools (`tools/`)

* Data: `convert_kspcb.py`, `verify_kspcb.py`, `verify_loader.py`, `build_event_annotations.py`.
* Verification: `compare_with_matlab.py`, `compare_reference.py`, `compare_v2.py`, `verify_run.py`,
  `verify_scaling.py`, `verify_controlled.py`, `check_wireless_pilot.py`.
* Analysis and figures: `environmental_200node.py`, `research_upgrade.py`, `wireless500.py`, `scaling_table.py`,
  `v2_scaling.py`, `five_seed_table.py`, `opt200.py`, `diagnose_mechanism.py`, and others.
* Run helpers: `run_measured.ps1`, `run_measured_v2.ps1`.
