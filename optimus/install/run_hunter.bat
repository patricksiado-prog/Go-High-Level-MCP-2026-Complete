@echo off
REM ===========================================================================
REM  RUN HUNTER - restart-every-cycle, always-latest fiber scan.
REM
REM  HOW IT WORKS (by design):
REM    1. Pull the latest code from GitHub.
REM    2. Run ONE scan pass of the ZIP (opens the map, captures, writes to Drive).
REM    3. Close, wait a few seconds, and GO BACK TO STEP 1 -- pulling fresh code
REM       again, so every cycle runs the newest fixes automatically.
REM
REM  So each loop is a fresh restart on the latest code. As fixes get pushed,
REM  this picks them up on the very next cycle -- no reinstall, no babysitting.
REM  Close this window (or Ctrl+C) to stop.
REM
REM  Edit the ZIP below to change the target area.
REM ===========================================================================
setlocal
set "REPO=%USERPROFILE%\optimus\repo"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "ZIP=77027"
set "WAIT_SECS=20"

cd /d "%REPO%\optimus" || (echo Repo not found at %REPO% - run install_optimus.bat first. & pause & exit /b 1)

:loop
echo.
echo ==== %DATE% %TIME%  pulling latest code, then scanning ZIP %ZIP% ====
git -C "%REPO%" pull origin %BRANCH%
REM One fresh pass on the newest code (the hunter also self-updates on start).
python precise_fiber_hunter.py --zip %ZIP% --net --auto
echo.
echo ---- adding phone numbers (FREE OpenStreetMap lookup, no API cost) ----
REM No --paid flag = OSM only, $0. Never calls the paid Google Places API.
python enrich_phones.py
echo.
echo ==== pass done. Restarting on the latest code in %WAIT_SECS%s. Close window to stop. ====
timeout /t %WAIT_SECS% /nobreak >nul
goto loop
