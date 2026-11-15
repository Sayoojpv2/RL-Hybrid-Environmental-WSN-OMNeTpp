# v2: runs ONE run (-Run index) of a configuration in Cmdenv, as its own process, and records wall-clock
# time and peak working set per run into logs_v2/performance_v2.csv. Never writes to results/ (the configs
# used with it set their own result-dir).
# Usage: tools\run_measured_v2.ps1 -Config Ctrl250 -Run 0
param([Parameter(Mandatory = $true)][string]$Config, [Parameter(Mandatory = $true)][int]$Run,
      [string]$OmnetRoot = "<USER_HOME>\Downloads\omnetpp-6.4.0-windows-x86_64\omnetpp-6.4.0")
$proj = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $proj "RLHybrid_Scalability_Experiment.exe"
$env:PATH = "$OmnetRoot\bin;$OmnetRoot\tools\win32.x86_64\clang64\bin;" + $env:PATH
New-Item -ItemType Directory -Force (Join-Path $proj "logs_v2\runs") | Out-Null
$log = Join-Path $proj "logs_v2\runs\run_${Config}_r$Run.log"
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath $exe -ArgumentList "-u", "Cmdenv", "-c", $Config, "-r", "$Run" -WorkingDirectory $proj `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru -WindowStyle Hidden
$null = $p.Handle
$peak = 0
while (-not $p.HasExited) {
    try { $p.Refresh(); if ($p.PeakWorkingSet64 -gt $peak) { $peak = $p.PeakWorkingSet64 } } catch {}
    Start-Sleep -Milliseconds 50
}
$p.WaitForExit()
$sw.Stop()
$events = (Select-String -Path $log -Pattern '\*\* Event #(\d+)' -AllMatches | ForEach-Object { $_.Matches } | ForEach-Object { [long]$_.Groups[1].Value } | Measure-Object -Maximum).Maximum
$perf = Join-Path $proj "logs_v2\performance_v2.csv"
if (-not (Test-Path $perf)) { Add-Content -Path $perf -Value "config,run,exitCode,wallSeconds,peakWorkingSetMiB,lastReportedEvent" }
$line = "{0},{1},{2},{3:F2},{4:F1},{5}" -f $Config, $Run, $p.ExitCode, $sw.Elapsed.TotalSeconds, ($peak / 1MB), $events
Add-Content -Path $perf -Value $line
$line
