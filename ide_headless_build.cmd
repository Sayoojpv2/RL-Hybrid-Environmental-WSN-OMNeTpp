@echo off
rem Imports the project into a fresh temporary IDE workspace and builds it with the
rem OMNeT++ IDE's own builders (see ide_headless_build.sh). Argument: debug (default) or release.
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
"%OMNETPP_ROOT%\tools\win32.x86_64\usr\bin\bash.exe" -l -c "set -o pipefail; ./ide_headless_build.sh %~1 2>&1 | tee logs/ide_headless_build_%~1_$(date +%%Y%%m%%d-%%H%%M%%S).log"
exit /b %ERRORLEVEL%
