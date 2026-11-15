# Research upgrade: IEEE 802.15.4 communication, physical energy model, event-aware RL-Hybrid

Project `RLHybrid_Scalability_Experiment`, OMNeT++ 6.4.0 + INET 4.7.0, 13 Nov 2026. All new output is in
`results_research_upgrade/`; `results_environmental/`, `results_environmental_500/`, the MATLAB project and the KSPCB
workbook were not written. Protection: 21 source/config files backed up in `archive/research_upgrade_2026-11-13/before/`
(`*.bak`) and SHA-256 of 3,719 files in `archive/research_upgrade_2026-11-13/SHA256_before.txt` (checked in section 13).

## 1. Current architecture

One OMNeT++ project and one environmental network architecture with a selectable communication model:

| `communicationModel` | network | data frames | status |
|---|---|---|---|
| `"abstract"` (default) | `PeriyarRiverNetwork` | `sendDirect`, MATLAB channel success bits | validated MATLAB reproduction, unchanged (byte-identical outputs, section 13) |
| `"ieee802154"` | `PeriyarWirelessNetwork` (`PeriyarWireless.ned`) | INET 802.15.4 MAC/PHY to the MAC address of the chosen next hop | new |

* `Controller` (round phases, workload, topology, ledgers, outputs), `SensorNode` (tabular Q-learning RL-Hybrid with the
  variant C energy guard) and `BaseStation` are the same C++ classes in both models. The wireless hosts
  (`WirelessSensor`, `WirelessBaseStation`) wrap them with INET's `Ieee802154NarrowbandInterface`, an energy meter and
  `RadioAdapter`.
* The main simulator `RLHybrid_Scalability_Experiment.exe` does not link INET: abstract runs and the MATLAB regressions
  never load it. INET code lives only in the plugin `wireless/libRLHybridWireless.dll` (`RadioAdapter`, `PilotSource`),
  loaded with `-l` by `run_wireless.sh`. `PeriyarWireless.ned` names INET types in full, so NED loading without INET on
  the NED path still works (resolved lazily).
* New or changed files: `Controller.cc/.h`, `SensorNode.cc/.h`, `BaseStation.cc/.h`, `Messages.msg`, `PeriyarModel.cc/.h`,
  `PeriyarValidation.ned` (new parameters with defaults = previous behaviour), `PeriyarWireless.ned`, `omnetpp.ini`
  (new `W_*` configs at the end), `wireless/` (plugin source, Makefile, `cc2420.ini`, `pilot.ini`), `build_wireless.*`,
  `run_wireless.sh`, `tools/check_wireless_pilot.py`, `tools/build_event_annotations.py`, `tools/research_upgrade.py`,
  `data/events/` (derived), `README.md` (one section).

## 2. INET installation and compatibility status

* INET 4.7.0 (the INET release for OMNeT++ 6.x) was already installed in the OMNeT++ 6.4.0 workspace
  (`<OMNETPP_ROOT>/samples/inet-4.7.0`, 21 Oct 2026) but not built. It was built in this session with the official
  procedure (`source setenv` in the OMNeT++ shell, `make MODE=release -j8` in the INET folder): 0 errors, about 22 min,
  `src/libINET.dll` 181 MB. The earlier partial debug build, the OMNeT++ installation, the toolchain and other projects
  were not changed; no second OMNeT++ was installed; no workspace-wide build was started.
* Status: **working**. The plugin builds against it (`build_wireless.cmd`), the pilot and the RL network run on it.

## 3. Wireless model implemented

Path of every data frame: RL node logic -> `RadioAdapter` (wraps the frame in an INET `Packet` with a `cPacketChunk`,
`MacAddressReq` = MAC address of the next hop the agent chose, protocol EtherType 0x88B5 "local experimental") ->
`DropTailQueue` (100) -> `Ieee802154NarrowbandMac` (unslotted CSMA/CA, MAC ACK, 3 retries) -> scalar radio and radio
medium -> receiver MAC (address filter, duplicate filter, ACK) -> adapter -> RL node.

* **Real next hop.** The action the agent selects is the MAC destination. Data frames never use `sendDirect` in this
  mode. Collisions, hidden nodes, capture and noise are decided by INET's medium and receivers, not by the RL code.
* **Outcome of a hop.** Success = the next hop's logic accepted the frame. Failure = INET dropped it at the sender
  (retry limit after missing MAC ACKs, channel-access failure after 4 CSMA backoffs, queue overflow), reported by the
  adapter from INET's `packetDropped`/`linkBroken` signals. A 20 s safety timer raises an error if neither arrives.
* **Routing feedback (audited).** What still bypasses the radio in 802.15.4 mode:
  1. per accepted hop, the receiver's answer (accepted / could not afford reception, residual energy, load, next-hop
     value for the Q-learning bootstrap) as a zero-delay `LinkAck` at the moment of acceptance (`SensorNode.cc`);
  2. the agent's candidate checks read neighbours' residual energy, load and availability directly, as in MATLAB;
  3. round start commands from the controller (round synchronisation, not network traffic).
  The abstract model's separate value feedback (`ValueFeedback`) is not used in this mode. Sending (1) as separate
  radio frames would change the hop-outcome logic (a lost feedback frame would need its own timeout and retry design),
  a major redesign that was not made. Its airtime and energy are modelled instead with `W_FeedbackAck`: the 6 bytes
  (energy 1 B, load 1 B, next-hop value 2 B, 802.15.4e header IE 2 B) ride on an enhanced MAC ACK (40 -> 88 bit, ACK
  wait 560 -> 752 us) inside INET, so the extra airtime, energy and collisions are real while the values still arrive at
  acceptance. Item (2) would need periodic hello frames; its cost is estimated in section 16.
* **Concurrency.** All decisions of a phase start concurrently at uniform offsets in [0, 2 s) (controller RNG); each
  node sends one frame at a time and queues the rest (FIFO; class priority with ageing in the event-aware option); a
  phase ends when all its frames have ended. Q-values are updated immediately at the hop outcome.
* **Frame size.** Routing header 6 B + report payloads (dataset `m2_payload_bytes`), at most 118 B MAC payload
  (127 B PSDU - 9 B MAC overhead). INET does not enforce this limit (pilot P5b sends a 128-byte MPDU), so the RL layer
  enforces it: route bundles are split into frames that fit, a larger frame raises an error.
