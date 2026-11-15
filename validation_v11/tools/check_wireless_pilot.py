"""Checks the IEEE 802.15.4 pilot (wireless/pilot.ini) against 802.15.4-2006 / INET expectations.
Usage: python -P tools/check_wireless_pilot.py  (after running the seven pilot configs; see the report)
Writes results_research_upgrade/pilot/pilot_checks.csv; exit code 1 if any check fails."""
import csv, math, pathlib, re, sys

D = pathlib.Path(__file__).resolve().parent.parent / "results_research_upgrade" / "pilot"
US = 1e-6
SHR_PHR = 128 * US + 16 * 4 * US      # preamble 4 B + SFD/PHR 2 B: 6 B at 32 us/B (INET: 128 us + 16 bit)
MHR_FCS = 9                           # MAC header + FCS bytes (INET Ieee802154NarrowbandMac headerLength 72 b)
RETRIES = 3                           # macMaxFrameRetries


def sca(name):
    v = {}
    for line in (D / name).read_text().splitlines():
        if line.startswith("scalar "):
            m = re.match(r'scalar (\S+) ("[^"]*"|\S+) (\S+)', line)
            v[(m[1].split(".", 1)[1], m[2].strip('"'))] = float(m[3])
    return v


def events(cfg):
    with open(D / "pilot_events.csv") as f:
        return [r for r in csv.reader(f) if r[0] == cfg]


rows = []


def check(pilot, what, ok, detail):
    rows.append((pilot, what, "PASS" if ok else "FAIL", detail))


def n(v, node, mod, key):
    return v.get((f"node[{node}].{mod}", key), 0.0)


def energy(pilot, v, simtime=30.0):
    nodes = sorted({m.split(".")[0] for m, _ in v if m.startswith("node[")})
    for nd in nodes:
        a = {k: x for (m, k), x in v.items() if m == f"{nd}.adapter"}
        states = [k.split(":")[1] for k in a if k.startswith("power:")]
        t = sum(a["timeActive:" + s] + a["timeGap:" + s] for s in states)
        e = sum((a["timeActive:" + s] + a["timeGap:" + s]) * a["power:" + s] for s in states)
        tot = a["radioEnergyActive"] + a["radioEnergyGap"]
        check(pilot, f"{nd} radio state times cover the run", abs(t - simtime) < 1e-9, f"{t:.9f} s")
        check(pilot, f"{nd} sum(P x t) = adapter energy = INET energy meter",
              abs(e - tot) < 1e-9 and abs(tot - a["radioEnergyInet"]) < 1e-9,
              f"{e:.9f} / {tot:.9f} / {a['radioEnergyInet']:.9f} J")


v = sca("P1_TwoNodeAck.sca")
check("P1", "20/20 frames delivered", n(v, 1, "app", "framesReceived") == 20 and n(v, 0, "app", "framesFailed") == 0,
      f"rx {n(v, 1, 'app', 'framesReceived'):.0f}")
check("P1", "one MAC attempt per frame, one MAC ACK per frame",
      n(v, 0, "wlan.mac", "nbTxFrames") == 20 and n(v, 1, "wlan.mac", "nbTxAcks") == 20 and n(v, 0, "wlan.mac", "nbRecvdAcks") == 20,
      f"tx {n(v, 0, 'wlan.mac', 'nbTxFrames'):.0f}, acks {n(v, 1, 'wlan.mac', 'nbTxAcks'):.0f}")
check("P1", "adapter hands 20 frames down / 20 up", n(v, 0, "adapter", "framesDown") == 20 and n(v, 1, "adapter", "framesUp") == 20, "")
check("P1", "upper layer is told of every MAC transmission", n(v, 0, "app", "macTransmissions") == n(v, 0, "wlan.mac", "nbTxFrames") == 20, "")
energy("P1", v)

v = sca("P2_OutOfRange.sca")
check("P2", "150 m: nothing delivered, every frame fails at the retry limit",
      n(v, 1, "app", "framesReceived") == 0 and n(v, 0, "adapter", "dropRetryLimit") == 20 and n(v, 0, "app", "framesFailed") == 20,
      f"failed {n(v, 0, 'app', 'framesFailed'):.0f}")
