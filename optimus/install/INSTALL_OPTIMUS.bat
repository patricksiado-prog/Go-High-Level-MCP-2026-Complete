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
REM whole repo (brings every module) -- gets the full file set...
powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr '%ZIP%' -OutFile $env:TEMP\opt.zip; $ex=Join-Path $env:TEMP 'optx'; if(Test-Path $ex){Remove-Item $ex -Recurse -Force}; Expand-Archive $env:TEMP\opt.zip -DestinationPath $ex -Force; $src=(Get-ChildItem $ex -Recurse -Directory -Filter optimus | Select-Object -First 1).FullName; Copy-Item (Join-Path $src '*') '%HUNTER%' -Recurse -Force" || ( echo     Could not reach GitHub. Check your internet. & pause & exit /b 1 )
REM ...then FORCE the core files straight from raw with a cache-buster, so even if
REM the repo-zip CDN is stale you still get the newest hunter code (this is what
REM kept people on old code before).
set "CB=%RANDOM%%RANDOM%"
curl -L -o "%HUNTER%\precise_fiber_hunter.py" "%RAW%/precise_fiber_hunter.py?cb=%CB%"
curl -L -o "%HUNTER%\optimus_dot_detect.py"   "%RAW%/optimus_dot_detect.py?cb=%CB%"
curl -L -o "%HUNTER%\optimus_api_capture.py"  "%RAW%/optimus_api_capture.py?cb=%CB%"
curl -L -o "%HUNTER%\hunter_fixes.py"         "%RAW%/hunter_fixes.py?cb=%CB%"
curl -L -o "%HUNTER%\backend_classifier.py"   "%RAW%/backend_classifier.py?cb=%CB%"
REM build_codes.json is REQUIRED for gold vs grey: without it every fiber
REM customer would misclassify. Download it here too (not just in the launcher).
curl -L -o "%HUNTER%\build_codes.json"        "%RAW%/build_codes.json?cb=%CB%"
REM VERIFY we actually got the CURRENT build (only new code says "GOLD CAPTURE ON").
REM The old marker "COMBO MATCH ON" lived in stale code too, so a failed/cached
REM download looked like success -- that is exactly what stranded people on old code.
findstr /C:"GOLD CAPTURE ON" "%HUNTER%\precise_fiber_hunter.py" >nul 2>&1
if errorlevel 1 (
  echo     ^*^* WARNING: still got OLD hunter code ^(GitHub cache or no internet^).
  echo        Wait 60 seconds and run this installer again -- it will pick up the
  echo        new version once GitHub's cache clears.
) else (
  for /f "delims=" %%L in ('findstr /C:"BUILD_DATE = " "%HUNTER%\precise_fiber_hunter.py"') do echo     OK - newest Fiber Hunter confirmed -- %%L
)

echo [3/7] Downloading the Maps Scraper from GitHub...
if not exist "%SCRAPER%" mkdir "%SCRAPER%"
curl -L -o "%SCRAPER%\maps_scraper_standalone.py" "%SCRAPERPY%?cb=%CB%" || ( echo     Could not reach GitHub. Check your internet. & pause & exit /b 1 )

echo [4/7] Packages ^(both tools^)...
py -m pip install --upgrade pip >nul 2>&1
py -m pip install --upgrade numpy pillow scipy playwright gspread google-auth requests mapbox-vector-tile

echo [5/7] Browser engine ^(first time can take a minute or two^)...
py -m playwright install chromium

echo [6/7] Google key ^(public link - lets the tools write to the sheet; no Drive access needed^)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{iwr '%CREDS%' -OutFile '%HUNTER%\google_creds.json'}catch{}"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{Copy-Item '%HUNTER%\google_creds.json' '%SCRAPER%\google_creds.json' -Force}catch{}"

echo [7/7] Creating the two Desktop icons...
if not exist "%LAUNCH%" mkdir "%LAUNCH%"
curl -L -o "%LAUNCH%\RUN_HUNTER.bat"  "%BASE%/RUN_HUNTER.bat"
curl -L -o "%LAUNCH%\RUN_SCRAPER.bat" "%BASE%/RUN_SCRAPER.bat"
curl -L -o "%LAUNCH%\hunter.ico"  "%BASE%/icons/hunter.ico"
curl -L -o "%LAUNCH%\scraper.ico" "%BASE%/icons/scraper.ico"
REM ONE hunter icon only -- the old "V200K (June build)" third icon was dropped
REM (Patrick, 2026-08-17: it confused the team and kept people on the frozen old
REM build). Clean up a stale V200K shortcut from a prior install if present.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); Remove-Item (Join-Path $d 'Optimus Hunter V200K (June build).lnk') -Force -ErrorAction SilentlyContinue"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $d=[Environment]::GetFolderPath('Desktop'); $a=$w.CreateShortcut((Join-Path $d 'Optimus Fiber Hunter.lnk')); $a.TargetPath=(Join-Path $env:USERPROFILE 'optimus\launchers\RUN_HUNTER.bat'); $a.IconLocation=(Join-Path $env:USERPROFILE 'optimus\launchers\hunter.ico'); $a.WorkingDirectory=(Join-Path $env:USERPROFILE 'optimus\launchers'); $a.Save(); $b=$w.CreateShortcut((Join-Path $d 'Optimus Maps Scraper.lnk')); $b.TargetPath=(Join-Path $env:USERPROFILE 'optimus\launchers\RUN_SCRAPER.bat'); $b.IconLocation=(Join-Path $env:USERPROFILE 'optimus\launchers\scraper.ico'); $b.WorkingDirectory=(Join-Path $env:USERPROFILE 'optimus\launchers'); $b.Save()"

echo.
echo  ============================================================
echo   DONE! Python + the tools are installed.
echo   TWO icons are now on your Desktop:
echo      - Optimus Fiber Hunter   ^(this is THE hunter -- always the latest^)
echo      - Optimus Maps Scraper   ^(type ZIP codes when it asks^)
echo   Double-click either one to run.
echo  ============================================================
echo.
pause
