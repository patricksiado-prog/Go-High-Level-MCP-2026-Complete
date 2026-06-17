@echo off
REM ===========================================================================
REM  GOOGLE MAPS BUSINESS SCRAPER -- one-file setup + run.
REM  Double-click it. First time: installs Python + the browser engine, then
REM  downloads the scraper "guts" from Drive and runs it. After that it just
REM  re-downloads the latest guts and runs -- so updates are automatic.
REM ===========================================================================
title Google Maps Business Scraper
setlocal EnableDelayedExpansion
set "HOME_DIR=%USERPROFILE%\maps_scraper"
set "PY=%HOME_DIR%\maps_scraper_standalone.py"
set "PYID=1yn-n5r85RSadIAben00F2MEAIA05E4oz"
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

echo [2/3] Browser engine...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install --upgrade playwright
python -m playwright install chromium

echo [3/3] Getting the latest scraper...
python -c "import urllib.request; urllib.request.urlretrieve('https://drive.google.com/uc?export=download^&id=%PYID%', r'%PY%')" || (echo Could not download the scraper - check the Drive link is shared. & pause & exit /b 1)

echo.
echo  Starting the scraper. A browser opens -- enter your ZIPs when asked.
echo.
python "%PY%"
echo.
echo  Finished. Your results are in:  %HOME_DIR%\businesses.csv
pause
