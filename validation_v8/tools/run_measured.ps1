# Runs one configuration in Cmdenv and records wall-clock time and peak memory (working set).
# Usage (PowerShell, from anywhere):  tools\run_measured.ps1 -Config Periyar250_Smoke
param([Parameter(Mandatory = $true)][string]$Config,
      [string]$OmnetRoot = "<USER_HOME>\Downloads\omnetpp-6.4.0-windows-x86_64\omnetpp-6.4.0")
$proj = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $proj "RLHybrid_Scalability_Experiment.exe"
$env:PATH = "$OmnetRoot\bin;$OmnetRoot\tools\win32.x86_64\clang64\bin;" + $env:PATH
$log = Join-Path $proj "logs\run_$Config.log"
New-Item -ItemType Directory -Force (Join-Path $proj "logs") | Out-Null
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath $exe -ArgumentList "-u", "Cmdenv", "-c", $Config -WorkingDirectory $proj `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err" -PassThru -WindowStyle Hidden
$null = $p.Handle     # keep the process handle so ExitCode is available after exit
$peak = 0
while (-not $p.HasExited) {
    try { $p.Refresh(); if ($p.PeakWorkingSet64 -gt $peak) { $peak = $p.PeakWorkingSet64 } } catch {}
    Start-Sleep -Milliseconds 100
}
$p.WaitForExit()
$sw.Stop()
$events = (Select-String -Path $log -Pattern '\*\* Event #(\d+)' -AllMatches | ForEach-Object { $_.Matches } | ForEach-Object { [long]$_.Groups[1].Value } | Measure-Object -Maximum).Maximum
$line = "{0}: exit {1}, wall {2:N1} s, peak working set {3:N1} MiB, last reported event #{4}" -f $Config, $p.ExitCode, $sw.Elapsed.TotalSeconds, ($peak / 1MB), $events
Add-Content -Path (Join-Path $proj "logs\performance.txt") -Value $line
$line