* **Duplicates.** INET's MAC sequence filter plus the RL `txSeq` filter (a frame retransmitted after a lost MAC ACK is
  counted once).
* **Dead nodes** switch their radio off at the next round start.
* **Agent link prior (`wirelessLinkPrior`).** MATLAB's prior `distancePriorLQ` is the expected link quality of the
  abstract channel law (usable links up to about 240 m). On 802.15.4 it is replaced by the same construction for the
  simulated channel: the reception ratio of an isolated link of length d for a 127-byte PSDU, computed from INET's own
  parameters (breakpoint path loss, background noise, transmitter power, receiver sensitivity and SNIR threshold) and the
  O-QPSK BER of IEEE 802.15.4-2006 E.4.1.8, clipped to MATLAB's bounds [0.1, 0.95] (`<run>-link_prior.csv`: PRR 0.998 at
  102 m, 0 at 103 m). `"matlabDistance"` keeps the abstract law and was run as a sensitivity case (section 10).
* **Unchanged:** state (8 ternary features, 6,561 states), actions, reward, update rule, alpha 0.1, gamma 0.9, epsilon
  schedule, MIN_LQ 0.5, link estimator, energy guard 0.8 (variant C), cluster heads and aggregation, TTL 15, the 2 J
  battery and the 200 uJ death threshold.

**Pilot (Stage 2, `wireless/pilot.ini`, `tools/check_wireless_pilot.py`): 58/58 checks passed.**

| pilot | set-up | result |
|---|---|---|
| P1 | 2 nodes 30 m, 20 frames | 20/20 delivered, 1 transmission and 1 MAC ACK per frame, delay 2.8-3.5 ms |
| P2 | 2 nodes 150 m (out of range) | 0 delivered, 80 transmissions = 20 x (1 + 3 retries), 20 retry-limit drops |
| P3 | 3 nodes in range, 2 senders at the same instants (+/-100 us) | 40/40 delivered, 64 backoffs for 43 transmissions (CCA deferrals), 3 retransmissions |
| P4 | hidden nodes 180 m apart, receiver in the middle | 29 receptions with bit errors, 101 transmissions, 33/40 delivered, 7 lost |
| P5 | payload 10 / 34 / 60 / 118 B | airtime 800 / 1568 / 2400 / 4256 us = 192 us + (9 + payload) x 32 us exactly |
| P5b | payload 119 B | sent by INET (no PSDU check) -> enforced by the RL layer |
| P6 | 10 frames queued at once | queue length 10, delays 3.5 ... 35.0 ms, strictly increasing |
| energy | every node of every pilot | state times sum to the run time; sum(P x t) = adapter ledger = INET energy meter (1e-9 J) |

A 10-node smoke test (`W10_Smoke`, MATLAB V2 layout) showed that the V2 layout is partitioned at 0 dBm: nodes 1-5 have no
neighbour within the 102 m radio range of node 6 (110 m gap), so their reports cannot reach the BS; nodes 6-10 deliver
over up to 5 hops.

## 4. MAC/PHY configuration

| item | value | source |
|---|---|---|
| PHY | 2.4 GHz O-QPSK DSSS, 250 kbit/s, preamble + SFD + PHR 6 B (192 us) | INET `Ieee802154NarrowbandRadio` (802.15.4-2006) |
| MAC | non-beacon unslotted CSMA/CA, MAC ACK (40 bit), macMaxFrameRetries 3, macMaxCSMABackoffs 4, BE 3-5, backoff period 320 us, CCA 128 us, turnaround 192 us, ACK wait 560 us, MAC header + FCS 72 bit, MTU 118 B | INET `Ieee802154NarrowbandMac` defaults |
| queue | DropTailQueue, 100 packets | INET default |
| TX power | 0 dBm (1 mW) | CC2420 datasheet SWRS041c, maximum PA level |
| sensitivity | -95 dBm | CC2420, typical (PER 1 %) |
| CCA threshold | -77 dBm, CCA mode 3 (energy or valid frame) | CC2420 CCA_THR reset value; INET reception state = mode 3 |
| SNIR threshold | -8 dB, then the BER-based packet error model | INET default (`Ieee802154ErrorModel`) |
| radio powers (3.3 V) | RX/listen 62.04 mW (18.8 mA), TX 0 dBm 57.42 mW (17.4 mA), idle 1.4058 mW (426 uA), power-down 0.066 mW (20 uA), off 0.000066 mW | CC2420 datasheet SWRS041c, 25 C |
| random streams | RNG 0 PHY error draws, RNG 1 CSMA/CA backoffs, RNG 2 decision jitter; `seed-set = ${seed}` | `W_Common` |

## 5. Radio propagation and interference assumptions

