@echo off
REM ===========================================================================
REM  RUN_V200K.bat  --  the EXACT June program that pulled the 200k green dots
REM  (commit 02ba61a, 2026-06-18), frozen byte-for-byte. It NEVER self-updates,
REM  so it stays this version forever. Uses your existing AT&T login + Google
REM  key (same folder as the regular hunter).
REM
REM  ONE flag, the June program's own: --no-match. It skips the live business
REM  re-read that today (at 18k+ scraped rows) freezes the motion mid-pan --
REM  the one thing that ended the June streak. Dots capture EXACTLY the same;
REM  business matching still happens from the scraper's side.
REM ===========================================================================
title Optimus Fiber Hunter V200K (the June build)
setlocal EnableDelayedExpansion
set "RAW=https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/claude/optimus-map-tools-setup-6dcl6o/optimus"

set "APP=%USERPROFILE%\optimus_hunter"
if not exist "%APP%\optimus_dot_detect.py" (
  echo First-time setup -- installing Optimus once, then launching V200K...
  curl -L -o "%TEMP%\IO.bat" "%RAW%/install/INSTALL_OPTIMUS.bat"
  call "%TEMP%\IO.bat"
)

cd /d "%APP%"
set "CB=%RANDOM%%RANDOM%"
curl -L -s -o precise_fiber_hunter_v200k.py "%RAW%/v200k/precise_fiber_hunter_v200k.py?cb=!CB!"

REM the June build stays EXACTLY the June build -- no self-update, ever.
set "OPTIMUS_NO_UPDATE=1"

:runloop
echo.
echo   ============================================================
echo    V200K -- the June 18 build, byte-for-byte. Position the map,
echo    press Enter, it sweeps. Close the browser to stop.
echo   ============================================================
echo.
set "PYCMD=python"
where py >nul 2>&1 && set "PYCMD=py"
%PYCMD% precise_fiber_hunter_v200k.py --no-match
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" goto :eof
echo.
echo   It stopped unexpectedly ^(code %RC%^) -- restarting automatically...
timeout /t 5 >nul
goto runloop
