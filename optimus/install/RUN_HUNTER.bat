@echo off
REM ===========================================================================
REM  RUN_HUNTER.bat  --  the Fiber Hunter desktop launcher.
REM  KEY: it RE-DOWNLOADS the newest hunter code from GitHub every single launch
REM  (cache-busted), THEN runs it. So the icon can never be stuck on old code --
REM  clicking it always gets the latest. (Belt-and-suspenders with the program's
REM  own self_update.)
REM ===========================================================================
title Optimus Fiber Hunter
setlocal EnableDelayedExpansion
set "RAW=https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/claude/optimus-map-tools-setup-6dcl6o/optimus"

REM pick the install folder (ZIP-install first, then the git-clone layout)
set "APP=%USERPROFILE%\optimus_hunter"
if not exist "%APP%\precise_fiber_hunter.py" if exist "%USERPROFILE%\optimus\repo\optimus\precise_fiber_hunter.py" set "APP=%USERPROFILE%\optimus\repo\optimus"

REM first time ever -> run the full installer
if not exist "%APP%\precise_fiber_hunter.py" (
  echo First-time setup -- installing everything, then launching...
  curl -L -o "%TEMP%\IO.bat" "%RAW%/install/INSTALL_OPTIMUS.bat"
  call "%TEMP%\IO.bat"
  goto :eof
)

cd /d "%APP%"

:runloop
echo Checking for the latest version...
set "CB=%RANDOM%%RANDOM%"
curl -L -s -o precise_fiber_hunter.py "%RAW%/precise_fiber_hunter.py?cb=!CB!"
curl -L -s -o optimus_dot_detect.py   "%RAW%/optimus_dot_detect.py?cb=!CB!"
curl -L -s -o optimus_api_capture.py  "%RAW%/optimus_api_capture.py?cb=!CB!"
findstr /C:"COMBO MATCH ON" precise_fiber_hunter.py >nul 2>&1 && echo   (on the latest version) || echo   (could not refresh -- running the copy you have)

echo.
py precise_fiber_hunter.py 2>nul || python precise_fiber_hunter.py
REM exit code 42 = the watchdog decided it froze -> relaunch fresh automatically.
if errorlevel 42 (
  echo.
  echo   It locked up -- restarting the hunter automatically...
  set "OPTIMUS_AUTORESUME=1"
  timeout /t 3 >nul
  goto runloop
)
