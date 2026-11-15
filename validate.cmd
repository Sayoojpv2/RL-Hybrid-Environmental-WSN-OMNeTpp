@echo off
rem Runs validate.sh (all validation stages) from a normal Windows command prompt.
rem This is a full experiment (five 1,000-round seeds), not a quick check.
rem Usage: validate.cmd [output dir]   default: validation_runs\<timestamp>\ ; the log is written inside that folder.
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
"%OMNETPP_ROOT%\tools\win32.x86_64\usr\bin\bash.exe" -l -c "./validate.sh %~1"
exit /b %ERRORLEVEL%
