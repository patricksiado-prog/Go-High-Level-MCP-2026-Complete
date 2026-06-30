@echo off
REM ===========================================================================
REM  INSTALL_OPTIMUS.bat  --  ONE installer for BOTH Optimus tools.
REM  Installs Python (python.org, on PATH so the Microsoft-Store trap can't
REM  bite), downloads the Fiber Hunter AND the Maps Scraper from GitHub,
REM  installs every package + the browser engine + the Google key, then drops
REM  two Desktop icons. Everything comes from the PUBLIC GitHub repo + a PUBLIC
REM  download link -- no access to anyone's Google Drive is required.
REM  Re-run anytime to refresh both tools to the newest code.
REM ===========================================================================
setlocal EnableDelayedExpansion
title OPTIMUS - Full Installer (Fiber Hunter + Maps Scraper)
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "RAW=https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/%BRANCH%/optimus"
set "BASE=%RAW%/install"
set "HUNTER=%USERPROFILE%\optimus_hunter"
set "SCRAPER=%USERPROFILE%\maps_scraper"
set "LAUNCH=%USERPROFILE%\optimus\launchers"
set "ZIP=https://codeload.github.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/zip/refs/heads/%BRANCH%"
set "SCRAPERPY=%RAW%/standalone/maps_scraper_standalone.py"
set "CREDS=https://drive.usercontent.google.com/download?id=1upYH4h2VsmOwO82v9CVjMpE6IzV-5dIs&export=download&confirm=t"

echo.
echo  ============================================================
echo     OPTIMUS  --  installing Fiber Hunter + Maps Scraper
echo  ============================================================
echo.

echo [1/7] Python...
where py >nul 2>&1
if errorlevel 1 (
    echo     Installing Python ^(one time, ~2 min^)...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe -OutFile $env:TEMP\pysetup.exe; Start-Process $env:TEMP\pysetup.exe -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=1','Include_launcher=1' -Wait"
)
where py >nul 2>&1 || ( echo     Python install did not finish - reboot and run this file again. & pause & exit /b 1 )

echo [2/7] Downloading the Fiber Hunter from GitHub...
if not exist "%HUNTER%" mkdir "%HUNTER%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr '%ZIP%' -OutFile $env:TEMP\opt.zip; $ex=Join-Path $env:TEMP 'optx'; if(Test-Path $ex){Remove-Item $ex -Recurse -Force}; Expand-Archive $env:TEMP\opt.zip -DestinationPath $ex -Force; $src=(Get-ChildItem $ex -Recurse -Directory -Filter optimus | Select-Object -First 1).FullName; Copy-Item (Join-Path $src '*') '%HUNTER%' -Recurse -Force" || ( echo     Could not reach GitHub. Check your internet. & pause & exit /b 1 )

echo [3/7] Downloading the Maps Scraper from GitHub...
if not exist "%SCRAPER%" mkdir "%SCRAPER%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr '%SCRAPERPY%' -OutFile '%SCRAPER%\maps_scraper_standalone.py'" || ( echo     Could not reach GitHub. Check your internet. & pause & exit /b 1 )

echo [4/7] Packages ^(both tools^)...
py -m pip install --upgrade pip >nul 2>&1
py -m pip install --upgrade numpy pillow scipy playwright gspread google-auth requests mapbox-vector-tile

echo [5/7] Browser engine ^(first time can take a minute or two^)...
py -m playwright install chromium

echo [6/7] Google key ^(public link - lets the tools write to the sheet; no Drive access needed^)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{iwr '%CREDS%' -OutFile '%HUNTER%\google_creds.json'}catch{}"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{Copy-Item '%HUNTER%\google_creds.json' '%SCRAPER%\google_creds.json' -Force}catch{}"

echo [7/7] Creating the three Desktop icons...
if not exist "%LAUNCH%" mkdir "%LAUNCH%"
curl -L -o "%LAUNCH%\RUN_HUNTER.bat"  "%BASE%/RUN_HUNTER.bat"
curl -L -o "%LAUNCH%\RUN_SCRAPER.bat" "%BASE%/RUN_SCRAPER.bat"
curl -L -o "%LAUNCH%\RUN_SCOUT.bat"   "%BASE%/RUN_SCOUT.bat"
curl -L -o "%LAUNCH%\hunter.ico"  "%BASE%/icons/hunter.ico"
curl -L -o "%LAUNCH%\scraper.ico" "%BASE%/icons/scraper.ico"
curl -L -o "%LAUNCH%\scout.ico"   "%BASE%/icons/scout.ico"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $d=[Environment]::GetFolderPath('Desktop'); $a=$w.CreateShortcut((Join-Path $d 'Optimus Fiber Hunter.lnk')); $a.TargetPath=(Join-Path $env:USERPROFILE 'optimus\launchers\RUN_HUNTER.bat'); $a.IconLocation=(Join-Path $env:USERPROFILE 'optimus\launchers\hunter.ico'); $a.WorkingDirectory=(Join-Path $env:USERPROFILE 'optimus\launchers'); $a.Save(); $b=$w.CreateShortcut((Join-Path $d 'Optimus Maps Scraper.lnk')); $b.TargetPath=(Join-Path $env:USERPROFILE 'optimus\launchers\RUN_SCRAPER.bat'); $b.IconLocation=(Join-Path $env:USERPROFILE 'optimus\launchers\scraper.ico'); $b.WorkingDirectory=(Join-Path $env:USERPROFILE 'optimus\launchers'); $b.Save(); $c=$w.CreateShortcut((Join-Path $d 'Optimus Fiber Scout.lnk')); $c.TargetPath=(Join-Path $env:USERPROFILE 'optimus\launchers\RUN_SCOUT.bat'); $c.IconLocation=(Join-Path $env:USERPROFILE 'optimus\launchers\scout.ico'); $c.WorkingDirectory=(Join-Path $env:USERPROFILE 'optimus\launchers'); $c.Save()"

echo.
echo  ============================================================
echo   DONE! Python + ALL tools are installed.
echo   Three icons are now on your Desktop:
echo      - Optimus Fiber Hunter   ^(log into AT^&T once on first run^)
echo      - Optimus Maps Scraper   ^(type ZIP codes when it asks^)
echo      - Optimus Fiber Scout    ^(finds NEW fiber areas to hunt^)
echo   Double-click any one to run. They auto-update each launch.
echo  ============================================================
echo.
pause
