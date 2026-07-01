@echo off
REM ===========================================================================
REM  RUN_TEST.bat  --  runs the AT&T map HEALTH CHECK (us vs them).
REM  Pulls the latest tester + hunter code from GitHub, then runs att_test.py.
REM  Use this when the hunter "stops / won't pan" to see if AT&T changed their
REM  site or if it's our code. Close the hunter first (they share the login).
REM ===========================================================================
title Optimus - AT&T Map Health Check
setlocal
set "APP=%USERPROFILE%\optimus_hunter"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "RAW=https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/%BRANCH%/optimus"

REM --- bootstrap: install the whole toolkit if it's not here yet ---
if not exist "%APP%\precise_fiber_hunter.py" (
  echo First-time setup -- installing Optimus ^(Python + tools^), one time...
  curl -L -o "%TEMP%\IO.bat" "%RAW%/install/INSTALL_OPTIMUS.bat"
  call "%TEMP%\IO.bat"
)

cd /d "%APP%"
echo Checking for updates...
curl -L -s -o "att_test.py"             "%RAW%/att_test.py"
curl -L -s -o "precise_fiber_hunter.py" "%RAW%/precise_fiber_hunter.py"
curl -L -s -o "optimus_dot_detect.py"   "%RAW%/optimus_dot_detect.py"
curl -L -s -o "optimus_api_capture.py"  "%RAW%/optimus_api_capture.py"

echo.
echo Running the AT&T map health check. Position the map over some dots,
echo press Enter, and it will test each step (load / login / map / dots /
echo pan / search / data feed) and print PASS/FAIL so we know what broke.
echo.
py att_test.py 2>nul || python att_test.py
echo.
echo Test done. A copy of the report is in:  %APP%\att_test_report.txt
pause
