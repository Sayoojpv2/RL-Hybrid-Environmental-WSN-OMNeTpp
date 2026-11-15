//
// Messages for the Periyar RL-Hybrid validation model.
//
// DataFrame : one radio frame of 4000 bits (MATLAB packetSize). A member->cluster-head
//             frame carries one report; a routing frame carries the cluster head's
//             aggregate (all reports of the cluster), exactly as RL_Hybrid.m charges
//             one tx_energy(packetSize, d) per aggregate frame.
// LinkAck / ValueFeedback / Command / Done : control messages. They are idealised:
//             error-free and free of energy cost (MATLAB has no control traffic).
//

enum FrameType
{
    FRAME_MEMBER = 1;     // sensing source -> chosen cluster head
    FRAME_ROUTE = 2;      // aggregate frame on a multi-hop route (to a relay or the BS)
}

enum CommandType
{
    CMD_CLUSTER = 1;      // controller -> source: choose a cluster head for this round's report
    CMD_ROUTE = 2;        // controller -> cluster head: aggregate and route the cluster payload
}

struct ReportRecord
{
    int reportIndex;      // MATLAB workload obs index (1..9825)
    int round;            // workload round (1..1000)
    int sourceNode;       // MATLAB node id of the sensing station
    string station;
    string date;          // observation date carried by sample-and-hold
    int numValues;        // payload: application measurements (NOT used for routing); layout = Workload::fields
    double values[16];    // MAX_PAYLOAD_FIELDS; NaN = no value
    bool attempted = false;    // has been on air at least once (MATLAB "attempts")
    bool ingressHop = false;   // reached its cluster head through a member hop
    double pathDelay = 0;      // sum of hop delays (k/Rbit + Tproc + d/c per hop), as MATLAB
    // communicationModel ieee802154 / eventAware only (never read by the validated abstract model)
    double genTime = -1;       // simulation time the report was generated (start of its round)
    double queueDelay = 0;     // time spent waiting for a busy node (relay or cluster-head queue)
    int payloadBits = 0;       // application payload bits (dataset m2_payload_bytes x 8)
    int eventClass = 0;        // 0 routine, 1 warning, 2 critical (data/events annotation)
    int triggerField = -1;     // payload field index of the measurement that raised the event (-1 none)
    double triggerValue = 0;   // that measurement
    double deadline = 0;       // simulation target for the generation-to-delivery delay (s), 0 = none
}

packet DataFrame
{
    int frameType;
    int senderId;          // MATLAB id of the transmitting node
    int clusterHead;       // MATLAB id of the cluster head that owns the aggregate
    int round;
    int hops;              // route hops travelled, including this one (MATLAB `hops`)
    int attempt = 0;       // 0 = first transmission; k = k-th retransmission (experimental option, off by default)
    int txSeq = 0;         // sender's frame counter, only set when retransmission is enabled (independent retry draws)
    int members[];         // cluster members (MATLAB visited(clusterMemberNodes{ch}))
    int visited[];         // nodes already on the route (MATLAB `visited`)
    simtime_t txStart;
    ReportRecord reports[];
}

message LinkAck
{
    int receiverId;
    bool rxOk;             // false: receiver unavailable or could not afford reception
    bool receiverDied;     // reception left the receiver at exactly 0 J
    bool atBS;
    double receiverEnergy; // J after reception (for the relay-energy reward term)
    double receiverLoad;   // nodeLoad after reception (for the load-balance reward term)
    bool hasNextValue = false; // ieee802154: the receiver's max Q at reception (immediate bootstrap, no feedback)
    int txSeq = -1;            // ieee802154: the accepted frame's sequence number (matches the answer to its frame)
    double nextValue = 0;
}

message ValueFeedback
{
    double value;          // max_a' Q(s',a') at the receiver, or -1 for a terminal failure
    bool terminal;
}

message Command
{
    int command;
    int round;
}
