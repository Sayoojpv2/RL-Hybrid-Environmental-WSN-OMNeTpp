//
// Periyar RL-Hybrid validation model (OMNeT++ 6.4, native modules, no INET).
//
// Faithful port of the frozen MATLAB experiment RL_WSN_Periyar:
//   50 battery nodes placed by generate_scenario.m (seed-dependent, 600 x 50 m river),
//   base station at (600, 25) m, 10 sensing stations (nodes 4 8 12 18 22 28 32 38 42 48),
//   Periyar workload (10,000 slots), RL_Hybrid.m routing and learning.
//
// Radio links: the MATLAB channel has NO hard radio range; every node can try to reach
// every other node and the BS. Frames are therefore sent with sendDirect() to the chosen
// receiver; whether a frame is decoded is decided by success_history(i,j,round) of
// generate_scenario.m, evaluated when the frame arrives. Node icons are drawn at a scaled
// graphical position (x*1.6+40, y*6+90 px); physical positions are in metres.
//

simple SensorNode
{
    parameters:
        @class(SensorNode);
        @display("i=misc/node;is=vs");
        int nodeId;                                         // MATLAB id 1..50
        double ackTimeout @unit(s) = default(20ms);         // > frame duration + 2 x propagation
        double processingDelay @unit(s) = default(5ms);     // Tproc in RL_Hybrid.m
        double bitRate @unit(bps) = default(250kbps);       // Rbit in RL_Hybrid.m
    gates:
        input radioIn @directIn;
}

simple BaseStation
{
    parameters:
        @class(BaseStation);
        @display("i=device/antennatower;is=s");
        double processingDelay @unit(s) = default(5ms);
        @signal[pathDelay](type=double);
        @statistic[pathDelay](title="path delay per delivered report (MATLAB definition)"; unit=s; record=mean,count);
        @signal[latency](type=simtime_t);
        @statistic[latency](title="OMNeT++ latency from round start to BS"; unit=s; record=mean);
        @signal[hops](type=long);
        @statistic[hops](title="hops per delivered report"; record=mean,histogram);
    gates:
        input radioIn @directIn;
}

