@echo off
REM ===========================================================================
REM  go.bat  --  THE RUN LOGIC.  Lives in the repo, so `git pull` refreshes it
REM  every time. OPTIMUS.bat (the on-switch) just calls this, which means the
REM  behavior updates from GitHub automatically and the on-switch NEVER needs
REM  to be re-downloaded again.
REM ===========================================================================
setlocal
set "OPT=%USERPROFILE%\optimus\repo\optimus"
cd /d "%OPT%" || (echo Could not find %OPT% - run OPTIMUS again. & pause & exit /b 1)

REM First time only: no saved AT&T login yet -> open the map so you sign in once.
if not exist "%OPT%\att_profile" (
    echo.
    echo   FIRST TIME: a browser opens. Log into AT^&T, get the Fiber Map showing,
    echo   then come back here and press Enter. You only do this once.
    echo.
    python precise_fiber_hunter.py --login
)

echo.
echo  ============================================================
echo     READY.  A browser opens to the AT^&T Fiber Map.
echo     1) Log in if asked, and pan/zoom to the area you want.
echo     2) Come back to this window and press Enter to START.
echo     It scans that area and keeps going. Close the browser
echo     (or this window) to stop. It will NOT reopen.
echo  ============================================================
echo.

REM Free phone enricher alongside, its own window (OSM only, no API cost).
start "Optimus Enrich (free)" cmd /c python enrich_phones.py --watch

REM MANUAL start (no --auto): you position the map, press Enter, it reads the
REM dots in THE CURRENT VIEW only (--cols 1 --rows 1 = no auto-panning, so it
REM can't bump itself to the portal), then re-checks in place every 30s. Pan the
REM map yourself to cover new ground. No reopen loop = never restarts.
python precise_fiber_hunter.py --cols 1 --rows 1 --loop 30

echo.
echo  Stopped. To run again, just start OPTIMUS again.
pause
