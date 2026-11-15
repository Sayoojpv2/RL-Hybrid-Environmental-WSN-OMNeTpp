@echo off
rem Usage: run.cmd <Config> [scenario^|all] [nodes]          (abstract model; runs run.sh in Cmdenv, no GUI)
rem   run.cmd GuiDemo20Rounds                       short demonstration: seed 42, rounds 1-20 only
rem   run.cmd V2_200Node_Environmental all 200      5 scenarios x seeds 42-46, 200 nodes (25 runs)
rem   run.cmd V2_200Node_Environmental water 500    one scenario, seeds 42-46, 500 nodes (5 runs)
rem   run.cmd V2_200Node_Environmental air          one scenario, 200 nodes (nodes default to 200 when a scenario is given)
rem   run.cmd V2_200Node_Environmental              every run of the config (both node counts, 50 runs)
rem Results go to %RESULT_DIR% if set, otherwise to a new runs\<Config>-<timestamp>\ folder; the historical
rem results folders are not written by default. Console log: logs\run_<Config>[_<scenario>_<nodes>]_<timestamp>.log
setlocal
rem OMNETPP_ROOT must name the OMNeT++ 6.4.0 installation (the folder that contains tools\win32.x86_64)
if not defined OMNETPP_ROOT (
  echo ERROR: OMNETPP_ROOT is not set. Set it once to your OMNeT++ 6.4.0 folder and open a new prompt, for example:  setx OMNETPP_ROOT "D:\omnetpp-6.4.0"
  exit /b 1
)
if not exist "%OMNETPP_ROOT%\tools\win32.x86_64\usr\bin\bash.exe" (
  echo ERROR: OMNETPP_ROOT="%OMNETPP_ROOT%" is not an OMNeT++ 6.4.0 folder - tools\win32.x86_64\usr\bin\bash.exe is missing.
  exit /b 1
)
set "HOME=%OMNETPP_ROOT%"
set MSYSTEM=CLANG64
set CHERE_INVOKING=1
cd /d "%~dp0"
rem run.sh builds the run filter itself, so no nested quoting is needed here
"%OMNETPP_ROOT%\tools\win32.x86_64\usr\bin\bash.exe" -l -c "./run.sh %~1 %~2 %~3"
exit /b %ERRORLEVEL%
