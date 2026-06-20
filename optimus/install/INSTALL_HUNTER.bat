@echo off
REM ===========================================================================
REM  INSTALL_HUNTER.bat  --  one-click installer for the OPTIMUS Fiber Hunter.
REM  Installs Python the reliable way (python.org, on PATH, so the Microsoft
REM  Store "python not found" trap can't bite), downloads the LATEST hunter
REM  from GitHub, installs the packages + browser engine + Google key, and
REM  launches it. Re-run anytime to refresh to the newest code.
REM ===========================================================================
setlocal EnableDelayedExpansion
title OPTIMUS Fiber Hunter - Installer
set "APP=%USERPROFILE%\optimus_hunter"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "ZIP=https://codeload.github.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/zip/refs/heads/%BRANCH%"
set "CREDS=https://drive.usercontent.google.com/download?id=1upYH4h2VsmOwO82v9CVjMpE6IzV-5dIs&export=download&confirm=t"

echo.
echo  ============================================================
echo     OPTIMUS FIBER HUNTER  --  installing the latest version
echo  ============================================================
echo.

echo [1/5] Python...
where py >nul 2>&1
if errorlevel 1 (
    echo     Installing Python ^(one time, ~2 min^)...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe -OutFile $env:TEMP\pysetup.exe; Start-Process $env:TEMP\pysetup.exe -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=1','Include_launcher=1' -Wait"
)
where py >nul 2>&1 || ( echo     Python install did not finish - reboot and run this file again. & pause & exit /b 1 )

echo [2/5] Downloading the latest hunter from GitHub...
if not exist "%APP%" mkdir "%APP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr '%ZIP%' -OutFile $env:TEMP\opt.zip; $ex=Join-Path $env:TEMP 'optx'; if(Test-Path $ex){Remove-Item $ex -Recurse -Force}; Expand-Archive $env:TEMP\opt.zip -DestinationPath $ex -Force; $src=(Get-ChildItem $ex -Recurse -Directory -Filter optimus | Select-Object -First 1).FullName; Copy-Item (Join-Path $src '*') '%APP%' -Recurse -Force" || ( echo     Could not reach GitHub. Check your internet. & pause & exit /b 1 )

echo [3/5] Packages...
py -m pip install --upgrade pip >nul 2>&1
py -m pip install --upgrade numpy pillow scipy playwright gspread google-auth requests mapbox-vector-tile

echo [4/5] Browser engine ^(first time can take a minute or two^)...
py -m playwright install chromium

echo [5/5] Google key ^(so it writes to your sheet^)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{iwr '%CREDS%' -OutFile '%APP%\google_creds.json'}catch{}"

cd /d "%APP%"
echo.
echo  Done. Launching the hunter:
echo    - log into AT^&T if asked
echo    - pan/zoom to a NEW area (green/gold dots = leads; all-grey = skip)
echo    - click this window, press Enter to sweep
echo.
py precise_fiber_hunter.py
echo.
echo  Closed. To run again later:  cd /d "%APP%"  then  py precise_fiber_hunter.py
pause
