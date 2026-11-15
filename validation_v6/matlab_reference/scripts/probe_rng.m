% probe_rng.m - READ-ONLY probe of MATLAB's 'twister' generator so the C++ port can
% reproduce rand()/randi() exactly. Writes only into ../data. Touches no project file.
out = fullfile(fileparts(mfilename('fullpath')), '..', 'data', 'rng_probe.txt');
fid = fopen(out, 'w');
rng(42, 'twister'); x = rand(1, 6);
fprintf(fid, 'rand42 %s\n', sprintf('%.17g ', x));
rng(42, 'twister'); y = zeros(1, 6); for k = 1:6, y(k) = randi(7); end
fprintf(fid, 'randi7_42 %s\n', sprintf('%d ', y));
rng(42, 'twister'); randi(1); a = rand;            % does randi(1) consume a draw?
rng(42, 'twister'); rand; b = rand; rng(42, 'twister'); c = rand;
fprintf(fid, 'after_randi1 %.17g  second_rand %.17g  first_rand %.17g\n', a, b, c);
rng(42, 'twister'); m = rand(3, 2);                 % fill order of a matrix
fprintf(fid, 'mat3x2 %s\n', sprintf('%.17g ', m(:)));
rng(43, 'twister'); fprintf(fid, 'rand43 %.17g\n', rand);
fprintf(fid, 'hypot %.17g sqrt %.17g\n', hypot(123.456, 7.891), sqrt(123.456^2 + 7.891^2));
fprintf(fid, 'release %s\n', version('-release'));
fclose(fid);
