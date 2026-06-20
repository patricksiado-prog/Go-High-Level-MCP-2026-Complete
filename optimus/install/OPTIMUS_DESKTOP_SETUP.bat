@echo off
setlocal
title Optimus Desktop Setup
set "DIR=%USERPROFILE%\optimus\launchers"
set "BASE=https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/claude/optimus-map-tools-setup-6dcl6o/optimus/install"
if not exist "%DIR%" mkdir "%DIR%"
echo.
echo  Setting up your Optimus desktop icons...
echo.
echo [1/2] Downloading launchers + icons...
curl -L -o "%DIR%\RUN_HUNTER.bat"  "%BASE%/RUN_HUNTER.bat"
curl -L -o "%DIR%\RUN_SCRAPER.bat" "%BASE%/RUN_SCRAPER.bat"
curl -L -o "%DIR%\hunter.ico"  "%BASE%/icons/hunter.ico"
curl -L -o "%DIR%\scraper.ico" "%BASE%/icons/scraper.ico"
echo [2/2] Creating the two desktop icons...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $d=[Environment]::GetFolderPath('Desktop'); $a=$w.CreateShortcut((Join-Path $d 'Optimus Fiber Hunter.lnk')); $a.TargetPath=(Join-Path $env:USERPROFILE 'optimus\launchers\RUN_HUNTER.bat'); $a.IconLocation=(Join-Path $env:USERPROFILE 'optimus\launchers\hunter.ico'); $a.WorkingDirectory=(Join-Path $env:USERPROFILE 'optimus\launchers'); $a.Save(); $b=$w.CreateShortcut((Join-Path $d 'Optimus Maps Scraper.lnk')); $b.TargetPath=(Join-Path $env:USERPROFILE 'optimus\launchers\RUN_SCRAPER.bat'); $b.IconLocation=(Join-Path $env:USERPROFILE 'optimus\launchers\scraper.ico'); $b.WorkingDirectory=(Join-Path $env:USERPROFILE 'optimus\launchers'); $b.Save()"
echo.
echo  DONE! Two icons are now on your Desktop:
echo     - Optimus Fiber Hunter   (navy map-pin)
echo     - Optimus Maps Scraper   (orange magnifier)
echo  Double-click either one. First click installs + runs; after that it just runs.
echo.
pause
