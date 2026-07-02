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
curl -L -s -o hunter_fixes.py         "%RAW%/hunter_fixes.py?cb=!CB!"
curl -L -s -o backend_classifier.py   "%RAW%/backend_classifier.py?cb=!CB!"
findstr /C:"COMBO MATCH ON" precise_fiber_hunter.py >nul 2>&1 && echo   (on the latest version) || echo   (could not refresh -- running the copy you have)

echo.
set "PYCMD=python"
where py >nul 2>&1 && set "PYCMD=py"
%PYCMD% precise_fiber_hunter.py
set "RC=%ERRORLEVEL%"
REM  0  = you closed the browser on purpose  -> stop (the only way it stays down)
REM  42 = the watchdog says it froze         -> relaunch fresh automatically
REM  anything else = it crashed              -> relaunch fresh automatically
REM  (every relaunch re-downloads the latest code first, so even a bad update
REM   heals itself on the next loop)
if "%RC%"=="0" goto :eof
echo.
if "%RC%"=="42" (
  echo   It locked up -- restarting the hunter automatically...
) else (
  echo   It stopped unexpectedly ^(code %RC%^) -- restarting automatically...
)
set "OPTIMUS_AUTORESUME=1"
timeout /t 5 >nul
goto runloop
