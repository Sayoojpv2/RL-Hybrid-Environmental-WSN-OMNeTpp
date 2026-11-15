@echo off
rem Usage: run.cmd <Config> [scenario^|all] [nodes]
rem   run.cmd V2_200Node_Environmental all 200     5 scenarios x seeds 42-46, 200 nodes (25 runs)
rem   run.cmd V2_200Node_Environmental water 500   one scenario, seeds 42-46, 500 nodes (5 runs)
rem   run.cmd V2_200Node_Environmental air         one scenario, 200 nodes (nodes default to 200 when a scenario is given)
rem   run.cmd V2_200Node_Environmental             every run of the config (both node counts, 50 runs)
rem   run.cmd ReferenceCheck ^| SmokeSeed42 ^| FiveSeeds   any other configuration
rem Runs in Cmdenv (no GUI) and saves the console output in logs\run_<Config>[_<scenario>_<nodes>].log
setlocal
rem OMNETPP_ROOT must name the OMNeT++ 6.4.0 installation (the folder that contains tools\win32.x86_64)
if not defined OMNETPP_ROOT echo ERROR: OMNETPP_ROOT is not set. Set it once to your OMNeT++ 6.4.0 folder and open a new prompt, for example:  setx OMNETPP_ROOT "D:\omnetpp-6.4.0"& exit /b 1
if not exist "%OMNETPP_ROOT%\tools\win32.x86_64\usr\bin\bash.exe" echo ERROR: OMNETPP_ROOT="%OMNETPP_ROOT%" is not an OMNeT++ 6.4.0 folder - tools\win32.x86_64\usr\bin\bash.exe is missing.& exit /b 1
set "HOME=%OMNETPP_ROOT%"
set MSYSTEM=CLANG64
set CHERE_INVOKING=1
cd /d "%~dp0"
if not exist logs mkdir logs
set "SCN=%~2"
set "NN=%~3"
if "%NN%"=="" set "NN=200"
set "FILTER="
set "LOG=logs/run_%1.log"
if not "%SCN%"=="" set "FILTER=-r '$N==%NN%'"
if not "%SCN%"=="" set "LOG=logs/run_%1_%SCN%_%NN%.log"
if not "%SCN%"=="" if /i not "%SCN%"=="all" set "FILTER=-r '\"$scenario\"==\"%SCN%\" && $N==%NN%'"
"%OMNETPP_ROOT%\tools\win32.x86_64\usr\bin\bash.exe" -l -c "./RLHybrid_Scalability_Experiment -u Cmdenv -c %1 %FILTER% 2>&1 | tee %LOG%"
