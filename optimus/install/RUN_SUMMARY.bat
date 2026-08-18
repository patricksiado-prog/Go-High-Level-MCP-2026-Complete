@echo off
REM ===========================================================================
REM  RUN_SUMMARY.bat -- builds the small "OPTIMUS DATA SUMMARY" sheet Claude can
REM  read. Runs in the hunter's folder (all the modules + google_creds are there),
REM  re-downloads the latest code each launch, then refreshes the summary every
REM  15 minutes. Leave it running in the background; close the window to stop.
REM ===========================================================================
title Optimus Data Summary
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

echo Getting the latest summary tool...
set "CB=%RANDOM%%RANDOM%"
curl -L -sf -o optimus_summary.py.new "%RAW%/optimus_summary.py?cb=!CB!" && move /y optimus_summary.py.new optimus_summary.py >nul || echo   (could not refresh -- using the copy you have)
del /q *.new 2>nul

echo.
set "PYCMD=python"
where py >nul 2>&1 && set "PYCMD=py"
%PYCMD% optimus_summary.py --loop 15
echo.
echo (summary stopped)
pause