* INET `Ieee802154NarrowbandScalarRadioMedium`: breakpoint path loss 40.2 dB + 20 log10(d) below 8 m, 58.5 dB +
  33 log10(d / 8 m) beyond (INET's 802.15.4 model, 802.15.4-2006 Annex E); background noise -96.616 dBm; isotropic
  antennas; all nodes and the BS at height 0 in the 600 x 50 m strip. Resulting radio range: about 102 m (sensitivity
  limit; SNR there 1.6 dB).
* No shadowing or fading (deterministic link budget per distance); no obstacles, no water-surface reflection.
* Interference: SNIR from all overlapping transmissions above -120 dBm (`minInterferencePower`), scalar (no spectral
  shape). The O-QPSK error model treats interference like noise; it is more tolerant to equal-power collisions than the
  CC2420's measured co-channel rejection (+3 dB SIR for PER 1 %), so capture is somewhat optimistic.
* Receiver sensitivity is a hard reception threshold (INET's simplification of the 1 % PER definition).
* The BS is mains powered (no energy consumer) and uses the same radio.

## 6. Energy model changes

Two separate ledgers; nothing is counted in both and they are never added together:

1. **2 J reference ledger (decisions, node death, lifetime).** The validated first-order model (Eelec 50 nJ/bit,
   Efs 10 pJ/bit/m2, Emp 0.0013 pJ/bit/m4, E_DA 5 nJ/bit, 2 J per node, death below 200 uJ) on the actual frame bits
   (payload + 21 B PHY/MAC/routing overhead). On 802.15.4 every MAC transmission that actually starts is charged once
   (the adapter reports each one; retries included; a frame dropped before it reached the air is refunded); RX energy is
   charged once per accepted frame. Checked: per node, charged transmissions = INET `nbTxFrames` (10-node test, all
   nodes); per round, energy conservation and the MATLAB invariants are enforced in every run.
2. **Physical model (reported, never drives decisions).**
   * Radio: INET `StateBasedEpEnergyConsumer` with the CC2420 powers (section 4), integrated by the adapter from the
     actual radio-state changes (off, sleep, switching, RX idle, RX busy, receiving, TX idle, transmitting), split into
     each round's active window and the gap between rounds, and cross-checked against INET's `IdealEpEnergyStorage`.
     TX = transmitting time (data and ACKs); RX = receiving time (addressed, overheard, ACKs); CCA = backoffs x 128 us;
     idle listening = the rest of the RX-mode time in the active windows. ACK TX/RX energy = ACK count x 352 us airtime.
   * Duty cycle (assumption): one round = 1 h of environmental time (`sensor_profiles.json`); the radio listens during
     the measured active window and sleeps (power-down, 20 uA) for the rest of the hour. The simulation itself keeps
     receivers on between rounds; that always-on energy is also reported.
   * Sensing and processing: the dataset ledger `m2_sensing_mJ` (sensor currents from `sensor_profiles.json`, each
     marked VERIFIED or ASSUMPTION there), split into sensing and MCU processing (5 mA x 10 ms per sample at 3.3 V,
     ASSUMPTION). Never charged to the 2 J battery.
   * Aggregation: first-order E_DA (part of the 2 J ledger).
   * Battery: no capacity is assumed. Lifetime is given as rounds and days per joule of usable capacity
     (`lifetime_vs_capacity.csv`); the 2 J reference is not a physical battery.

**Time mapping (audited).** One environmental round = 1 h (`sensor_profiles.json`, `round_hours`). In OMNeT++ a round
is scheduled every 100 s (`roundPeriod`). Inside a round everything runs in real time: decisions start in 2 s windows,
frames take their real airtime (192 us + 32 us per byte; 1.57 ms for a 34-byte payload), CSMA/CA backoffs (320 us
units), CCA (128 us), turnaround (192 us), MAC ACK waits (560 us), retries and queue waits are simulated as they occur.
A round's active window (round start until the last frame of the round has ended) lasts about 4 s; nothing happens
between rounds except the occasional MAC retry or ACK just after the window. The compression of the remaining 96 s
(instead of 3,596 s) was tested: the same 20 rounds with `roundPeriod = 3600 s` give identical per-round results,
identical fates, hops and delays (latency differs by < 1e-10 s from rounding of larger absolute times), identical
radio active time (16,212 node-s), active-window energy (1,000.27 J) and transmissions (17,761); only the idle gap grows
(385,788 -> 14,455,788 node-s). Energy for the elapsed environmental time is therefore computed per node and round as

* measured: CC2420 energy of every radio state in the active window, plus any late activity after it;
* plus the rest of the hour in an assumed state: **listening** (non-beacon routers keep receivers on: 62.04 mW, about
  223 J per node-hour) or **power-down** (synchronised duty cycle: 20 uA, 0.24 J per node-hour).

The 100-s idle gap that the simulation itself spends listening is not used for any physical figure. The 2 J ledger is a
separate first-order count of transmissions and receptions (no time component), and sensing is a separate per-hour
ledger; the three are never added to each other. No physical battery life is claimed (no battery capacity is modelled).

## 7. Environmental event detection

`tools/build_event_annotations.py` -> `data/events/<dataset>.csv` (one row per report; datasets unchanged):

* **Warning** = a valid round value exceeds a documented threshold of its sensor profile: CPCB water-quality criteria
  (pH 6.5-8.5, EC <= 2,250 uS/cm, DO >= 4 mg/L), Environment (Protection) Rules 1986 Schedule VI (effluent pH, BOD,
  COD, NH3-N), India NAAQS 2009 (PM2.5, PM10, NO2, SO2, O3, CO); soil moisture limits are marked ASSUMPTION. This is the
  dataset's `alarm_flag`, recomputed and checked for all 1.24 M rows.
* **Critical** (simulation rule) = the same threshold exceeded in >= 3 consecutive distinct samples (a held KSPCB grab
  sample counts once).
* **Event report**: the 10 B application header (node, sequence, round = timestamp, profile = scenario, alarm/priority
  flags) + trigger field id (1 B) + trigger value (2 B) in the event-aware option; the annotation also lists unit,
  threshold rule, its source, quality flag and sample time. Trigger = the rule with the largest relative exceedance.
* **Deadlines** (simulation targets, from generation): critical 2 s (one decision window), warning 10 s, routine 100 s.

| dataset (200 nodes) | reports | routine | warning | critical |
|---|---|---|---|---|
| water | 68,700 | 27,920 | 18,120 | 22,660 (EC above 2,250 uS/cm triggers 37,560 of the 40,780 events) |
| effluent | 99,306 | 82,589 | 4,125 | 12,592 |
| air | 100,000 | 35,213 | 5,440 | 59,347 (PM2.5 above 60 ug/m3 in 59,087 of the 64,787 events) |
| soil | 25,135 | 24,636 | 235 | 264 |
| mixed | 73,306 | 42,288 | 7,517 | 23,501 |

## 8. Priority-aware RL-Hybrid behaviour

One option, `eventAware = true` (`W_EventAware`); the Q-learning state, reward and update rule are unchanged:

* a critical report is not held for cluster aggregation: its source routes it at once in the cluster phase;
* frames waiting at a node leave by priority = class (critical 2, warning 1, routine 0) + 1 per second of waiting
  (ageing, so routine frames cannot starve); ties in arrival order;
* in route bundles, critical and then warning reports take the first frames;
* event reports carry 3 extra bytes (trigger field id and value).

Variant C runs load the same annotations only to label reports; behaviour and frames are identical to running without
them (checked, section 13).

## 9. Topology improvements

* `placement = "common"` (default): one topology per seed for every scenario (MATLAB layout for nodes 1-10, extra-node
  stream for the rest), so scenario comparisons are paired.
* `placement = "scenario"` (`W_ScenarioPlacement`), SYNTHETIC layouts in the same 600 x 50 m area, no GPS coordinates:
  water along the river centreline (|y - 25 m| <= 5 m); effluent in five outfall clusters on the near bank (+/-30 m);
  air on a regular grid over the whole area; soil on a regular grid over the near-bank half. The 10 nodes that replay
  the real KSPCB stations keep their positions; mixed = every node by its own profile.
* Fixed area vs fixed density (802.15.4 only: in the abstract model the channel law scales with the area length):
  500 nodes in 600 x 50 m (density x 2.5) vs 500 nodes in 1500 x 50 m with the BS at (1500, 25) (`W_FixedDensity`,
  same density as 200 nodes in 600 m). With about 100 m hops, 1500 m needs at least 15 hops = the unchanged TTL.

## 10. 200-node results

**Completed on IEEE 802.15.4 (200 nodes, mixed scenario, 500 rounds; status as of 13 Nov 2026, 19:45):**

| experiment | seeds completed | label |
|---|---|---|
| variant C, link-budget prior (`W_Environmental`) | 42, 43, 44, 45, 46 | **five-seed** |
| event-aware option (`W_EventAware`) | 42 | **single seed** (43-46 were started and interrupted; nothing reported from them) |
| variant C, MATLAB prior (sensitivity) | 42 | single seed |
| water, effluent, air, soil scenarios on 802.15.4 | none | **not run** |
| smoke tests (20 rounds: event-aware, placement, range filter; 5 rounds: 500 nodes) | 42 | short smoke tests, not results |

Seed 42 is the earlier run, reused after checking its configuration (config, iteration variables, controller and radio
parameters in its .sca) and recording its checksums (`wireless_N200/SHA256SUMS.txt`); a rerun of its first 20 rounds
with the current binaries reproduces it byte for byte. Seeds 43 and 45 first failed with the INET MAC fault of section
15 and were rerun with the fix; the rerun equals the failed run up to the fault (rounds 1-485 and 1-83).

Per seed (mixed, 500 rounds):

| seed | abstract PDR | 802.15.4 variant C PDR | 802.15.4 event-aware PDR | 802.15.4 variant C hops | 2 J ledger spent (802.15.4) |
|---|---|---|---|---|---|
| 42 | 45.98 % | 89.51 % | 94.30 % | 7.63 | 24.27 J |
| 43 | 45.70 % | 90.24 % | - | 7.50 | 23.91 J |
| 44 | 42.47 % | 89.97 % | - | 7.68 | 24.47 J |
| 45 | 45.80 % | 89.84 % | - | 7.83 | 24.41 J |
| 46 | 45.45 % | 89.42 % | - | 7.64 | 24.40 J |

Five seeds, mean +/- SD, and paired difference 802.15.4 - abstract with 95 % t-interval (n = 5):

| metric | abstract | 802.15.4 variant C | paired difference [95 % CI] |
|---|---|---|---|
| PDR | 45.08 +/- 1.47 % | **89.80 +/- 0.34 %** | +44.72 [+42.74, +46.70] points |
| mean delivered hops | 5.41 +/- 0.22 | 7.66 +/- 0.12 | +2.25 [+1.86, +2.64] |
| relay frames received by the busiest 10 % of nodes | 35.3 +/- 1.3 % | 44.9 +/- 1.3 % | +9.6 [+7.2, +11.9] points |
| 2 J ledger spent (of 400 J) | 29.35 +/- 1.11 J | 24.29 +/- 0.23 J | -5.06 [-6.41, -3.71] J |
| energy per delivered report | 0.888 +/- 0.032 mJ | 0.369 +/- 0.004 mJ | -0.519 [-0.558, -0.481] mJ |
| first node failure | none in 500 rounds | none in 500 rounds | - |
| end-to-end delay mean / p95 | not modelled | 3.058 +/- 0.004 s / 3.965 s | - |
| queueing delay per report | not modelled | 2.08 +/- 0.14 ms | - |
| MAC delay per hop (n = 4) | not modelled | 5.17 +/- 0.04 ms | - |
| lost: channel or MAC / TTL | - | 7,109 +/- 286 / 371 +/- 133 | - |
| hops lost inside a receiver MAC (section 15) | - | 0.4 +/- 0.5 (2 in 5 runs) | - |

The 802.15.4 runs differ from one another by less than 1 point of PDR; the two models differ by 45 points (section 12).
Radio-aware prior vs MATLAB prior (seed 42): 89.51 % vs 78.71 % PDR; with the MATLAB prior the agent first tries links
of 100-240 m the radio cannot close (36 % of the decisions of the first 20 rounds; hop success 98-100 % up to 100 m,
23 % at 100-110 m, 0 beyond, `figS2`) and reaches 89.9 % only in rounds 451-500 (`figS1`).

MAC, link quality and queues (802.15.4 variant C, mixed, mean +/- SD over 5 seeds; RSSI, SNIR and node queues over 4
seeds, the first run predates them):

| metric | value |
|---|---|
| MAC data transmissions | 438,600 +/- 9,270 |
| retransmissions | 70,950 +/- 1,950 (16.2 %) |
| transmissions without MAC ACK | 75,300 +/- 2,200 (17.2 %) |
| drops: retry limit / channel access (4 CSMA backoffs) / queue overflow | 4,358 +/- 285 / 1,383 +/- 29 / 0 |
| receptions with bit errors at any radio (collision proxy) | 1.83 M +/- 0.02 M |
| channel utilisation seen by the nodes (busy + receiving + TX over the active window) | 12.44 +/- 0.10 % |
| active window per round | 4.055 s |
| RSSI of frames accepted by the BS / by nodes | -68.6 +/- 4.8 dBm / -82.0 +/- 0.3 dBm |
| mean per-frame minimum SNIR at the BS | 26.8 +/- 4.8 dB |
| largest node queue / largest MAC interface queue | 8.5 +/- 7 frames / 1 frame (one frame at a time per node) |

Energy per node and round (802.15.4 variant C, mixed, mean of 5 seeds; one round = 1 h, section 6):

| component | J per node-round | note |
|---|---|---|
| CC2420 TX (data + ACKs) | 0.00053 | measured state time x 57.42 mW |
| CC2420 RX (frames, incl. overheard and ACKs) | 0.0305 | measured |
| CCA | 0.00005 | backoffs x 128 us x 62.04 mW |
| idle listening in the active window | 0.220 | measured; 88 % of the active-window radio energy |
| radio, active window total | 0.251 | measured |
| rest of the hour: power-down (duty-cycle assumption) | 0.237 | 20 uA x 3.3 V |
| **radio, duty-cycled** | **0.489** | |
| radio, listening all hour (non-beacon router) | 223.3 | 62.04 mW x 3,600 s |
| sensing (dataset ledger) | 87.5 | mixed average: effluent analyser 240 J/h (ASSUMPTION), air PM sensor 60 J/h (VERIFIED) + gas sensors; water 0.61, soil 0.01 |
| processing (MCU, ASSUMPTION) | 0.00058 | 5 mA x 10 ms per sample |
| 2 J ledger TX + RX (first-order) | 0.00024 | the reference model's radio cost |

Checks in all 7 completed 500-round 802.15.4 runs: radio-state integration = INET energy meter, and per node the 2 J
ledger TX charges = INET MAC transmissions.

**Event-aware option vs variant C (802.15.4, mixed, seed 42, 500 rounds, paired; single seed, no interval):**

| metric | variant C | event-aware | difference |
|---|---|---|---|
| PDR, all reports (73,306) | 89.51 % | 94.30 % | +4.79 points |
| critical reports (23,501): PDR | 91.33 % | 97.02 % | +5.69 points |
| critical: mean delay | 3.05 s | 1.06 s | -1.99 s |
| critical: delivered within 2 s | 0.11 % | **94.17 %** | +94.06 points |
| warning reports (7,517): PDR (= within 10 s) | 88.95 % | 93.24 % | +4.30 points |
| routine reports (42,288): PDR (= within 100 s) | 88.60 % | 92.98 % | +4.38 points |
| routine: mean delay / largest queue wait | 3.06 s / 0.163 s | 3.09 s / 0.135 s | no starvation |
| 2 J ledger spent / per delivered report | 24.27 J / 0.370 mJ | 25.93 J / 0.375 mJ | +6.8 % / +1.4 % |
| CC2420 radio, duty-cycled, per node-round | 0.4888 J | 0.4900 J | +0.2 % |
| sensing energy | 87.53 J | 87.53 J | identical (same samples) |
| MAC transmissions / retransmissions | 445,817 / 73,606 | 501,200 / 64,950 | +12 % / -12 % |

The first 100 rounds of this run equal the earlier 100-round event-aware run byte for byte. The variant C seed-to-seed
SD of critical PDR is 0.28 points, so a +5.7-point gain on one paired seed is very unlikely to be noise, and the deadline
effect is structural (critical reports leave in the cluster phase instead of waiting for aggregation and the route
phase). A confidence interval needs seeds 43-46.

Placement (20-round smoke only, mixed seed 42): scenario-specific synthetic layout 85.8 % PDR vs common topology 86.0 %.

## 11. 500-node results

* **Abstract model (existing results, reproduced byte for byte, section 13):** PDR water 43.8 +/- 1.0 %, effluent
  44.7 +/- 0.9 %, air 45.1 +/- 1.1 %, soil 40.5 +/- 0.5 %, mixed 43.5 +/- 0.9 % (seeds 42-46); hops 5.5-6.3; no node
  failure in 500 rounds. Relative to 200 nodes: 1.4-2.0 points lower PDR, longer routes, 13-15 % more energy per report.
* **IEEE 802.15.4, 500 rounds, fixed area (600 x 50 m), mixed: seed 42 complete; seeds 43-46 stopped at round 96 (not reported).**
  - Configuration: `W_Environmental` run #29 (N = 500, mixed, seed 42, variant C, link-budget prior, TTL 15, CC2420,
    `rangeFilter = "interferenceRange"`, MAC no-outcome timeout 1 s), result dir `results_research_upgrade/wireless_N500`.
  - Binaries: simulator SHA-256 `9c85e8de20da02bdde7f...` (13 Nov 09:31, section-15 fix), plugin `libRLHybridWireless.dll`
    `9b3d42a6f6f4ac6123b5...`. No code, MAC, radio or routing change was made for the 500-node runs.
  - Seed 42 ran alone, detached from the Claude session, 15 Nov 16:07-21:30: 500/500 rounds, exit 0, no `<!> Error`,
    energy closure, slot accounting and per-round invariants OK. Radio energy equals the INET meter; ledger TX charges equal
    MAC TX. No receiver-MAC frame loss occurred (`framesLostNoOutcome` = 0).
  - Seeds 43-46 (runs #34, #39, #44, #49) were started 15 Nov 21:31, four in parallel, and stopped at 22:46
    after 96 of 500 rounds when the project was frozen (final snapshot, v1.0.0). Their partial outputs are in
    `interrupted_runs/N500-W_Environmental-mixed-seed<N>-20261115-stopped-round96/`; they are not results.
  - Earlier attempts are not used: one run on the binary without the section-15 fix, and one interrupted at round 47
    (`interrupted_runs/`).
  - Analysis: `python -P tools/wireless500.py` writes `wireless_N500/analysis/` (per_seed.csv, summary.csv, report.txt).
    Mean, SD and CI appear only once two or more seeds are complete.

| seed 42, 500 rounds, 500 nodes | 802.15.4 | abstract (same seed, `results_environmental_500`) | difference |
|---|---|---|---|
| PDR (delivered / scheduled) | 49.84 % (91,085 / 182,752) | 44.54 % (81,402) | +5.30 points |
| lost: channel / MAC | 83,162 | 101,323 | -18,161 |
| lost: TTL | 8,505 | 27 | +8,478 |
| critical / warning / routine PDR | 51.42 / 49.76 / 49.02 % | 45.28 / 44.11 / 44.22 % | +6.14 / +5.65 / +4.80 |
| critical reports within 2 s | 0.004 % (variant C, not event-aware) | not modelled | - |
| mean delivered hops | 7.05 | 6.17 | +0.89 |
| end-to-end delay mean / p95 | 3.09 s / 4.02 s | not modelled | - |
| reference ledger: spent / residual | 58.91 J / 941.09 J (of 1,000 J) | 78.71 J / 921.29 J | -19.80 J |
| ledger energy per delivered report | 0.647 mJ | 0.967 mJ | -0.320 mJ |
| alive / dead nodes after 500 rounds | 500 / 0 (no node failure) | 500 / 0 | 0 |

  - MAC and link: 1,283,870 MAC transmissions, 33.8 % retransmissions, 36.5 % without a MAC ACK. 34,398 frames hit the
    retry limit, 38,565 failed channel access, none overflowed the queue. INET marked 36.1 M receptions as
    corrupted. MAC delay per delivered hop 9.17 ms (200 nodes: 5.17 ms).
  - Signal and load: RSSI at the BS -67.3 dBm (SNIR 26.4 dB), mean node RSSI -78.8 dBm, channel utilisation 29.3 %
    of the active window (4.17 s per round). Queues stay short: at most 6 frames in a node queue and 1 in the MAC
    queue; mean queueing delay 5.2 ms.
  - CC2420 radio energy per node-round:
    - active window: 0.258 J (idle listening 0.184 J, RX 0.074 J, TX 0.0006 J);
    - one 1 h round, duty-cycled (power-down outside the window): 0.496 J;
    - one 1 h round, always listening: 223.3 J.
  - Comparison with the abstract model:
    - The abstract per-hop link loss does not depend on load, so its PDR barely changes from 200 to 500 nodes (section 12).
      On 802.15.4, 2.5 times more nodes contend in the same 2 s decision windows. MAC losses rise (missed ACKs, retry-limit
      and channel-access drops) and the 200-node advantage of +44.7 points shrinks to +5.3 points.
    - Failed hops make the agent pick other neighbours, so routes get longer (7.05 hops) and 8,505 reports run out of
      TTL; the abstract model loses only 27 that way.
    - The ledger is charged per started MAC transmission and per accepted frame (section 6), unlike the abstract
      charging, so the lower energy per report reflects the charging rules as well as the network.
    - Critical reports are not prioritised in variant C, so almost none arrive within 2 s; the event-aware option was not
      run at 500 nodes.
  - Runtime and resources: 322.4 min wall time (5.37 h) for one run alone, peak working set 168.7 MB, about 2.43 G events.
  - Limitations: one seed only (no spread); fixed-area layout only, the fixed-density layout and 5 s windows were not run
    at 500 rounds. The first rounds ran on battery, the rest on AC; this affects wall time, not results.

* **Earlier 5-round smoke runs (rounds 1-5, single seed; direction only):**

| network | delivered | lost: MAC / channel | lost: TTL |
|---|---|---|---|
| 200 nodes, 600 x 50 m | 80.9 % | 17.2 % | 1.9 % |
| 500 nodes, 600 x 50 m (fixed area, density x 2.5) | 37.9 % | 61.3 % | 0.8 % |
| 500 nodes, 1500 x 50 m (fixed density), BS at (1500, 25) | 32.9 % | 40.9 % | 26.3 % |

  Fixed area: 2.5 times more nodes decide within the same 2 s windows, so contention rises: in the 5 rounds 44 % of the
  12,532 transmissions got no MAC ACK, 589 frames hit the retry limit and 330 failed channel access. Fixed density: the
  per-node neighbourhood is that of 200 nodes, but routes to a BS 1.5 km away need 15 or more 100 m hops, the unchanged
  TTL. Density and scale therefore fail for different reasons (contention vs hop budget). These are learning-phase rounds
  of single runs and only show the direction. The planned check of the contention explanation (500 nodes with 5 s decision
  windows) was not run.

## 12. Comparison with the previous abstract model

The 802.15.4 model changes PDR from 45.1 % to 89.8 % (mixed, 5 seeds, paired +44.7 points). This is not an artefact; it follows from the two
channel models:

* The abstract (MATLAB) channel draws every link outcome from `lq = clip(1 - d / 480 m + U(-0.15, 0.15), 0.1, 0.95)` with
  no retransmission: a 50 m hop fails 12 % of the time, a 100 m hop 21 %, a 200 m hop 42 %, and RL-Hybrid's 5-hop routes
  lose about half of the reports.
* On 802.15.4 a hop within the 102 m range succeeds in 98-100 % of cases thanks to CSMA/CA, MAC ACK and up to 3
  retransmissions, and a hop beyond it always fails (`figS2`). With the link-budget prior the agent only uses links that
  exist; routes become longer (7.7 hops) and the remaining losses are MAC failures under contention and TTL expiry.
* Energy per delivered report falls by more than half (0.89 -> 0.37 mJ in the 2 J ledger, 5 seeds): short hops avoid the d^2/d^4 amplifier term, and
  far fewer frames are lost after being paid for. Retransmissions are charged; they cost less than the abstract losses.
* The abstract model has no time or queueing; its "path delay" is a sum of serialization terms (37 ms). On 802.15.4 the
  end-to-end delay of 3.1 s is dominated by the round structure (2 s cluster window, then the route phase), not by the
  radio (queueing 2 ms per report).
* Exact MATLAB equality is expected and obtained only for the preserved abstract configurations (section 13).

## 13. Reproducibility

* Random streams: topology, channel and agent use the MATLAB twister streams of the run seed; on 802.15.4 the OMNeT++
  streams (RNG 0 PHY errors, 1 CSMA/CA backoffs, 2 decision jitter) are seeded by the run seed (`seed-set = ${seed}`).
  The 802.15.4 run's workload and topology files are byte-identical to the abstract run with the same seed (paired).
* Abstract model after all changes (`validation_v11/`): 50-node MATLAB validation stages B-E passed (20 + 55 checks,
  51/51 files byte-identical with the archived v1 baseline); MATLAB V2 10-node 95/95 checks; the 50 environmental runs
  (200 and 500 nodes) rerun and compared with `results_environmental*/`: 300/300 and 300/300 files identical (CSV and text
  outputs byte for byte, scalar lines of the .sca files); log `validation_v11/logs/final_validation_summary.txt`.
* 802.15.4 determinism across binaries and options: an independent 20-round rerun (rebuilt binary, event annotations
  loaded) reproduces rounds 1-20 of the 500-round run byte for byte (per-round counters and all 2,515 reports with fates,
  hops and delays); loading the annotations changes no output (all CSVs and scalars identical); INET's
  `rangeFilter = "interferenceRange"` changes no output (only a 1e-14 relative rounding in the energy-meter cross-check).
* After the section-15 fix: the fixed binary reproduces rounds 1-20 of the stored seed-42 run byte for byte; the fixed
  reruns of seeds 45 and 43 equal the failed runs up to the fault (rounds 1-83 and 1-485, per-round counters byte for
  byte); the 500-round event-aware run equals the earlier 100-round event-aware run in rounds 1-100.
* Seed-to-seed spread of the 200-node 802.15.4 network (mixed, 5 seeds): PDR 89.80 +/- 0.34 %, energy per delivered
  report 0.369 +/- 0.004 mJ: the network is reproducible for a given seed and stable across seeds.
* Round length: 100 s and 3,600 s rounds give identical behaviour (section 6).
* Protection: SHA-256 of the 3,719 pre-task files: 3,702 unchanged; the 15 changed files are the intended sources,
  generated message code, the rebuilt simulator, `omnetpp.ini` and `README.md`. All result folders, the KSPCB workbook
  (both copies, SHA-256 cee7cae9...) and the MATLAB project (no file modified) are unchanged.

## 14. Performance and memory

| run | wall time | peak memory | note |
|---|---|---|---|
| abstract, 200 nodes, 500 rounds | 4.5-7 s | 62-71 MB | `results_environmental/runtimes.csv` |
| 802.15.4, 200 nodes, 500 rounds | 25.1 min (MATLAB prior: 20.9 min) | 106 MB | 378 M (314 M) events, about 250,000 events/s, 2 runs in parallel, earlier machine state |
| 802.15.4, 200 nodes, 500 rounds, batch | 2.0-2.4 h per run (seed 46: 125.8 min) | 95-103 MB | 4 runs in parallel on AC, about 47,000 events/s each (CPU at about half its base clock) |
| 802.15.4, 500 nodes, per round | 18 s (fixed area), 20 s (fixed density with the range filter, 27 s without) | 167 MB | 5-round runs |
| 802.15.4, 500 nodes, 500 rounds (fixed area, mixed, seed 42) | 322.4 min (5.37 h) | 168.7 MB peak | about 2.43 G events; ran alone, detached; battery at first, then AC |
| INET 4.7.0 release build | about 22 min | | once |

The 802.15.4 runs are bound by radio-signal events (every frame reaches every radio within the -120 dBm interference
range). On this laptop (i5-13420H, 4 performance + 4 efficient cores) the same run took 25 min early in the night but
about 2 h later: the CPU ran at roughly half its base clock even on AC with Windows set to Best performance (probably the
vendor power mode or charging/thermal limits; not changed). Benchmark (5 rounds, 200 nodes): 1 run 68 s, 2 parallel
74 s each, 4 parallel 86 s each, i.e. 3.2x the throughput of one run with 4 in parallel; ten parallel runs on battery
fell to about 30,000 events/s each. Recommended: 4 parallel runs on mains power. Memory is not a limit.

## 15. Bugs found and fixed

| found by | problem | fix |
|---|---|---|
| pilot run | ini `result-dir` is relative to the ini file, scalars went to `wireless/results_research_upgrade/` | `../results_research_upgrade/pilot` |
| P5 run 2 | INET keeps the EtherType protocol table per run: "Unknown protocol rlhybrid" from the second run in one process | register in every run's initialization |
| P3/P4 | scripted senders at exactly the same simulation time trip INET's same-start check | +/-100 us jitter (unsynchronised clocks); the check stays on |
| P1 checker | INET's 802.15.4 MAC sends data frames without `packetSentToLower`, so the adapter's TX counter was always 0 | counter deleted; INET `nbTxFrames` used |
| W10 | INET `StationaryMobility.initialX/Y` cannot be set at run time | position written to the host display tag (read as a double) |
| W10 | the mains-powered BS radio had an energy consumer without a source | consumer on battery nodes only |
| review | MAC retries were not charged in the 2 J ledger | one charge per started MAC transmission, refund if never on air |
| 200-node smoke | MATLAB's distance prior made 36 % of early decisions target nodes beyond radio range | link-budget prior (section 3) |
| build | `headerLength` is an integer parameter | read with `intValue()` |
| analysis | "always-on" radio energy included the idle tail after round 500 (the run continues to `sim-time-limit`) | counted within the 500 rounds only |
| batch | 10 parallel runs on a battery-powered laptop ran at 1/8 speed (30,000 events/s each) | batch stopped; documented plan with at most 4 runs on mains power |
| 200-node runs (seeds 45 and 43, rounds 84 and 486) | a hop never got an outcome: INET's `Ieee802154Mac` records the sequence number of a data frame that arrives while it is starting its own transmission (`TRANSMITFRAME`) and discards it as an FSM error; the sender's retransmission is then ACKed as a duplicate without being delivered, so the sender's MAC reports success while the next hop never receives the frame. Reproduced deterministically (same frame, same event number) with MAC logging | the hop is counted as a lost hop (`framesLostNoOutcome`) after `wirelessAckTimeout` = 1 s (longest MAC service about 0.44 s) instead of stopping the run; every answer carries its frame's sequence number so a late answer is ignored. Runs that completed before the fix never met this case and are identical (checked); the two failed runs were rerun |

## 16. Remaining limitations

* **Experiments not completed on 802.15.4:** the water, effluent, air and soil scenarios (20 variant C runs); the
  event-aware option for seeds 43-46 and the four other scenarios (24 runs); 500-round 500-node runs other than fixed-area
  mixed seed 42 (seeds 43-46 stopped at round 96; fixed density and 5 s decision windows not run); full placement runs; the `W_FeedbackAck` airtime run. All configurations exist;
  only compute time was missing (about 2 h per 200-node run on this laptop, roughly 12 h per 500-node run).
* Routing feedback (receiver answer, energy, load, next-hop value) still reaches the sender out of band at the moment
  the frame is accepted; its airtime can be modelled with `W_FeedbackAck` (6 bytes in an enhanced ACK; not yet run).
  Neighbour energy and load are read directly, as in MATLAB; a hello frame per node and round (17 B, 544 us) would cost
  about 0.03 mJ TX per node-round and about 1 % more channel time, and almost no extra RX energy because the CC2420
  draws the same 62 mW listening as receiving (estimate, not simulated).
* INET's 802.15.4 MAC can lose a frame that arrives while it starts its own transmission (section 15). It is counted
  as a lost hop (2 hops in 5 runs, about 1 in 1.1 million transmissions).
* INET scalar radio: deterministic path loss (no shadowing or fading), interference treated like noise (equal-power
  collisions are survived more often than with the CC2420's +3 dB co-channel rejection), sensitivity as a hard threshold,
  flat 2-D strip.
* No 802.15.4 LQI in INET; RSSI and SNIR of accepted frames are recorded (rebuilt binary; the first full run predates it).
* Energy: node death still uses the first-order 2 J ledger (validated reference); the CC2420 ledger is reported, not
  used for decisions. Duty cycling is an analytic schedule (receivers on only in the measured active windows) without
  wake-up synchronisation cost. Many sensor currents and the MCU figures are labelled ASSUMPTION in
  `sensor_profiles.json`. No battery chemistry or capacity is modelled: lifetimes are given per joule of capacity.
* Event classes, the 3-sample persistence rule and the deadlines are simulation rules; soil thresholds are assumptions.
* The round structure (2 s decision windows, cluster phase before route phase) sets the end-to-end delay and the load
  per second; it was not tuned. TTL 15 limits the deployment length to about 1.4 km at 0 dBm.
* The MATLAB V2 10-node layout is partitioned at 0 dBm (nodes 1-5 cannot reach the BS).

## 17. Recommended final research configuration

* Reference (unchanged, validated): `V2_200Node_Environmental` (abstract channel, variant C).
* Realistic main configuration: `W_Environmental` (IEEE 802.15.4, CC2420 values, link-budget prior, variant C, common
  topology), 200 nodes, 600 x 50 m, five scenarios x seeds 42-46, 500 rounds; `W_EventAware` for event-driven delivery
  (critical deadlines); physical energy from `tools/research_upgrade.py` (duty-cycled CC2420 + sensing ledger).
* 500 nodes: scale the decision windows with the node count before drawing conclusions (contention), and keep the BS
  within 15 radio hops.
* Run on mains power with at most 4 runs in parallel (OMNeT++ shell; `opp_runall` needs `bash` before the script on
  Windows; checked with its `-e` export: 25 runs enumerated; about 8-10 h for the 200-node batch):

Remaining runs only (completed runs are reused; filters checked with `-q runnumbers`: 20 and 24 runs):

```
opp_runall -j4 -b1 bash ./run_wireless.sh -c W_EventAware -r '$N==200 && ("$scenario"!="mixed" || $seed!=42)'
opp_runall -j4 -b1 bash ./run_wireless.sh -c W_Environmental -r '$N==200 && "$scenario"!="mixed"'
./run_wireless.sh -c W_FeedbackAck -r '"$scenario"=="mixed" && $N==200 && $seed==42' --result-dir=results_research_upgrade/feedback_ack_N200_100rounds --**.controller.numRounds=100 --sim-time-limit=10000s
./run_wireless.sh -c W_Environmental -r '$N==500 && "$scenario"=="mixed" && $seed==42'
./run_wireless.sh -c W_FixedDensity -r '$N==500 && "$scenario"=="mixed" && $seed==42'
python -P tools/research_upgrade.py
```

## Exact commands

Windows (set `OMNETPP_ROOT` once, e.g. `setx OMNETPP_ROOT "<path to omnetpp-6.4.0>"`), or the OMNeT++ 6.4.0 shell:

| step | command |
|---|---|
| build the simulator (INET-free) | `build.cmd` (= `./build.sh`) |
| build INET 4.7.0 (once, official procedure) | OMNeT++ shell: `cd "$OMNETPP_ROOT/samples/inet-4.7.0" && source setenv && make MODE=release -j8` |
| build the 802.15.4 plugin | `build_wireless.cmd` (= `./build_wireless.sh`) |
| pilot tests + checker | `for c in P1_TwoNodeAck P2_OutOfRange P3_Csma P4_HiddenNode P5_Lengths P5b_Oversize P6_Queue; do ./run_wireless.sh -f wireless/pilot.ini -c $c; done` then `python -P tools/check_wireless_pilot.py` |
| event annotations | `python -P tools/build_event_annotations.py` |
| 802.15.4 runs | `./run_wireless.sh -c W_Environmental -r '"$scenario"=="mixed" && $N==200 && $seed==42'` (same pattern for `W_EventAware`, `W_ScenarioPlacement`, `W_FixedDensity`, `W10_Smoke`); rounds 1-100: add `--**.controller.numRounds=100 --sim-time-limit=10000s` |
| abstract runs (unchanged) | `run.cmd V2_200Node_Environmental all 200` |
| analysis and figures | `python -P tools/research_upgrade.py` -> `results_research_upgrade/analysis/` |
| MATLAB 50-node validation | copy `tools/`, `matlab_reference/`, `data/*.csv`, `data/kspcb_converted/` into a new `validation_vN/`, then `VALDIR=validation_vN ./validate_v2.sh` |
| MATLAB V2 10-node validation | `./RLHybrid_Scalability_Experiment -u Cmdenv -c V2_10Node --result-dir=validation_vN/v2_10node` then `V2_RES=validation_vN/v2_10node python -P tools/compare_v2.py V2_10Node 42 43 44 45 46` |

## Final classification

| item | classification |
|---|---|
| INET 4.7.0 build and compatibility with OMNeT++ 6.4.0 | Fully implemented and validated |
| IEEE 802.15.4 wireless model (real next hop, CSMA/CA, ACK, retries, queue, collisions, PSDU limit) | Fully implemented and validated (pilot 58/58; 200-node runs with all per-round invariants) |
| Preservation of the abstract model and the MATLAB references | Fully implemented and validated (50-node, 10-node V2, environmental 200/500 byte-identical) |
| Radio energy from measured radio states (CC2420), duty-cycled estimate, no double counting | Fully implemented and validated (state integration = INET meter; ledger charges = MAC transmissions) |
| 2 J reference ledger with per-transmission charging | Fully implemented and validated |
| Environmental event detection (classes, triggers, deadlines) | Fully implemented and validated (row-by-row check against the dataset alarm flags) |
| 200-node 802.15.4, mixed scenario, seeds 42-46 (variant C) | Fully implemented and validated (5 seeds, 500 rounds) |
| Event-aware RL-Hybrid option | Implemented but partially validated (mixed seed 42, 500 rounds; one paired seed) |
| 200-node 802.15.4, the other four scenarios | Not run (configured; commands in section 17) |
| 500-node 802.15.4, fixed area vs fixed density | Implemented but partially validated (fixed area, mixed: seed 42 complete over 500 rounds, seeds 43-46 stopped at round 96; fixed density: 5-round smoke runs only) |
| Time mapping (100 s simulated round = 1 h) | Fully implemented and validated (identical behaviour with 3,600 s rounds) |
| Routing-feedback airtime (`W_FeedbackAck`) | Implemented, not run |
| Scenario-specific placement | Implemented but partially validated (20-round run) |
| Link information: history and RSSI/SNIR recorded, link-budget prior | Implemented but partially validated (RSSI/SNIR only in rebuilt-binary runs) |
| 802.15.4 LQI | Not implemented (not provided by INET's scalar radio) |
| Enhanced-ACK airtime for routing feedback, shadowing/fading, battery chemistry | Not implemented |
| Blocked by missing dependencies | none
