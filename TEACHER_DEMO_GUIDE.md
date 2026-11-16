# Teacher demonstration guide: five environmental scenarios in Qtenv

The menu opens the **same 200-node RL-Hybrid sensor network** with five different environmental workloads. All five are
the existing `[Config V2_200Node_Environmental]` (runs #0-#4: N = 200, seed 42, abstract MATLAB-equivalent channel);
only the scenario changes. Nothing in `omnetpp.ini` is edited.

The demo is a **20-round preview** of each 500-round experiment (the launcher adds `--**.controller.numRounds=20` and
`--sim-time-limit=2000s`; the workload stays the 500-round one). Rounds 1-20 of the preview are identical to rounds
1-20 of the published runs. The preview is for watching the network, **not a benchmark**: its PDR is from the first,
still-learning rounds. The validated numbers are the full results in section 6.

## 1. Prepare once

1. Tell the scripts where OMNeT++ 6.4.0 is (Windows command prompt, once), then open a new window:
   ```bat
   setx OMNETPP_ROOT "C:\path\to\omnetpp-6.4.0"
   ```
2. Build the simulator: double-click `build.cmd`.
3. Try each scenario once before the meeting.

## 2. Start the menu

Double-click **`teacher_demo.cmd`** in the project folder (or run `./teacher_demo.sh` in the OMNeT++ shell).

```
  1. Water quality monitoring
  2. Industrial effluent monitoring
  3. Air quality monitoring
  4. Soil monitoring
  5. Mixed environmental monitoring
  6. Exit
```

Type a number and press Enter. The window prints the selected scenario, its data and its output folder, and Qtenv
opens with that scenario loaded. Then:

* **Maximise** the Qtenv window.
* Press **Run** (F5) to watch the routing animation of the first round. Animation is slow: one round can take minutes.
* Press **Stop** (F8), then **Fast** (F6) to move through rounds with less animation, or **Express** (F7) to finish
  the 20 rounds in seconds.
* At the end Qtenv reports that the time limit was reached; confirm, then **close the window**. The menu comes back
  and prints the run's PDR and energy from its summary.

If the window is closed before the 20 rounds finish, no summary is written (only the files created at the start).

## 3. The five scenarios

Same network for all: 200 nodes in a 600 × 50 m river section, one base station (BS) at (600, 25) m, 2 J radio
energy per node, RL-Hybrid variant C. Every node senses and forwards.

| # | Scenario | Data | Fields each report carries |
|---|---|---|---|
| 1 | Water quality (`water`) | **real**: KSPCB River Periyar analysis reports, 10 station streams; nodes 11-200 replay one of them | temperature, pH, conductivity, TDS (DO is read locally for the DO < 4 mg/L alarm) |
| 2 | Industrial effluent (`effluent`) | **synthetic**: 20 virtual outfalls, generated values, not measurements | temperature, pH, conductivity, TDS, DO, turbidity, COD, BOD, NH3-N |
| 3 | Air quality (`air`) | **real**: UCI Beijing Multi-Site Air Quality (CC BY 4.0), 12 station streams; other nodes replay them | PM2.5, PM10, CO, NO2, SO2, O3, temperature, humidity, wind |
| 4 | Soil (`soil`) | **synthetic**: 10 virtual fields, generated values | soil moisture, soil temperature, EC; pH and N/P/K once per 24 rounds |
| 5 | Mixed (`mixed`) | each node carries one of the four profiles above | depends on the node's profile |

Replayed nodes are virtual sensors repeating a real station's stream; they are not extra real stations. Details:
`scenario_study/SCENARIO_CATALOG.md`, `scenario_study/DATASET_PROVENANCE.md`.

## 4. What to point out on the screen

* **Top panel:** configuration and seed, round number (with "PREVIEW: first rounds only"), scheduled and delivered
  reports, PDR so far, operational nodes, Q-table updates and the exploration rate ε.
* **River map:** the river section, the BS (antenna icon) at the downstream end, and the 200 nodes. Blue = sensing
  node, red = node unavailable under the energy rules. Each label shows the node's profile and station. With 200 nodes
  the labels overlap: zoom in on one part of the river (zoom buttons of the network view) or follow one node.
* **Moving dots:** cyan = report to a cluster head, blue = aggregate frame, green = ACK, red = NACK, grey = Q-value
  feedback.
* **Arrows (this round):** green solid = frame decoded by the receiver; red dashed = frame lost on the channel. No
  fixed links are drawn: any node may try any other node or the BS.
* **Bottom log:** each event (reports, ACKs, cluster steps) as it happens.
* Hover over a node or the BS for a tooltip; the BS tooltip shows how many reports it has received.

**What changes between scenarios:** the number of reports per round (soil about 50, water about 64, mixed about
125, effluent and air about 200 in the first rounds), the frame sizes (more fields = bigger frames) and therefore
traffic and energy. The network and the algorithm stay the same.

## 5. What RL-Hybrid and the base station do

At each routing decision, a node holding a report considers possible next hops (other nodes or the BS). For each
candidate it forms a state from 8 features, each binned low/medium/high (6,561 states): its own energy, the
candidate's energy, the link quality, the distance, the progress towards the BS, the past reliability of that link, the
candidate's load and the hop count so far. From its Q-table it usually picks the best-valued candidate and sometimes a
random one to keep learning (ε-greedy). When the outcome comes back (ACK or NACK and the next node's value estimate),
it updates the Q-value of that choice. Cluster heads collect reports and send them on as aggregate frames. The energy
guard (variant C) keeps low-energy nodes from being overused.

**The base station** is the sink at the downstream end: it receives the reports and records delivery, hop count and
delay. It does not route or sense.

## 6. Full research results to show (500 rounds, seeds 42-46, mean ± SD)

From `results_environmental/summary_mean_sd.csv` (figures: `results_environmental/figures/`, for example
`fig1_delivery.png`, `fig3_residual_energy.png`, `fig5_energy_per_delivered.png`). These are the completed,
validated runs; the menu preview does not produce them.

| Scenario | Scheduled reports | Delivered | PDR | Mean hops | Energy per delivered report | Radio energy left | Mean path delay | Nodes alive after 500 rounds |
|---|---|---|---|---|---|---|---|---|
| Water | 68,700 | 31,096 ± 1,925 | **45.26 ± 2.80 %** | 5.16 | 0.736 mJ | 94.3 % | 35.5 ms | 200 / 200 |
| Effluent | 99,306 | 46,416 ± 1,700 | **46.74 ± 1.71 %** | 5.38 | 0.904 mJ | 89.5 % | 41.0 ms | 200 / 200 |
| Air | 100,000 | 46,875 ± 1,646 | **46.88 ± 1.65 %** | 5.30 | 0.896 mJ | 89.5 % | 40.4 ms | 200 / 200 |
| Soil | 25,135 | 10,539 ± 485 | **41.93 ± 1.93 %** | 4.84 | 0.959 mJ | 97.5 % | 33.8 ms | 200 / 200 |
| Mixed | 73,306 | 33,046 ± 1,078 | **45.08 ± 1.47 %** | 5.41 | 0.888 mJ | 92.7 % | 38.7 ms | 200 / 200 |

How to read it:
* PDR is about 42-47 % in every scenario. With the MATLAB channel model (no retransmission, per-hop loss growing with
  distance), multi-hop routes lose part of the reports; the scenario changes the traffic, not the channel.
* No node ran out of energy in 500 one-hour rounds; busier scenarios (effluent, air) use more energy.
* Energy here is the 2 J radio battery only; sensing energy is a separate estimate and is not charged to it.
* On the IEEE 802.15.4 model (INET, mixed scenario, 5 seeds) the same algorithm reaches 89.80 ± 0.34 % PDR at 200
  nodes, because the MAC retransmits lost frames; see `PROJECT_REPORT.md` section 5.

## 7. Suggested order (about 10 minutes)

1. **Water**: introduce the network, the panel, the legend, and one round of routing with Run.
2. **Air**: same network, different real data and more traffic; use Fast.
3. **Effluent**, 4. **Soil**: synthetic workloads; note the different report rates.
5. **Mixed**: all profiles together; finish with Express and show the summary in the menu window.
6. Show the full-results table above and one figure.

## 8. Output of each run

Each launch writes to a new folder `runs\teacher_demo\<scenario>\<date>-<time>\` (never an existing folder, never the
published `results*` folders):

* `V2_200Node_Environmental-<scenario>-seed42-summary.txt`: the run summary (written when the run ends).
* `...-per_round.csv` (one row per round), `...-metrics.csv`, `...-reports.csv` (one row per report),
  `...-nodes.csv`, `...-payload_fields.csv`, `...-sensing_ledger.csv`, `...-workload_summary.txt` and the `.sca` file.

## 9. A short introduction for the teacher

"My project is RL-Hybrid, a reinforcement-learning routing method for environmental sensor networks. Each node learns
with Q-learning which neighbour to forward its reports to, balancing delivery and energy. I developed it in MATLAB and
rebuilt it in OMNeT++, where it reproduces the MATLAB results exactly. Here the same 200-node network monitors five
applications: river water quality with real Periyar data, industrial effluent, air quality with real Beijing data,
soil, and a mixed deployment. The demo shows the first 20 rounds; the table shows the completed 500-round results over
five seeds. I also ran it on a simulated IEEE 802.15.4 radio stack, and a small hardware demonstration is planned."
