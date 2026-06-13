@echo off
REM ===========================================================================
REM  RUN HUNTER - self-updating, self-restarting fiber scan.
REM  Double-click it. It pulls the latest code, runs the precise hunter in
REM  unattended mode (no "press Enter" pauses), and restarts itself when the
REM  run finishes or crashes. Close the window (or Ctrl+C) to stop.
REM
REM  Edit the ZIP below to change the target area.
REM ===========================================================================
setlocal
set "REPO=%USERPROFILE%\optimus\repo"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "ZIP=77027"
set "RESTART_SECS=60"

cd /d "%REPO%\optimus" || (echo Repo not found at %REPO% - run install_optimus.bat first. & pause & exit /b 1)

:loop
echo.
echo ==== %DATE% %TIME%  updating + scanning ZIP %ZIP% ====
git -C "%REPO%" pull origin %BRANCH%
python precise_fiber_hunter.py --zip %ZIP% --net --auto
echo.
echo ==== run finished/exited. Restarting in %RESTART_SECS%s. Close window to stop. ====
timeout /t %RESTART_SECS% /nobreak >nul
goto loop
