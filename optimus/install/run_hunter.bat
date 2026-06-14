@echo off
REM ===========================================================================
REM  RUN HUNTER - hands-free fiber scan that stays current and keeps going.
REM
REM  WHAT YOU'LL SEE (this is NORMAL, not a crash):
REM    - It pulls the latest code from GitHub, then opens ONE browser on the map.
REM    - It re-scans the same area every 10 minutes IN PLACE (the map pans a bit
REM      each time). That re-scan is the tool working, not a restart.
REM    - It only fully relaunches the browser if it actually crashed/closed.
REM    - Close this window (or press Ctrl+C) to stop it for good.
REM
REM  Edit the ZIP below to change the target area.
REM ===========================================================================
setlocal
set "REPO=%USERPROFILE%\optimus\repo"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "ZIP=77027"
set "RESCAN_SECS=600"
set "RESTART_SECS=120"

cd /d "%REPO%\optimus" || (echo Repo not found at %REPO% - run install_optimus.bat first. & pause & exit /b 1)

:loop
echo.
echo ==== %DATE% %TIME%  starting scan of ZIP %ZIP% (re-scans in place every %RESCAN_SECS%s) ====
echo      (the map panning every few minutes is the re-scan -- leave it running.)
REM The hunter pulls the latest code itself on start (self-update) and then runs
REM ONE browser session that stays on the map and re-scans in place (no portal flip).
python precise_fiber_hunter.py --zip %ZIP% --net --auto --loop %RESCAN_SECS%
echo.
echo ==== the browser closed (you closed it, or it crashed). ====
echo ==== If you meant to stop, close this window now. Otherwise it reopens in %RESTART_SECS%s. ====
timeout /t %RESTART_SECS% /nobreak >nul
goto loop
