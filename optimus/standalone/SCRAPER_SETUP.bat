@echo off
REM ===========================================================================
REM  GOOGLE MAPS BUSINESS SCRAPER -- one permanent launcher (the link never
REM  changes). It is a THIN on-switch: every run it RE-DOWNLOADS the latest
REM  scraper from GITHUB (public repo, no login), then runs it -- so the program
REM  auto-updates itself each run with nothing for the user to do but have this
REM  link. To publish an update: just commit to GitHub -- the next run pulls it.
REM ===========================================================================
title Google Maps Business Scraper
setlocal EnableDelayedExpansion
set "HOME_DIR=%USERPROFILE%\maps_scraper"
set "PY=%HOME_DIR%\maps_scraper_standalone.py"
set "CREDS=%HOME_DIR%\google_creds.json"
set "RAW=https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/claude/optimus-map-tools-setup-6dcl6o/optimus/standalone/maps_scraper_standalone.py"
set "CREDSID=1upYH4h2VsmOwO82v9CVjMpE6IzV-5dIs"
if not exist "%HOME_DIR%" mkdir "%HOME_DIR%"

echo.
echo  ============================================================
echo     GOOGLE MAPS BUSINESS SCRAPER
echo  ============================================================
echo.

echo [1/3] Python...
where python >nul 2>&1
if errorlevel 1 (
    echo    Installing Python ^(one time^)...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    echo.
    echo    Python was just installed. CLOSE this window and run this file
    echo    ONE more time so Windows can see Python.
    pause & exit /b 0
)

echo [2/3] Browser engine + sheet support...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install --upgrade playwright gspread google-auth
python -m playwright install chromium

echo [3/3] Getting the latest scraper from GitHub ^(auto-update, every run^)...
python -c "import urllib.request; urllib.request.urlretrieve('%RAW%', r'%PY%')" || (echo Could not reach GitHub. Check your internet. & pause & exit /b 1)
REM verify we got real Python, not an error page
findstr /C:"def main" "%PY%" >nul 2>&1 || (
    echo.
    echo   *** The scraper did not download correctly. ***
    echo   Check your internet and run this file again.
    echo.
    pause & exit /b 1
)
python -c "import urllib.request; urllib.request.urlretrieve('https://drive.usercontent.google.com/download?id=%CREDSID%^&export=download^&confirm=t', r'%CREDS%')" 2>nul || echo    (key not downloaded -- CSV output still works fine.)

echo.
echo  Starting the scraper. A browser opens -- enter your ZIPs when asked.
echo.
python "%PY%"
echo.
echo  Finished. Your CSV is in:  %HOME_DIR%\businesses.csv
pause
