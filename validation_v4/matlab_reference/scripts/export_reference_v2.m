% export_reference_v2.m - READ-ONLY export of the MATLAB V2 10-node RL-Hybrid experiment
% (<USER_HOME>\Documents\MATLAB\RL_WSN_Periyar_V2_10Nodes, as run by run_experiment.m: 10 nodes,
% rounds 1-500 of the 1000-round schedule, seeds 42-46) for the OMNeT++ validation.
% It calls the V2 functions and reads results/results_500rounds.mat. It writes ONLY into ../data_v2 and
% ../../data of this OMNeT++ project. Nothing in the MATLAB project is created, modified or deleted.
here = fileparts(mfilename('fullpath'));
outDir = fullfile(here, '..', 'data_v2'); if ~isfolder(outDir), mkdir(outDir); end
ws = '<USER_HOME>\Documents\MATLAB\RL_WSN_Periyar_V2_10Nodes';
addpath(fullfile(ws, 'protocols'), fullfile(ws, 'simulation'), ws);   % in-memory path only
assert(startsWith(which('RL_Hybrid'), ws) && startsWith(which('generate_scenario'), ws), 'V2 functions shadowed');
cfg = wsn_config(); cfg.numRounds = 500;                              % exactly as run_experiment.m
seeds = cfg.seeds;

% --- provenance -------------------------------------------------------------------------------
fid = fopen(fullfile(outDir, 'provenance.txt'), 'w');
fprintf(fid, 'matlab_release %s\n', version('-release'));
files = {'protocols/RL_Hybrid.m', 'simulation/generate_scenario.m', 'simulation/create_periyar_workload_continuous.m', ...
         'simulation/load_consdata_xlsx.m', 'simulation/tx_energy.m', 'simulation/rx_energy.m', ...
         'simulation/extract_metrics.m', 'wsn_config.m', 'run_experiment.m', 'data/consdata.xlsx', 'results/results_500rounds.mat'};
for k = 1:numel(files), fprintf(fid, '%s md5 %s\n', files{k}, md5Of(fullfile(ws, files{k}))); end
fprintf(fid, 'numNodes %d numRounds %d scheduleRounds %d seeds %s sensingNodes %s stationNodeIds %s topology %s\n', ...
    cfg.numNodes, cfg.numRounds, cfg.scheduleRounds, mat2str(seeds), mat2str(cfg.sensingNodes), mat2str(cfg.stationNodeIds), cfg.topology);
fclose(fid);

% --- dataset as loaded by V2 (input of the OMNeT++ generic loader) ------------------------------
wq = load_consdata_xlsx(cfg.workbook);
fid = fopen(fullfile(here, '..', '..', 'data', 'v2_consdata_loaded.csv'), 'w');
fprintf(fid, 'Location,Date,Temperature,pH,Conductivity,TDS,DO\n');
for i = 1:height(wq)
    v = [wq.Temperature(i), wq.pH(i), wq.Conductivity(i), wq.TDS(i), wq.DO(i)];
    s = arrayfun(@(x) num2strOrEmpty(x), v, 'UniformOutput', false);
    fprintf(fid, '%s,%s,%s\n', wq.Location{i}, char(wq.Date(i), 'yyyy-MM-dd'), strjoin(s, ','));
end
fclose(fid);

% --- workload (rounds 1-500 of the 1000-round schedule; identical for every seed) ----------------
W = create_periyar_workload_continuous(wq, cfg.numRounds, 'uniform', cfg.sensingNodes, cfg.numNodes, cfg.scheduleRounds);
reportRound = zeros(numel(W.obs_src_nodes), 1);
for r = 1:W.numRounds, reportRound(W.round_obs{r}) = r; end
fid = fopen(fullfile(outDir, 'workload_matlab.csv'), 'w');
fprintf(fid, 'reportIndex,round,sourceNode,station,date,temperature,pH,conductivity,TDS\n');
for k = 1:numel(W.obs_src_nodes)
    fprintf(fid, '%d,%d,%d,%s,%s,%.17g,%.17g,%.17g,%.17g\n', k, reportRound(k), W.obs_src_nodes(k), ...
        W.sourceStations{k}, W.sourceDates{k}, W.temperature(k), W.pH(k), W.conductivity(k), W.TDS(k));
end
fclose(fid);
fid = fopen(fullfile(outDir, 'workload_summary_matlab.txt'), 'w');
fprintf(fid, 'raw %d valid %d dates %d scheduled %d available %d unavailable %d\n', height(wq), ...
    W.metadata.validObservationCount, numel(W.unique_dates), W.totalScheduledReports, ...
    W.totalAvailableDataReports, W.totalUnavailableDataReports);
fprintf(fid, 'r_events %s\n', sprintf('%d ', W.r_events));
fprintf(fid, 'stations %s\n', strjoin(W.station_names, '|'));
fprintf(fid, 'nodes %s\n', sprintf('%d ', W.sensing_nodes));
fclose(fid);

% --- published results (run_experiment.m) ----------------------------------------------------------
P = load(fullfile(ws, 'results', 'results_500rounds.mat'), 'R'); P = P.R;
ph = P.protocols(strcmp({P.protocols.name}, 'RL-Hybrid'));