simple Controller
{
    parameters:
        @class(Controller);
        @display("i=block/cogwheel;is=s");
        int scenarioSeed;                                   // 42..46 (topology, channel and agent streams)
        string datasetPath;                                 // copy of RL_WSN_Periyar/data/Periyar_WaterQuality_Project.csv
        // ---- SCENARIO / WORKLOAD CONFIGURATION (defaults = the validated Periyar experiment).
        // The routing algorithm never reads any of the workload/payload settings below.
        string workloadMode = default("dataset");          // "dataset" | "synthetic" | "mixed" (dataset stations + synthetic sources)
        string datasetTimeColumn = default("Date");        // ISO timestamps (lexical order = chronological)
        string datasetStationColumn = default("Location");
        // payload fields read from the CSV: "column|name|unit|lo|hi; ..." (valid range; '>'/'<' = exclusive; inf allowed)
        string datasetFields = default("Temperature|temperature|degC|15|50; pH|pH|pH|0|14; Conductivity|conductivity|unspecified|>0|inf; TDS|TDS|unspecified|>0|inf");
        // station label -> source node id; order = source order (create_periyar_workload_continuous.m mapping)
        string stationMap = default("ALUVA - MANAPPURAM=4; PURAPILLIKADAVU US=8; PURAPILLIKADAVU BUND NAVIGATION=12; PURAPILLIKADAVU BUND DS=18; PATHALAM BUND U/S=22; PATHALAM BUND D/S=28; PATHALAM BRIDGE=32; PUTHALAM KADAVU=38; MANJUMMAL BUND=42; VETTUKADAVU=48");
        string invalidRowPolicy = default("drop");         // "drop": row unusable unless all fields valid (MATLAB) | "keepNaN"
        string holdPolicy = default("sampleAndHold");      // "sampleAndHold": causal LOCF (MATLAB) | "freshOnly": only rounds with a new sample
        int expectedRawRows = default(1273);               // regression guards for the Periyar file; -1 disables
        int expectedValidRows = default(1251);
        int expectedUniqueTimes = default(212);
        string syntheticSources = default("");             // node ids, e.g. "5, 9, 20-24" (labelled SYNTHETIC-n<id>)
        string syntheticFields = default("");              // "name|unit|mean|amplitude|noise; ..." (generated values, not measurements)
        int syntheticSeed = default(1);
        int syntheticPeriodRounds = default(100);
        int reportInterval = default(1);                   // every source has a slot in rounds 1, 1+k, 1+2k, ...
        int workloadRounds = default(1000);                // rounds the workload spans (MATLAB numRounds)
        int scheduleRounds = default(-1);                  // timestamp->round schedule length (V2: 1000 with 500 simulated rounds); -1 = workloadRounds
        string placement = default("common");              // "common": one topology for every scenario (paired comparisons) |
                                                           // "scenario": SYNTHETIC profile-specific layout (Scenario::placeByProfile)
        string topologyMode = default("referenceLayout");  // "referenceLayout" (50-node layout + extra nodes) | "stationPositions" (V2)
        string stationNodeIds = default("");               // stationPositions: reference-layout ids that become nodes 1..N (V2: "4,8,12,18,22,28,32,38,42,48")
        bool reportPreservingEnergy = default(false);      // V2: a route frame with m reports costs m packets (TX and RX); false = frozen 50-node rule
        double areaLength = default(600);                  // m (generate_scenario.m)
        double areaWidth = default(50);                    // m
        double bsX = default(600);                         // m
        double bsY = default(25);                          // m
        int packetSize = default(4000);                    // bits per frame
        double initialEnergy = default(2.0);               // J per node
        int numRounds = default(1000);
        double roundPeriod @unit(s) = default(10s);         // simulated time reserved for one MATLAB round
        double stepGuard @unit(s) = default(1ms);           // gap between sequential decision steps
        string outputPrefix;
        bool exportReference = default(false);              // write workload / topology files (Stage B)
        bool exportChannel = default(false);                // also write all success_history bits
        double epsilonInitial = default(0.25);              // RL_Hybrid.m lines 37-39
        double epsilonMinimum = default(0.05);
        double epsilonDecayPerRound = default(0.9985);
        int extraTopologySeed = default(-1);                // added relays (N > 50): MatlabTwister seed; -1 = 900000 + scenarioSeed
        int topologySeed = default(-1);                     // nodes 1..50 layout: -1 = scenarioSeed (MATLAB); >= 0 fixes the layout
        string channelStream = default("matlab");           // "matlab": rng(seed + r); "independent": rng(1000000*seed + r)
        bool exportDeliveredPayload = default(false);       // write <prefix>-delivered_payload.csv (payload as received by the BS)
        bool enableRetransmission = default(false);         // EXPERIMENTAL (not MATLAB): resend a frame that was not decoded
        int maxRetransmissions = default(1);                // retries per frame when enabled
        double retryEnergyReserve = default(0);             // EXPERIMENTAL A: retry only if sender and receiver keep this fraction of E0
        bool qPriorInit = default(false);                   // EXPERIMENTAL B: untried actions start at the prior expected reward
        double energyGuard = default(0);                    // EXPERIMENTAL C: skip candidates below this fraction of their mean energy
        string replaySources = default("");                 // "others": nodes not in stationMap replay station ((k-1) mod S)+1 (virtual)
        bool exportDecisionLog = default(true);            // <prefix>-decisions.csv (one line per routing decision)
        bool exportDiagnostics = default(false);            // write <prefix>-hops.csv (true link quality per transmission)
        // ENVIRONMENTAL WSN (off by default; primary workflow = [Config V2_200Node_Environmental]): read the workload from
        // data/scenarios/<name>/observations.csv or the mixed node_map.csv instead of the loader settings above.
        // scenarioMode "m2" = each sensor profile's own reporting schedule (m2_report); "m1" = the retired fixed
        // V2_200Node slots (m1_report). The m2_sensing_mJ column feeds a separate sensing ledger, never charged to initialEnergy.
        string scenario = default("");                      // label: water | effluent | air | soil | mixed (summary, results)
        string scenarioDataset = default("");
        string scenarioMode = default("m2");
        // per-report radio-frame bits: "dataset" = each report's own m2_frame_bits column (primary workflow: 17 B 802.15.4
        // MAC/PHY + 10 B header + 2 B per present field), or a map by sensor_type, e.g. "water_quality=280; soil_monitoring=264;
        // soil_monitoring+chem=328" (retired M2F), or "" = every report has packetSize bits. With frame bits, every energy charge, energy-feasibility check and frame
        // airtime uses the actual frame; packetSize stays only the node-death threshold E < E_elec x packetSize.
        string scenarioFrameBits = default("");
        // COMMUNICATION MODEL. "abstract" (default) = the validated MATLAB-equivalent model. "ieee802154" needs the network
        // PeriyarWirelessNetwork (PeriyarWireless.ned) and the plugin wireless/RLHybridWireless (INET 4.7.0): data frames then
        // go through INET's IEEE 802.15.4 narrowband MAC (CSMA/CA, ACKs, retries) and radio medium; decisions of a phase run
        // concurrently; routing feedback (receiver energy and load, next-hop value) stays out of band.
        string communicationModel = default("abstract");
        double wirelessAckTimeout @unit(s) = default(1s);    // > longest MAC service (~0.44 s); no outcome by then = frame lost in a MAC
        string wirelessLinkPrior = default("linkBudget");    // ieee802154: agent link prior p0 = expected PRR of the 802.15.4
                                                             // channel ("linkBudget") | MATLAB abstract-channel law ("matlabDistance")
        double clusterJitter @unit(s) = default(2s);         // ieee802154: decisions of a phase start uniformly in [0, jitter)
        double routeJitter @unit(s) = default(2s);
        int routingHeaderBytes = default(6);                 // RL-Hybrid header per frame: type, hops, cluster head, sequence
        int macPayloadLimitBytes = default(118);             // INET Ieee802154NarrowbandMac mtu = 127 B PSDU - 9 B MAC overhead
        int macOverheadBytes = default(9);                   // INET Ieee802154NarrowbandMac headerLength (72 b, incl. FCS)
        int phyOverheadBytes = default(6);                   // INET narrowband radio: preamble 4 B + SFD 1 B + PHR 1 B
        int defaultPayloadBits = default(144);               // reports without a dataset payload size (V2 loader workload)
        bool eventAware = default(false);                    // ieee802154: critical reports skip aggregation; priority queues
        string eventAnnotations = default("");               // data/events/<dataset>.csv (tools/build_event_annotations.py)
        double ageingInterval @unit(s) = default(1s);        // eventAware: +1 priority level per interval of waiting
}