check("P2", f"ACK timeout -> {RETRIES} retransmissions per frame",
      n(v, 0, "wlan.mac", "nbTxFrames") == 20 * (1 + RETRIES) and n(v, 0, "wlan.mac", "nbMissedAcks") == 20 * (1 + RETRIES),
      f"attempts {n(v, 0, 'wlan.mac', 'nbTxFrames'):.0f}")
check("P2", "upper layer is told of every retransmission (charged in the 2 J ledger)",
      n(v, 0, "app", "macTransmissions") == 20 * (1 + RETRIES), f"{n(v, 0, 'app', 'macTransmissions'):.0f}")
energy("P2", v)

v3 = sca("P3_Csma.sca")
tx3 = n(v3, 0, "wlan.mac", "nbTxFrames") + n(v3, 2, "wlan.mac", "nbTxFrames")
bo3 = n(v3, 0, "wlan.mac", "nbBackoffs") + n(v3, 2, "wlan.mac", "nbBackoffs")
rx3 = n(v3, 1, "app", "framesReceived")
check("P3", "CSMA/CA defers: more backoffs than transmissions (CCA found the channel busy)", bo3 > tx3,
      f"backoffs {bo3:.0f}, attempts {tx3:.0f}")
check("P3", "simultaneous senders in range: all frames delivered (retries recover collisions)", rx3 == 40,
      f"rx {rx3:.0f}/40, retransmissions {tx3 - 40:.0f}")
energy("P3", v3)

v = sca("P4_HiddenNode.sca")
rx4 = n(v, 1, "app", "framesReceived")
fail4 = n(v, 0, "app", "framesFailed") + n(v, 2, "app", "framesFailed")
check("P4", "hidden nodes collide at the receiver (frames received with errors)", n(v, 1, "adapter", "corruptedReceptions") > 0,
      f"corrupted {n(v, 1, 'adapter', 'corruptedReceptions'):.0f}")
check("P4", "collisions cost retries and losses; every frame accounted for", rx4 + fail4 == 40 and rx4 < rx3,
      f"rx {rx4:.0f}, failed {fail4:.0f}, attempts {n(v, 0, 'wlan.mac', 'nbTxFrames') + n(v, 2, 'wlan.mac', 'nbTxFrames'):.0f}")
energy("P4", v)

for ln in (10, 34, 60, 118):
    v = sca(f"P5_Lengths-len{ln}.sca")
    want = SHR_PHR + (MHR_FCS + ln) * 32 * US
    got = n(v, 0, "adapter", "timeActive:tx")
    check("P5", f"{ln} B payload: airtime = SHR+PHR + (9 + {ln}) B x 32 us",
          abs(got - want) < 1e-12 and n(v, 1, "app", "framesReceived") == 1, f"{got * 1e6:.0f} us (expected {want * 1e6:.0f})")
    energy("P5", v)

v = sca("P5b_Oversize.sca")
check("P5b", "INET does not enforce aMaxPHYPacketSize (a 128 B MPDU is sent) -> the RL layer must cap MAC payload at 118 B",
      n(v, 1, "app", "framesReceived") == 1, f"airtime {n(v, 0, 'adapter', 'timeActive:tx') * 1e6:.0f} us")

v = sca("P6_Queue.sca")
d = [float(r[6]) for r in events("P6_Queue") if r[1] == "rx"]
check("P6", "10 frames queued at once: queue reaches 10, all delivered",
      n(v, 0, "wlan.queue", "queueLength:max") == 10 and len(d) == 10, f"max queue {n(v, 0, 'wlan.queue', 'queueLength:max'):.0f}")
check("P6", "end-to-end delay grows with queue position", all(b > a for a, b in zip(d, d[1:])),
      " ".join(f"{x * 1e3:.1f}" for x in d) + " ms")
energy("P6", v)

with open(D / "pilot_checks.csv", "w", newline="") as f:
    csv.writer(f).writerows([("pilot", "check", "result", "detail")] + rows)
for r in rows:
    print(f"{r[2]}  {r[0]:4s} {r[1]}  [{r[3]}]")
bad = sum(r[2] == "FAIL" for r in rows)
print(f"{len(rows) - bad}/{len(rows)} checks passed")
sys.exit(1 if bad else 0)
