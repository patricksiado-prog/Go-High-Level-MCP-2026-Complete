@echo off
REM ===========================================================================
REM  INSTALL_SCOUT.bat  --  installs the Optimus Fiber Scout as a Desktop app.
REM  Drops an "Optimus Fiber Scout" icon that AUTO-UPDATES every run. The first
REM  launch installs the whole Optimus toolkit (Python + tools) if needed.
REM  Everything comes from the PUBLIC GitHub repo -- no Drive access required.
REM ===========================================================================
setlocal
title Optimus Fiber Scout - Installer
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "BASE=https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/%BRANCH%/optimus/install"
set "DIR=%USERPROFILE%\optimus\launchers"

echo.
echo  ============================================================
echo     OPTIMUS FIBER SCOUT  --  installing the Desktop app
echo  ============================================================
echo.
if not exist "%DIR%" mkdir "%DIR%"

echo [1/2] Downloading the launcher + icon...
curl -L -o "%DIR%\RUN_SCOUT.bat" "%BASE%/RUN_SCOUT.bat"
curl -L -o "%DIR%\scout.ico"     "%BASE%/icons/scout.ico"

echo [2/2] Creating the Desktop icon...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $d=[Environment]::GetFolderPath('Desktop'); $s=$w.CreateShortcut((Join-Path $d 'Optimus Fiber Scout.lnk')); $s.TargetPath=(Join-Path $env:USERPROFILE 'optimus\launchers\RUN_SCOUT.bat'); $s.IconLocation=(Join-Path $env:USERPROFILE 'optimus\launchers\scout.ico'); $s.WorkingDirectory=(Join-Path $env:USERPROFILE 'optimus\launchers'); $s.Save()"

echo.
echo  ============================================================
echo   DONE! A new Desktop icon "Optimus Fiber Scout" is ready.
echo   Double-click it:
echo     - first run installs everything ^(one time, ~5-10 min^)
echo     - it checks for updates and runs EVERY launch ^(always newest^)
echo   It finds NEW fiber areas (green + gold, no grey) and saves a
echo   screenshot of each fresh spot to your optimus_hunter\fresh_zones folder.
echo  ============================================================
echo.
pause
