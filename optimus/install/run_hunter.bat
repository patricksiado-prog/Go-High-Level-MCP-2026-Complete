@echo off
REM ===========================================================================
REM  RUN HUNTER - one smooth, fast, non-stop scan.
REM
REM  It opens the map ONCE and keeps scanning in place -- it does NOT close and
REM  reopen the browser, so there's no portal flip / "restarting". It pulls the
REM  latest code once at the start, then runs continuously and fast.
REM
REM  A second small window ("Optimus Enrich") runs alongside it and adds phone
REM  numbers FREE (OpenStreetMap, no API cost) as addresses come in.
REM
REM  The map panning every few seconds IS the scan moving across the area --
REM  that's the tool working, not a restart. Close the windows (or Ctrl+C) to stop.
REM  It only reopens the browser if it genuinely crashed.
REM
REM  Edit the ZIP below to change the target area.
REM ===========================================================================
setlocal
set "REPO=%USERPROFILE%\optimus\repo"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "ZIP=77027"
set "RESCAN_SECS=5"

cd /d "%REPO%\optimus" || (echo Repo not found at %REPO% - run install_optimus.bat first. & pause & exit /b 1)

echo.
echo ==== %DATE% %TIME%  updating once, then scanning ZIP %ZIP% non-stop (fast) ====
git -C "%REPO%" pull origin %BRANCH%

REM Start the FREE phone enricher alongside (its own window). --watch tails the
REM hunter's captures and enriches as they land. No --paid = OSM only, $0.
start "Optimus Enrich (free)" cmd /c python enrich_phones.py --watch

:loop
REM ONE long-lived browser session: stays on the map, re-scans every few seconds,
REM no reload. --fast tightens the pacing.
python precise_fiber_hunter.py --zip %ZIP% --net --auto --fast --loop %RESCAN_SECS%
echo.
echo ==== the browser actually closed (crash or you closed it). ====
echo ==== Close this window now to stop, or it reopens in 10s. ====
timeout /t 10 /nobreak >nul
goto loop
