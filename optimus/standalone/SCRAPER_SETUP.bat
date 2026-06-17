@echo off
REM ===========================================================================
REM  GOOGLE MAPS BUSINESS SCRAPER -- one permanent launcher (the link never
REM  changes). It is a THIN on-switch: every run it RE-DOWNLOADS the latest
REM  scraper ("guts") from Drive, then runs it -- so the program auto-updates
REM  itself each run with nothing for the user to do but have this link.
REM  To publish an update WITHOUT changing the link: replace the guts file in
REM  Drive (right-click -> Manage versions -> Upload new version). Same id, same
REM  link, new code -- everyone gets it next run.
REM ===========================================================================
title Google Maps Business Scraper
setlocal EnableDelayedExpansion
set "HOME_DIR=%USERPROFILE%\maps_scraper"
set "PY=%HOME_DIR%\maps_scraper_standalone.py"
set "CREDS=%HOME_DIR%\google_creds.json"
set "PYID=1jRFrgO-2kkqCWrwF0MN1uUFv81vDMEEy"
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

echo [3/3] Getting the latest scraper ^(auto-update, every run^)...
python -c "import urllib.request; urllib.request.urlretrieve('https://drive.google.com/uc?export=download^&id=%PYID%', r'%PY%')" || (echo Could not download the scraper - make sure the Drive guts file is shared. & pause & exit /b 1)
python -c "import urllib.request; urllib.request.urlretrieve('https://drive.google.com/uc?export=download^&id=%CREDSID%', r'%CREDS%')" 2>nul || echo    (key not downloaded -- CSV output still works fine.)

echo.
echo  Starting the scraper. A browser opens -- enter your ZIPs when asked.
echo.
python "%PY%"
echo.
echo  Finished. Your CSV is in:  %HOME_DIR%\businesses.csv
pause
