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
REM download to a TEMP name first, and ONLY replace the real file if the download
REM actually succeeded (-f = fail on HTTP error) AND the new file is really the
REM current build. A failed/cached curl must NOT masquerade as "latest" -- that
REM silent lie is exactly what stranded PCs on old code. (goto-based, not
REM &&/|| nesting, so the batch parser can't choke on it.)
set "DLOK=1"
curl -L -sf -o precise_fiber_hunter.py.new "%RAW%/precise_fiber_hunter.py?cb=!CB!" || set "DLOK=0"
curl -L -sf -o optimus_dot_detect.py.new  "%RAW%/optimus_dot_detect.py?cb=!CB!"  || set "DLOK=0"
curl -L -sf -o optimus_api_capture.py.new "%RAW%/optimus_api_capture.py?cb=!CB!" || set "DLOK=0"
curl -L -sf -o hunter_fixes.py.new        "%RAW%/hunter_fixes.py?cb=!CB!"        || set "DLOK=0"
curl -L -sf -o backend_classifier.py.new  "%RAW%/backend_classifier.py?cb=!CB!"  || set "DLOK=0"
curl -L -sf -o build_codes.json.new       "%RAW%/build_codes.json?cb=!CB!"       || set "DLOK=0"
if not "!DLOK!"=="1" goto :dlfail
REM only trust the download if the fresh main file is really the current build
findstr /C:"GOLD CAPTURE ON" precise_fiber_hunter.py.new >nul 2>&1 || goto :dlbad
move /y precise_fiber_hunter.py.new precise_fiber_hunter.py >nul
move /y optimus_dot_detect.py.new   optimus_dot_detect.py   >nul
move /y optimus_api_capture.py.new  optimus_api_capture.py  >nul
move /y hunter_fixes.py.new         hunter_fixes.py         >nul
move /y backend_classifier.py.new   backend_classifier.py   >nul
move /y build_codes.json.new        build_codes.json        >nul
for /f "delims=" %%L in ('findstr /C:"BUILD_DATE = " precise_fiber_hunter.py') do echo   UPDATED to latest -- %%L
goto :dldone
:dlbad
echo   *** Update looked stale/partial ^(GitHub cache^) -- keeping the copy you have. ***
echo   *** If this shows an OLD build, wait 60s and relaunch, or re-run INSTALL_OPTIMUS.bat. ***
goto :dldone
:dlfail
echo   *** COULD NOT REACH GITHUB -- running the copy you already have. ***
echo   *** If this window shows an OLD build, get on the internet and relaunch, ***
echo   *** or re-run INSTALL_OPTIMUS.bat to force a clean update. ***
:dldone
del /q *.new 2>nul

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
