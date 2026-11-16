# Teacher demonstration guide (OMNeT++ Qtenv)

Five existing short simulations, opened one at a time in Qtenv from a menu. Each runs only the first 20 rounds of an
existing configuration. These are **previews for watching the network**, not research results; the validated results
are in `PROJECT_REPORT.md`.

## 1. Prepare once

1. OMNeT++ 6.4.0 is installed. Tell the scripts where it is (Windows command prompt, once), then open a new window:
   ```bat
   setx OMNETPP_ROOT "C:\path\to\omnetpp-6.4.0"
   ```
2. Build the simulator: double-click `build.cmd` (or run it in a prompt).
3. For demo 5 only: INET 4.7.0 must be built (release) in `<OMNETPP_ROOT>\samples\inet-4.7.0`, then run
   `build_wireless.cmd`.
4. Try each demo once before the meeting.

## 2. Start the menu

Double-click **`teacher_demo.cmd`** in the project folder (or, in the OMNeT++ shell, run `./teacher_demo.sh`).

```
  1. 10-node Periyar real-data demo
  2. 50-node MATLAB-equivalent demo   (recommended first)
  3. 250-node network preview
  4. Synthetic environmental monitoring demo
  5. IEEE 802.15.4 wireless demo
  6. Exit
```

Type a number and press Enter. Qtenv opens with that simulation already loaded. Press **Run** (animated), **Step**
(one event), **Fast** or **Express** (fast, little or no animation) and **Stop**. Close the Qtenv window to return to
the menu. If something is missing (no build, no plugin, no INET), the menu prints what to do and waits for a key.

Each launch writes to its own new folder `runs\teacher_demo\<Config>-<date>-<time>\` (summary, per-round CSV,
per-report CSV, `.sca`). Nothing in the published `results*` folders is touched. If you close Qtenv before running,
the empty folder is removed.

## 3. The five demonstrations

| # | Configuration | Network | Data | What to show |
|---|---|---|---|---|
| 1 | `V2_10Node_Smoke` | 10 nodes at the 10 station positions + BS | **real**: KSPCB River Periyar water-quality reports (`data/v2_consdata_loaded.csv`) | every node senses and forwards; first 20 of 500 rounds |
| 2 | `GuiDemo20Rounds` | 50 nodes (10 sources, 40 relays) + BS, seed 42 | **real**: the MATLAB project's Periyar water-quality dataset (`data/Periyar_WaterQuality_Project.csv`, 10 river stations) | the MATLAB-equivalent RL-Hybrid network; best introduction |
| 3 | `Periyar250_GuiPreview` | 250 nodes (the same 10 sources + 240 relays) | same as demo 2 | larger network, longer multi-hop routes |
| 4 | `Synthetic_Smoke` | 50 nodes, 5 sources (nodes 5, 15, 25, 35, 45) | **synthetic**: generated water temperature, turbidity and dissolved oxygen (not measurements) | the workload/loader works with other sensor fields; a report every 2 rounds |
| 5 | `W10_Smoke` | the 10-node layout of demo 1 with INET 802.15.4 radios | **real** (as demo 1) | real MAC behaviour: CSMA/CA, ACKs, retries, collisions |

Node positions in demos 2-4 are simulated positions along the river, not real monitoring stations (except the
station-mapped sources).

## 4. What to point out on the Qtenv screen (demos 1-4)

* **Top panel:** configuration, round number (of 20 in this preview), scheduled and delivered reports, PDR so far,
  operational nodes, Q-table updates and the exploration rate ε. It says "PREVIEW: first rounds only".
* **River map:** the river section, the BS (antenna icon) at the downstream end, and the nodes. Blue = node with its
  own sensor reports (label shows the station), grey = relay without its own reports, red = node unavailable (energy
  rules). Hover over a node or the BS for a tooltip (the BS shows how many reports it has received).
* **Moving dots:** cyan = report to a cluster head, blue = aggregate frame, green = ACK, red = NACK, grey = Q-value
  feedback.
* **Arrows (this round):** green solid = frame decoded by the receiver; red dashed = frame lost on the channel. No
  fixed links are drawn: as in MATLAB, any node may try any other node or the BS.
* Maximise the Qtenv window so the network view is large. In the 250-node preview the node labels overlap at the
  default zoom: zoom in on one part of the river (zoom buttons of the network view), point at the blue source nodes
  and this round's arrows, or use Step to follow one frame.

## 5. What RL-Hybrid does at each routing decision

A node that holds a report considers possible next hops (other nodes or the BS). For each candidate it forms a
state from 8 features, each binned low/medium/high (6,561 states): its own energy, the candidate's energy, the link
quality, the distance, the progress towards the BS, the past reliability of that link, the candidate's load and the hop
count so far. From its Q-table it usually picks the best-valued candidate and sometimes a random one to keep learning
(ε-greedy). When the outcome comes back (ACK or NACK and the next node's value estimate), it updates the Q-value of
that choice. Cluster heads collect reports and send them on as aggregate frames. Over the rounds, nodes learn which
next hops deliver reliably and cheaply.

**The base station** is the sink at the downstream end: it receives the reports and records delivery, hop count and
delay (its tooltip shows the count). It does not route or sense.

## 6. What is different in demo 5 (IEEE 802.15.4)

Demos 1-4 use the abstract (MATLAB-equivalent) channel: each hop succeeds or fails by a probability that depends on
distance. Demo 5 sends the same routing decisions through a simulated radio stack from INET 4.7.0:

* Each node is a compound module: the RL-Hybrid logic (`rl`), an adapter, and an IEEE 802.15.4 interface (`wlan`:
  CSMA/CA MAC with ACKs and up to 3 retries, CC2420 radio values), plus `radioMedium` for propagation and interference.
* The screen has no river drawing: nodes sit at their physical positions (600 × 50 m), so the layout is a thin strip;
  zoom in. Frames appear as radio transmissions through the medium.
* Double-click a node to open it and show the MAC and radio inside.
* It takes a few seconds longer to start because INET is loaded.

## 7. Suggested order (about 10 minutes)

1. **Demo 2**: introduce the network, the panel, the legend and a few rounds of routing.
2. **Demo 1**: the 10 real station streams; every node senses and forwards.
3. **Demo 3**: the same idea at 250 nodes; longer routes.
4. **Demo 4**: other sensor types; stress that the values are generated.
5. **Demo 5**: the same routing over a real MAC protocol.

## 8. A short introduction for the teacher

"My project is RL-Hybrid, a reinforcement-learning routing method for environmental sensor networks. Each sensor node
learns with Q-learning which neighbour to forward its reports to, balancing delivery and energy. I first developed it in
MATLAB, then rebuilt it in OMNeT++, where it exactly reproduces the MATLAB results. I then scaled it to hundreds of
nodes, ran five environmental monitoring scenarios using real Periyar water-quality and air-quality data, and moved it
onto a simulated IEEE 802.15.4 radio stack with INET. These demos show the first 20 rounds of some of those
simulations; the full results are in the project report. A small hardware demonstration is planned but not built."
