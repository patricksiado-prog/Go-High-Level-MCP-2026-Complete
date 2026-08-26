@echo off
rem COUNT_TABS.bat -- how many rows are in every tab of ATT FIBER LEADS.
rem Double-click it. Prints the count for every tab (gold, green, grey, the lot)
rem and publishes the same numbers to GitHub so Claude can read them without
rem needing Google access. Reads only -- it changes nothing in the sheet.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (set PY=python) else (set PY=py -3)

echo ==========================================
echo   ATT FIBER LEADS -- ROW COUNT PER TAB
echo ==========================================
echo.
%PY% sheet_feed.py
echo.
echo Done. The 'Gold Confirmed' line above is your dialable gold count.
pause