network PeriyarRiverNetwork
{
    parameters:
        int numNodes = default(50);   // battery nodes N (any N >= 1 the topology mode allows); module node[k] = node id k+1
        // ---- DISPLAY ONLY. Nothing below affects routing, energy or channel calculations.
        // Map area: node (x, y) in metres is drawn at (60 + 1.6*x, 140 + 6.8*y) px, i.e. the 50 m
        // river width is exaggerated 4.25x relative to the 600 m length (see Controller.cc).
        @display("bgb=1180,705;bgg=,0");
        @figure[panel](type=rectangle; pos=10,8; size=1160,96; fillColor=#f3f6fa; lineColor=#b8c4d4; cornerRadius=6; zIndex=-3);
        @figure[status](type=text; pos=150,14; text="status"; font=,9; color=#1b2a3a);
        @figure[ctrlNote](type=text; pos=14,72; text="simulation\ncontroller\n(not a radio node)"; font=,7; color=#666666);
        @figure[mapCaption](type=text; pos=60,114; text="Map of the river section (display-scaled: 1.6 px/m along the river, 6.8 px/m across = 4.25x vertical exaggeration). Routing and energy use the real coordinates in metres."; font=,8; color=#555555);
        @figure[river](type=rectangle; pos=60,140; size=960,340; fillColor=#dcecf8; lineColor=#9cc3e0; zIndex=-2);
        @figure[downstream](type=text; pos=1024,140; text="downstream\nend (BS)"; font=,7; color=#4a7fa8);
        @figure[hops](type=group; zIndex=-1);
        // legend: roles
        @figure[lgTitle](type=text; pos=20,498; text="Legend"; font=,9,bold);
        @figure[lgSrc](type=oval; pos=22,522; size=14,14; fillColor=#1f6fd1; lineColor=#0b3d80);
        @figure[lgSrcT](type=text; pos=42,522; text="sensing/source node (10): label  nK \"station\""; font=,8);
        @figure[lgRel](type=oval; pos=25,545; size=9,9; fillColor=#a8a8a8; lineColor=#6e6e6e);
        @figure[lgRelT](type=text; pos=42,543; text="node without its own reports (none in the 10-node V2 setup): label  nK"; font=,8);
        @figure[lgDead](type=oval; pos=23,564; size=12,12; fillColor=#d62728; lineColor=#7a0000);
        @figure[lgDeadT](type=text; pos=42,563; text="unavailable node (energy rules)"; font=,8);
        @figure[lgIds](type=text; pos=20,584; text="nK = node K;  BS = base station"; font=,8);
        // legend: packets and link outcomes
        @figure[lgOk](type=line; points=330,529, 370,529; lineColor=#2e9e44; lineWidth=3);
        @figure[lgOkT](type=text; pos=378,522; text="frame decoded by the receiver (this round)"; font=,8);
        @figure[lgLost](type=line; points=330,550, 370,550; lineColor=#d62728; lineWidth=2; lineStyle=dashed);
        @figure[lgLostT](type=text; pos=378,543; text="frame lost on the channel (not decoded)"; font=,8);
        @figure[lgPk](type=text; pos=330,563; text="moving dots: cyan = report to cluster head, blue = aggregate frame,\ngreen = ACK, red = NACK, grey = Q-value feedback"; font=,8);
        @figure[lgNoLinks](type=text; pos=330,600; text="No fixed links are drawn: as in MATLAB, any node may try any other node or the BS."; font=,8; color=#555555);
        // station table (filled in at runtime from the workload's station -> node mapping)
        @figure[stations](type=text; pos=760,498; text=""; font=,8; color=#1b2a3a);
    submodules:
        controller: Controller {
            @display("p=40,46;i=block/cogwheel;is=s");
        }
        BS: BaseStation;
        // all battery nodes: node[k] has MATLAB node id k+1; every node can sense (if the workload gives it reports) and forward
        node[numNodes]: SensorNode { nodeId = index + 1; }
}
