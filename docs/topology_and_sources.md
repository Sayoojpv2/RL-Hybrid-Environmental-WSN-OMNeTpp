# Topology, node ids and source mapping

## Area and base station
Fixed for every N: river section 600 m (x) × 50 m (y), BS at (600, 25) m. This is **relay-density
scaling**: the same area holds 50, 100, 250 or 500 battery nodes. The area is not enlarged.

## Nodes 1..50: the MATLAB topology, unchanged
`Scenario::generate(seed, N, extraSeed)` first runs the exact port of `generate_scenario.m`:
`rng(seed,'twister')`, `X = rand(1,50)·600`, `Y = rand(1,50)·50`, then sort by X. Ids 1..50 are therefore
bit-identical to MATLAB `nodes_seed<seed>.csv`. `verify_scaling.py` check S2 confirms this at every N.
The original 50 nodes are never re-sorted or renumbered when relays are added.

## Nodes 51..N: added relay-only nodes
* Stream: a dedicated MT19937 (`MatlabTwister`, the same generator as MATLAB's `twister`) seeded with
  `extraTopologySeed`. The default (`-1`) means `900000 + scenarioSeed`, i.e. seeds 900042..900046.
  This stream is separate from every MATLAB stream, so the original 50-node random path cannot change.
* For k = 51..N, in order: x = rand·600, y = rand·50 (uniform over the area). The relays are appended
  **unsorted**, in draw order. Exact duplicates of an existing node or of the BS are rejected and redrawn
  (none occurred in the tested seeds).
* NED: `n1..n50` are the original modules; `relay[k]` (k = 0..N−51) has `nodeId = 51 + k`.
  In Qtenv an added relay is labelled `relay[k] "n<51+k>"`.
* **These coordinates are simulated positions. They are not, and must not be presented as, real
  Periyar monitoring stations.**

## Sources (identical for every N)
The workload is built from `data/Periyar_WaterQuality_Project.csv` exactly as in MATLAB
(`create_periyar_workload_continuous.m`). The authoritative station → node mapping is:

| Node | Station |
|---|---|
| 4 | ALUVA |
| 8 | PURAPILLIKADAVU US |
| 12 | PURAPILLIKADAVU BUND NAVIGATION |
| 18 | PURAPILLIKADAVU BUND DS |
| 22 | PATHALAM BUND U/S |
| 28 | PATHALAM BUND D/S |
| 32 | PATHALAM BRIDGE |
| 38 | PUTHALAM KADAVU |
| 42 | MANJUMMAL BUND |
| 48 | VETTUKADAVU |

This is 10 sources × 1000 rounds = 10,000 scheduled slots, of which 9,825 hold valid data (175 lie before a
station's first observation). Every other node (40 original + N−50 added) is relay-only. Checks S3/S4
confirm: the workload is identical to MATLAB's, and no node outside the 10 stations ever originates a
report or takes a source (cluster-phase) action.

## Channel
* Links among nodes 1..50 and from nodes 1..50 to the BS: MATLAB's per-round `rng(seed + r)` stream,
  unchanged. It is computed for the 50×51 block only, at every N. Check S7 confirms the block is
  bit-identical to MATLAB's `success_history`. This covers 2,550,000 bits over 1000 rounds at N = 250
  and N = 500 (seed 42), and the first 20 rounds in the smoke tests.
* Any link that involves an added relay (i or j > 50): the **same clipped distance law**,
  lq = clip(base + 0.3(u1 − 0.5), 0.1, 0.95), with base = 1 − d/(600·0.8) to a node or 1 − d/(600·1.2) to the BS,
  and success = u2 < lq. Here u1 and u2 come from a splitmix64 counter hash of (seed, round, i, j).
  It is evaluated only when a frame on that link arrives (O(1), no N×N×rounds table), and it is deterministic.
  It uses no future outcome: the value is drawn from (round, i, j) alone, never from what happens later.
* The routing agent's prior link estimate (`distancePriorLQ`) uses the same closed form for all N×(N+1) pairs.

## Action indexing
Action j = node j (1..N); action N+1 = the BS. The Q key is (state−1)·(N+1) + (action−1). For N = 50 this is
exactly the old key with the constant 51.