% --- per seed: scenario, fresh RL_Hybrid run, traces ----------------------------------------------
fid = fopen(fullfile(outDir, 'reference_metrics_matlab.csv'), 'w');
fprintf(fid, ['seed,scheduled,workloadAvailable,sourceAvailable,attempts,unattempted,delivered,stageLoss,' ...
    'lossNoCandidate,lossChannel,lossEnergy,lossTTL,PDR,sourcePDR,validPDR,FND,HND,LND,finalAlive,residualJ,spentJ,' ...
    'energyPerDeliveredJ,meanDelayRoundS,meanDelayPacketS,meanHops,qUpdates,explorations,exploitations,physicalFrames,' ...
    'matchesPublished\n']);
for si = 1:numel(seeds)
    seed = seeds(si);
    [env, ~, succ] = generate_scenario(seed, cfg);
    q = RL_Hybrid(env, [], succ, seed, W);
    m = extract_metrics(q, env);
    pubOK = isequal(m.cumDelivered, ph.cumDelivered(si, :)) && isequal(m.energy, ph.energy(si, :)) && ...
            isequal(m.alive, ph.alive(si, :));
    f2 = fopen(fullfile(outDir, sprintf('nodes_seed%d.csv', seed)), 'w');
    fprintf(f2, 'node,x,y\n');
    for i = 1:env.numNodes, fprintf(f2, '%d,%.17g,%.17g\n', i, env.X(i), env.Y(i)); end
    fclose(f2);
    f2 = fopen(fullfile(outDir, sprintf('success_seed%d.bin', seed)), 'w');   % column-major i, j, round
    fwrite(f2, uint8(succ(:)), 'uint8'); fclose(f2);
    L = q.decisionLog;
    f2 = fopen(fullfile(outDir, sprintf('decisions_matlab_seed%d.csv', seed)), 'w');
    fprintf(f2, 'round,hopType,actor,target,reports,qHat,prior,attemptsBefore,successesBefore,actorE,targetE,outcome\n');
    fprintf(f2, '%d,%d,%d,%d,%d,%.17g,%.17g,%d,%d,%.17g,%.17g,%g\n', L');
    fclose(f2);
    Rn = cfg.numRounds;
    f2 = fopen(fullfile(outDir, sprintf('per_round_matlab_seed%d.csv', seed)), 'w');
    fprintf(f2, 'round,delivered,aliveCount,residualJ,qUpdates,explorations,epsilon,scheduled,sourceAvailable,attempts,stageLoss,unattempted,spentJ,meanDelayS\n');
    M = [ (1:Rn)', q.deliveredPerRound(:), q.aliveCountPerRound(:), q.physicalResidualEnergyPerRound(:), ...
          q.qUpdateCountPerRound(:), q.explorationActionCountPerRound(:), q.epsilonHistory(:), q.scheduledPerRound(:), ...
          q.sourceAvailablePerRound(:), q.actualTxAttemptReportsPerRound(:), q.stageLossPerRound(:), q.unattemptedPerRound(:), ...
          q.actualEnergyExpendedPerRound(:), q.meanEndToEndDelayPerRound(:) ];
    fprintf(f2, '%d,%d,%d,%.17g,%d,%d,%.17g,%d,%d,%d,%d,%d,%.17g,%.17g\n', M');
    fclose(f2);
    f2 = fopen(fullfile(outDir, sprintf('node_energy_matlab_seed%d.csv', seed)), 'w');   % end of round 500
    fprintf(f2, 'node,residualJ,alive,firstUnavailableRound,reason\n');
    for i = 1:env.numNodes
        fprintf(f2, '%d,%.17g,%d,%g,%s\n', i, q.residualEnergyHistory(i, end), q.isAliveHistory(i, end), ...
            q.firstUnavailableRound(i), q.unavailabilityReason{i});
    end
    fclose(f2);
    spent = sum(q.actualEnergyExpendedPerRound);
    hopsMean = mean(q.deliveredReportHopCounts);
    fprintf(fid, ['%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%.10g,%.10g,%.10g,%g,%g,%g,%d,%.10g,%.10g,%.10g,%.10g,%.10g,%.10g,' ...
        '%d,%d,%d,%d,%d\n'], seed, sum(q.scheduledPerRound), W.totalAvailableDataReports, m.generated, m.attempted, ...
        m.unattempted, m.delivered, m.lost, sum(q.routeFailureNoCandidatePerRound), sum(q.routeFailureChannelPerRound), ...
        sum(q.routeFailureEnergyPerRound), sum(q.routeFailureTTLPerRound), m.pdr, 100 * m.delivered / m.generated, ...
        100 * m.delivered / W.totalAvailableDataReports, m.fnd, m.hnd, m.lnd, m.finalAlive, m.residual, spent, m.epr, ...
        m.meanDelay, m.meanDelayPacket, hopsMean, sum(q.qUpdateCountPerRound), sum(q.explorationActionCountPerRound), ...
        sum(q.exploitationActionCountPerRound), sum(q.physicalTransmissionFramesPerRound), pubOK);
    fprintf('seed %d delivered %d PDR %.2f residual %.4f FND %g matchesPublished %d\n', seed, m.delivered, m.pdr, m.residual, m.fnd, pubOK);
end
fclose(fid);
disp('export complete');

function s = num2strOrEmpty(x)
    if isnan(x), s = ''; else, s = sprintf('%.17g', x); end
end

function h = md5Of(file)
    fid = fopen(file, 'r'); b = fread(fid, Inf, '*uint8'); fclose(fid);
    md = java.security.MessageDigest.getInstance('MD5'); md.update(b);
    h = lower(reshape(dec2hex(typecast(md.digest(), 'uint8'), 2)', 1, []));
end
