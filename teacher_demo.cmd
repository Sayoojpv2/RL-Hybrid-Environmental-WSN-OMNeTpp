@echo off
rem Teacher demonstration menu: double-click to open one of the five environmental scenarios of the existing
rem V2_200Node_Environmental configuration (200 nodes, seed 42, 20-round preview) in OMNeT++ Qtenv.
rem Needs OMNETPP_ROOT (OMNeT++ 6.4.0 folder) and a built simulator (build.cmd). See TEACHER_DEMO_GUIDE.md.
setlocal
if not defined OMNETPP_ROOT (
  echo ERROR: OMNETPP_ROOT is not set. Set it once to your OMNeT++ 6.4.0 folder, for example:
  echo     setx OMNETPP_ROOT "D:\omnetpp-6.4.0"
  echo then close this window and double-click teacher_demo.cmd again.
  pause
  exit /b 1
)
if not exist "%OMNETPP_ROOT%\tools\win32.x86_64\usr\bin\bash.exe" (
  echo ERROR: OMNETPP_ROOT="%OMNETPP_ROOT%" is not an OMNeT++ 6.4.0 folder - tools\win32.x86_64\usr\bin\bash.exe is missing.
  pause
  exit /b 1
)
set "HOME=%OMNETPP_ROOT%"
set MSYSTEM=CLANG64
set CHERE_INVOKING=1
cd /d "%~dp0"
set BAD=0

:menu
echo.
echo  RL-Hybrid environmental WSN - 200 nodes, Qtenv demonstration
echo.
echo   1. Water quality monitoring
echo   2. Industrial effluent monitoring
echo   3. Air quality monitoring
echo   4. Soil monitoring
echo   5. Mixed environmental monitoring
echo   6. Exit
echo.
set "K="
set /p "K=Select 1-6: "
if "%K%"=="6" exit /b 0
for %%v in (1 2 3 4 5) do if "%K%"=="%%v" goto run
set /a BAD+=1
if %BAD% GEQ 10 exit /b 1
echo Please enter a number from 1 to 6.
goto menu

:run
set BAD=0
"%OMNETPP_ROOT%\tools\win32.x86_64\usr\bin\bash.exe" -l -c "./teacher_demo.sh %K%"
if errorlevel 1 (
  echo The demo did not start or ended with an error - see the message above.
  pause
)
goto menu
