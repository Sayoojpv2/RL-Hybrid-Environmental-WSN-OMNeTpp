@echo off
rem Builds the INET-dependent plugin wireless\libRLHybridWireless.dll (needs OMNETPP_ROOT and INET 4.7.0 built in release mode).
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
if not exist logs mkdir logs
"%OMNETPP_ROOT%\tools\win32.x86_64\usr\bin\bash.exe" -l -c "set -o pipefail; ./build_wireless.sh 2>&1 | tee logs/build_wireless_$(date +%%Y%%m%%d-%%H%%M%%S).log"
exit /b %ERRORLEVEL%
