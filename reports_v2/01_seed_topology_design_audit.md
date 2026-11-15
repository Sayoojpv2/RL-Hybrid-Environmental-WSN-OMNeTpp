# 1. Seed and topology design audit

## 1.1 Every random process in the model (audited in the source, 25 Oct 2026)

| # | Random process | v1 (and the frozen MATLAB experiment) | Where |
|---|---|---|---|
| R1 | Positions of nodes 1..50 | `rng(seed)`: X = rand(1,50)·600, Y = rand(1,50)·50, sorted by X | `Scenario::generate` (generate_scenario.m) |
| R2 | Positions of added relays 51..N | MT19937 seeded `extraTopologySeed`, default **900000 + seed** | `Scenario::generate` |
| R3 | Channel of round r, links among nodes 1..50 and to the BS | `rng(seed + r)`: link-quality noise, then success draws | `Scenario::channelForRound` (generate_scenario.m) |
| R4 | Channel of a link that involves an added relay | splitmix64 hash of (seed, r, i, j) | `Scenario::extraLinkSuccess` |
| R5 | RL agent: ε-test, random action, tie-break among equal Q | `rng(seed)`, a single stream for all nodes | `Controller::agentRng` (RL_Hybrid.m line 28) |
| – | Workload (Periyar data, schedule, sample-and-hold) | deterministic, no randomness | `Workload::build` |
| – | OMNeT++ RNGs | **not used anywhere** (grep: no `uniform`, `intrand`, `dblrand`, `getRNG`) | – |

**Leakage check (no future outcome reaches a decision).** Channel bits for round r are computed at the start of round r.
They are read in only one place, `Controller::decoded(i, j)`. That function is called when a frame **arrives**:
in `SensorNode::onFrame` and `BaseStation`, after the sender has already chosen the target and spent the energy.
Decisions use only:
- qEst, from the node's own past attempt and success counts plus the distance prior;
- energies, loads and Q-values.

The new diagnostic `trueLQ` is written to `-hops.csv` in `logDecision`, after the outcome is known. No routing code reads it.
Confirmed by code reading. The 50-node decision trace is identical to MATLAB's, which would be impossible if the
port used extra information.

## 1.2 Problems found in the v1 scalability design

1. **Placement and run randomness were mixed (as suspected).** In v1, one `seed` drove R1–R5. Each of the five
   "seeds" at N = 100/250/500 therefore had:
   - a different layout of nodes 1..50 (MATLAB's seed-dependent layout);
   - different added relays (900000 + seed);
   - different channel and agent streams.

   The v1 standard deviations combine placement and stochastic variation. They are not "run-to-run" standard deviations.
2. **The channel streams of consecutive seeds overlap (new finding).** MATLAB's `rng(seed + r)` gives run
   seed s+1 at round r exactly the same generator state as run seed s at round r+1. Measured
   (`logs/audit_channel_stream_overlap.txt`), with the topology held fixed:

   | Mapping | seed 43 round r vs seed 42 round r+1 |
   |---|---|
   | MATLAB `rng(seed + r)` | **999 of 999 rounds bit-identical** (all 2550 link outcomes) |
   | independent `rng(1000000·seed + r)` | 0 of 999 identical; bitwise agreement 0.656 = chance level |

   The v1/MATLAB runs avoided exact identity only because the topology changed with the seed. Even so, in the **frozen
   MATLAB benchmark** consecutive seeds agree on 93.7 % of link outcomes at a one-round shift, against 65.3 % at no
   shift (`logs/audit_matlab_benchmark_channel_coupling.txt`). The frozen benchmark's five seeds therefore share most
   of their channel randomness, and its seed-to-seed standard deviation probably understates channel variability.
   This is reported, not changed: the frozen benchmark is left exactly as it is.
3. **FND censoring.** v1 averaged FND over the runs that had a failure and appended "+1 seed with none". That is a
   conditional mean, and it was not labelled clearly enough. Corrected in `03_first_unavailability.md`.

## 1.3 v2 controlled design

| Stream | v2 controlled design (Ctrl50/100/250/500) | Fixed across run seeds? |
|---|---|---|
| R1 nodes 1..50 | `topologySeed = 42`: the MATLAB layout of seed 42, for every run seed and every N | **fixed** |
| R2 added relays | `extraTopologySeed = 900042`: one stream, drawn in order, so relays 51..100 of N = 100 are the first 50 relays of N = 250 and N = 500, and relays 51..250 of N = 250 are the first 200 of N = 500 (**nested**; check X2) | **fixed** |
| R3 channel, original block | `channelStream = "independent"`: MT19937 seeded 1,000,000·runSeed + r. Distinct for every (run seed, round) with r < 10^6, and disjoint from all other seeds in use (topology 42, agent 42–46, relays 900042 and 910001–910004) | varies with run seed |
| R4 channel, added-relay links | hash of (runSeed, r, i, j). There is no shift-overlap, because each component is hashed separately | varies with run seed |
| R5 agent | `rng(runSeed)`, as in RL_Hybrid.m | varies with run seed |

Run seeds are 42, 43, 44, 45 and 46. Each run seed is shared across N, so per-seed differences between N are paired
(common random numbers for the original-block channel and for the agent stream's starting state).

**Coupling inherited from MATLAB, not removed:** in MATLAB the agent stream `rng(seed)` starts in the same state as the
topology stream. In v2 this coupling remains only for run seed 42, where the agent's uniform draws are the same numbers
that placed the layout-42 nodes. This was left as is, so the plumbing could be checked against MATLAB. The effect is
expected to be negligible, but it was not measured.

**New parameters** (`PeriyarValidation.ned`, Controller):
- `topologySeed` (default −1 = run seed);
- `channelStream` (default `"matlab"`);
- `exportDiagnostics` (default false).

The defaults reproduce the MATLAB experiment exactly, so no existing configuration changed behaviour.

## 1.4 Evidence that the design does what it claims

| Check | Result | Log |
|---|---|---|
| 50-node MATLAB reproduction on the v2 build (`validate_v2.sh`, outputs written to `validation_v2/`, never `results/`) | **112/112**, decision traces identical to MATLAB for seeds 42–46; 51/51 files byte-identical to the unmodified-copy baseline | `logs/validate_v2.log`, `logs/byte_identity_vs_unmodified_copy.txt` |
| New parameters in MATLAB mode (topologySeed 42, relays 900042, `matlab` channel), run seed 42, N = 50/100/250/500 | 9/9 output files byte-identical to the v1 seed-42 runs at **every** N | `logs/check_matlab_mode_reproduces_v1.txt` |
| Topology fixed across run seeds (X1); nesting 50 ⊂ 100 ⊂ 250 ⊂ 500 (X2); five distinct random paths per N (X3) | pass | `logs/verify_controlled.txt` |
| Design file of every run: run seed, topology 42, relays 900042, independent channel, round-1 channel seed 1,000,000·s + 1 (C2) | 20/20 pass | same |
| v1 `results/` untouched (MD5 manifest of 317 files before and after) | unchanged, nothing added | `logs/v1_results_untouched.txt` |

Source changes v1 → v2 (`logs/source_diff_v1_to_v2.diff`) are confined to:
- `PeriyarModel.*`: topology-seed and channel-seed plumbing, plus the link-quality accessor;
- `Controller.*`: parameters and the diagnostics file;
- NED parameters;
- new ini configurations.

`SensorNode.*` (the RL-Hybrid algorithm), `BaseStation.*`, `MatlabRng.h`, the reward, the state features, the energy
model and the workload code are byte-identical to v1.
