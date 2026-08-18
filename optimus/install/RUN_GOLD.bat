@echo off
REM ===========================================================================
REM  RUN_GOLD.bat -- ONE double-click to get ALL the gold (upgrade) dots.
REM  1) refreshes the code,
REM  2) --backfill-gold: pulls every gold dot already captured into the
REM     "Gold Dots" tab (Patrick's residential-upgrade call list), then
REM  3) writes the small "OPTIMUS DATA SUMMARY" sheet (Gold Dot Addresses +
REM     Gold Hotspots) so Claude can read WHERE the new fiber is.
REM  Runs in the hunter's folder (has the modules + google_creds.json).
REM  Run it once; the hunter keeps the Gold Dots tab current on its own after.
REM ===========================================================================
title Optimus GOLD DOTS
setlocal EnableDelayedExpansion
set "RAW=https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/claude/optimus-map-tools-setup-6dcl6o/optimus"

REM use the hunter's install (has the modules + google_creds.json already)
set "APP=%USERPROFILE%\optimus_hunter"
if not exist "%APP%\precise_fiber_hunter.py" if exist "%USERPROFILE%\optimus\repo\optimus\precise_fiber_hunter.py" set "APP=%USERPROFILE%\optimus\repo\optimus"
if not exist "%APP%\precise_fiber_hunter.py" (
  echo Could not find the hunter install. Run INSTALL_OPTIMUS.bat first.
  pause
  exit /b 1
)
cd /d "%APP%"

echo Getting the latest code...
set "CB=%RANDOM%%RANDOM%"
curl -L -sf -o precise_fiber_hunter.py.new "%RAW%/precise_fiber_hunter.py?cb=!CB!" && move /y precise_fiber_hunter.py.new precise_fiber_hunter.py >nul || echo   (could not refresh hunter -- using the copy you have)
curl -L -sf -o optimus_summary.py.new "%RAW%/optimus_summary.py?cb=!CB!" && move /y optimus_summary.py.new optimus_summary.py >nul || echo   (could not refresh summary -- using the copy you have)
curl -L -sf -o build_codes.json.new "%RAW%/build_codes.json?cb=!CB!" && move /y build_codes.json.new build_codes.json >nul
del /q *.new 2>nul

set "PYCMD=python"
where py >nul 2>&1 && set "PYCMD=py"

echo.
echo === Step 1/2: filling the "Gold Dots" tab with every gold dot so far ===
%PYCMD% precise_fiber_hunter.py --backfill-gold --no-update

echo.
echo === Step 2/2: writing the small "OPTIMUS DATA SUMMARY" sheet (gold hotspots) ===
%PYCMD% optimus_summary.py --no-update

echo.
echo Done. The "Gold Dots" tab has your upgrade call list, and the
echo "OPTIMUS DATA SUMMARY" sheet has the Gold Hotspots (where the new fiber is).
pause
