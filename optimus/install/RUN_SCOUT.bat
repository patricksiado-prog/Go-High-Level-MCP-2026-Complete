@echo off
REM ===========================================================================
REM  RUN_SCOUT.bat  --  desktop launcher for the Optimus Fiber Scout.
REM  AUTO-UPDATES EVERY RUN: re-downloads the scout + its code from GitHub each
REM  launch, so you always run the newest version with nothing to reinstall.
REM  First run also installs the whole Optimus toolkit if it's not there yet.
REM ===========================================================================
title Optimus Fiber Scout
setlocal
set "APP=%USERPROFILE%\optimus_hunter"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "RAW=https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/%BRANCH%/optimus"

REM --- bootstrap: if the Optimus tools aren't installed yet, install everything first ---
if not exist "%APP%\precise_fiber_hunter.py" (
  echo First-time setup -- installing Optimus ^(Python + tools^), one time...
  curl -L -o "%TEMP%\IO.bat" "%RAW%/install/INSTALL_OPTIMUS.bat"
  call "%TEMP%\IO.bat"
)

cd /d "%APP%"
echo Checking for updates...
curl -L -s -o "fiber_scout.py"          "%RAW%/fiber_scout.py"
curl -L -s -o "optimus_dot_detect.py"   "%RAW%/optimus_dot_detect.py"
curl -L -s -o "precise_fiber_hunter.py" "%RAW%/precise_fiber_hunter.py"
curl -L -s -o "optimus_api_capture.py"  "%RAW%/optimus_api_capture.py"

echo.
echo Starting the Fiber Scout. Pan the map to an area, press Enter, and it
echo surveys for NEW fiber (lots of green + gold, little/no grey).
echo.
py fiber_scout.py 2>nul || python fiber_scout.py
echo.
echo Scout closed. Fresh-area screenshots are in:  %APP%\fresh_zones
pause
