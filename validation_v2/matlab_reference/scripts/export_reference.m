% export_reference.m - READ-ONLY export of the frozen MATLAB Periyar experiment for the
% OMNeT++ validation. It calls the frozen loader/workload/scenario functions and reads the
% authoritative result MAT. It writes ONLY into ../data of the OMNeT++ validation project.
% Nothing in the MATLAB workspace is created, modified or deleted.
here = fileparts(mfilename('fullpath'));
outDir = fullfile(here, '..', 'data');
ws = '<USER_HOME>\Documents\MATLAB\RL_WSN_Periyar';
addpath(fullfile(ws, 'simulation'));   % path change is in-memory only (not saved)
seeds = [42 43 44 45 46];

% --- provenance --------------------------------------------------------------
S = load(fullfile(ws, 'results', 'five_seed_rl_hybrid_corrected_authoritative.mat'), 'result');
R = S.result;
fid = fopen(fullfile(outDir, 'provenance.txt'), 'w');
fprintf(fid, 'matlab_release %s\n', version('-release'));
fprintf(fid, 'RL_Hybrid.m md5 (current file)      %s\n', md5Of(fullfile(ws, 'protocols', 'RL_Hybrid.m')));
fprintf(fid, 'RL_Hybrid.m md5 (stored provenance) %s\n', R.provenance.rlHybridSourceMD5);
files = {'generate_scenario.m', 'create_periyar_workload_continuous.m', 'load_water_quality_data.m', 'tx_energy.m', 'rx_energy.m'};
for k = 1:numel(files)
    fprintf(fid, '%s md5 %s\n', files{k}, md5Of(fullfile(ws, 'simulation', files{k})));
end
fprintf(fid, 'Periyar_WaterQuality_Project.csv md5 %s\n', md5Of(fullfile(ws, 'data', 'Periyar_WaterQuality_Project.csv')));
fprintf(fid, 'result MAT created %s, seeds %s\n', R.provenance.createdAt, mat2str(R.seeds));
fclose(fid);

% --- workload (identical for every seed) --------------------------------------
[wq, summ] = load_water_quality_data();
W = create_periyar_workload_continuous(wq, 1000, 'uniform');
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
fprintf(fid, 'raw %d valid %d dates %d scheduled %d available %d unavailable %d\n', summ.totalObservations, ...
    W.metadata.validObservationCount, numel(W.unique_dates), W.totalScheduledReports, ...
    W.totalAvailableDataReports, W.totalUnavailableDataReports);
fprintf(fid, 'r_events %s\n', sprintf('%d ', W.r_events));
fprintf(fid, 'stations %s\n', strjoin(W.station_names, '|'));
fprintf(fid, 'nodes %s\n', sprintf('%d ', W.sensing_nodes));
fclose(fid);
assert(isequal(R.workload_trace.reportSourceNode(:), W.obs_src_nodes(:)) && ...
       isequal(R.workload_trace.reportRound(:), reportRound(:)), 'workload differs from the stored trace');

% --- scenario + frozen results per seed ---------------------------------------
fid = fopen(fullfile(outDir, 'reference_metrics_matlab.csv'), 'w');
fprintf(fid, ['seed,scheduled,workloadAvailable,sourceAvailable,attempts,unattempted,delivered,stageLoss,' ...
    'lossNoCandidate,lossChannel,lossEnergy,lossTTL,PDR,FND,finalAlive,residualJ,spentJ,energyPerDeliveredJ,' ...
    'meanHops,meanDelayS,qUpdates,explorations,exploitations,physicalFrames\n']);
for si = 1:numel(seeds)
    seed = seeds(si);
    [env, ~, succ] = generate_scenario(seed);
    q = R.raw_results{si};
    assert(isequal(q.wsn_env.X, env.X) && isequal(q.wsn_env.Y, env.Y), 'scenario mismatch');
    f2 = fopen(fullfile(outDir, sprintf('nodes_seed%d.csv', seed)), 'w');
    fprintf(f2, 'node,x,y\n');
    for i = 1:env.numNodes, fprintf(f2, '%d,%.17g,%.17g\n', i, env.X(i), env.Y(i)); end
    fclose(f2);
    % channel outcomes, uint8, MATLAB column-major order (i fastest, then j, then round)
    f2 = fopen(fullfile(outDir, sprintf('success_seed%d.bin', seed)), 'w');
    fwrite(f2, uint8(succ(:)), 'uint8'); fclose(f2);
    L = q.decisionLog;
    f2 = fopen(fullfile(outDir, sprintf('decisions_matlab_seed%d.csv', seed)), 'w');
    fprintf(f2, 'round,hopType,actor,target,reports,qHat,prior,attemptsBefore,successesBefore,actorE,targetE,outcome\n');
    fprintf(f2, '%d,%d,%d,%d,%d,%.17g,%.17g,%d,%d,%.17g,%.17g,%g\n', L');
    fclose(f2);
    f2 = fopen(fullfile(outDir, sprintf('per_round_matlab_seed%d.csv', seed)), 'w');
    fprintf(f2, 'round,delivered,aliveCount,residualJ,qUpdates,explorations,epsilon\n');
    M = [ (1:1000)', q.deliveredPerRound(:), q.aliveCountPerRound(:), q.physicalResidualEnergyPerRound(:), ...
          q.qUpdateCountPerRound(:), q.explorationActionCountPerRound(:), q.epsilonHistory(:) ];
    fprintf(f2, '%d,%d,%d,%.17g,%d,%d,%.17g\n', M');
    fclose(f2);
    f2 = fopen(fullfile(outDir, sprintf('unavailability_matlab_seed%d.csv', seed)), 'w');
    fprintf(f2, 'node,firstUnavailableRound,reason\n');
    for i = 1:env.numNodes, fprintf(f2, '%d,%g,%s\n', i, q.firstUnavailableRound(i), q.unavailabilityReason{i}); end
    fclose(f2);
    spent = sum(q.actualEnergyExpendedPerRound);
    fprintf(fid, '%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%.10g,%g,%d,%.10g,%.10g,%.10g,%.10g,%.10g,%d,%d,%d,%d\n', ...
        seed, q.totalScheduledReports, q.totalWorkloadAvailableReports, q.totalSourceAvailableReports, ...
        q.totalTransmissionAttemptReports, q.totalUnattemptedReports, q.totalDeliveredReports, q.totalStageLossReports, ...
        sum(q.routeFailureNoCandidatePerRound), sum(q.routeFailureChannelPerRound), sum(q.routeFailureEnergyPerRound), ...
        sum(q.routeFailureTTLPerRound), q.applicationPDR, q.FND, q.finalAliveCount, q.finalPhysicalResidualEnergy, ...
        spent, q.energyPerDeliveredReport, R.metrics.meanDeliveredHops(si), R.metrics.meanDelayPerDeliveredReport(si), ...
        sum(q.qUpdateCountPerRound), sum(q.explorationActionCountPerRound), sum(q.exploitationActionCountPerRound), ...
        sum(q.physicalTransmissionFramesPerRound));
end
fclose(fid);
disp('export complete');

function h = md5Of(file)
    fid = fopen(file, 'r'); b = fread(fid, Inf, '*uint8'); fclose(fid);
    md = java.security.MessageDigest.getInstance('MD5'); md.update(b);
    h = lower(reshape(dec2hex(typecast(md.digest(), 'uint8'), 2)', 1, []));
end
