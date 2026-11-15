# Research roadmap

v1.0.0 closes the software simulation study. The items below are open; none of them is claimed as done.

## Remaining simulation gaps (configured, not completed)

1. **500-node IEEE 802.15.4, mixed:** finish seeds 43-46 (about 6-7 h each on the development laptop) to obtain a
   five-seed mean, SD and confidence interval. Only seed 42 is complete.
2. **500-node fixed-density layout** (`W_FixedDensity`, 1,500 × 50 m) and longer decision windows (5 s) at 500 rounds,
   to separate the contention effect from the hop-budget (TTL) effect seen in the 5-round smoke tests.
3. **802.15.4 for the water, effluent, air and soil scenarios** at 200 nodes (20 variant C runs).
4. **Event-aware option, seeds 43-46** and the other four scenarios (24 runs).
5. **Feedback airtime** (`W_FeedbackAck`): send routing answers as real frames instead of out of band.
6. **INET MAC fault:** replace the 1 s timeout workaround with a fix or a documented patch in INET's 802.15.4 MAC.

## Method extensions (ideas, not started)

* A systematic literature review and related-work comparison; it was not completed in this project.
* Scale decision windows and TTL with network size and density.
* Compare RL-Hybrid on 802.15.4 with established WSN routing baselines (for example RPL or a
  minimum-hop/ETX scheme) in the same simulator.
* Calibrate the sensing-energy ledger with measured sensor currents.

## Stage 3: hardware demonstration (proposed)

A small air-quality sensor network to check the simulated behaviour on real radios:

* 5-10 nodes with IEEE 802.15.4 radios (CC2420-class or similar) and low-cost air-quality sensors, one gateway as BS.
* Port the RL-Hybrid decision logic (Q-table, features, sinkward rule) to the node firmware.
* Measure delivery ratio, delay, retransmissions and current draw, and compare them with the simulation of the same
  layout.

No hardware has been built, programmed or measured in this project.
