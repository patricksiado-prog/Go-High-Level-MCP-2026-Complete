@echo off
rem FIND_NEW_FIBER.bat -- the "go find fibre nobody has worked yet" button.
rem
rem The normal sweep spirals outward from wherever the map happens to sit. This
rem one reads the AT&T build-out news first, then flies to each town the news
rem named and sweeps it. Fresh green, in towns lit recently enough that nobody
rem has called them.
rem
rem If there is no news that launch it falls back to the normal sweep, so it is
rem never idle.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (set PY=python) else (set PY=py -3)

echo ================================================================
echo   OPTIMUS  --  FIND NEW FIBER
echo ================================================================
echo.
echo   BEFORE YOU START: log in to youachieve.att.com in Chrome and
echo   open the dealer MAP (not the account chooser). If the hunter
echo   sees a login page it captures nothing.
echo.
echo   While it runs:
echo     Ctrl+Shift+Pause   PAUSE / RESUME -- same key both ways
echo     Ctrl+Shift+Y       GO from the view on screen right now
echo     Ctrl+Shift+S       STOP -- finishes the cell, closes clean
echo     Ctrl+Shift+K       KILL -- force-quit if it ever freezes
echo.
pause
%PY% precise_fiber_hunter.py --follow-news --cells-per-target 12
echo.
echo   Done. Green dots = fibre live, NOT an AT&T customer = the $500 lead.
pause
