@echo off
REM ===========================================================================
REM  INSTALL_SCRAPER.bat  --  one-click installer for the Google Maps Scraper.
REM  Installs Python the reliable way (python.org, on PATH, so the Microsoft
REM  Store "python not found" trap can't bite), downloads the LATEST scraper
REM  from GitHub, installs the packages + browser engine + Google key, and
REM  launches it. Re-run anytime to refresh to the newest code.
REM ===========================================================================
setlocal EnableDelayedExpansion
title OPTIMUS Maps Scraper - Installer
set "APP=%USERPROFILE%\maps_scraper"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "RAW=https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/%BRANCH%/optimus/standalone/maps_scraper_standalone.py"
set "CREDS=https://drive.usercontent.google.com/download?id=1upYH4h2VsmOwO82v9CVjMpE6IzV-5dIs&export=download&confirm=t"

echo.
echo  ============================================================
echo     GOOGLE MAPS SCRAPER  --  installing the latest version
echo  ============================================================
echo.

echo [1/5] Python...
where py >nul 2>&1
if errorlevel 1 (
    echo     Installing Python ^(one time, ~2 min^)...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe -OutFile $env:TEMP\pysetup.exe; Start-Process $env:TEMP\pysetup.exe -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=1','Include_launcher=1' -Wait"
)
where py >nul 2>&1 || ( echo     Python install did not finish - reboot and run this file again. & pause & exit /b 1 )

echo [2/5] Downloading the latest scraper from GitHub...
if not exist "%APP%" mkdir "%APP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr '%RAW%' -OutFile '%APP%\maps_scraper_standalone.py'" || ( echo     Could not reach GitHub. Check your internet. & pause & exit /b 1 )

echo [3/5] Packages...
py -m pip install --upgrade pip >nul 2>&1
py -m pip install --upgrade requests gspread google-auth playwright

echo [4/5] Browser engine ^(first time can take a minute or two^)...
py -m playwright install chromium

echo [5/5] Google key ^(so it writes to your sheet^)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{iwr '%CREDS%' -OutFile '%APP%\google_creds.json'}catch{}"

cd /d "%APP%"
echo.
echo  Done. Launching the scraper - type your ZIP codes when it asks.
echo.
py maps_scraper_standalone.py
echo.
echo  Closed. To run again later:  cd /d "%APP%"  then  py maps_scraper_standalone.py
pause
