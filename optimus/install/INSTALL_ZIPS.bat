@echo off
REM ===========================================================================
REM  INSTALL_ZIPS.bat  --  installs the Optimus ZIP Reader as a Desktop app.
REM  Drops an "Optimus ZIP Reader" icon that AUTO-UPDATES every run. The direct
REM  reader: type nothing, it reads each ZIP off the AT&T backend and ranks the
REM  freshest green+gold areas. First launch installs the toolkit if needed.
REM ===========================================================================
setlocal
title Optimus ZIP Reader - Installer
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "BASE=https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/%BRANCH%/optimus/install"
set "DIR=%USERPROFILE%\optimus\launchers"

echo.
echo  ============================================================
echo     OPTIMUS ZIP READER  --  installing the Desktop app
echo  ============================================================
echo.
if not exist "%DIR%" mkdir "%DIR%"

echo [1/2] Downloading the launcher + icon...
curl -L -o "%DIR%\RUN_ZIPS.bat" "%BASE%/RUN_ZIPS.bat"
curl -L -o "%DIR%\zips.ico"     "%BASE%/icons/scout.ico"

echo [2/2] Creating the Desktop icon...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $d=[Environment]::GetFolderPath('Desktop'); $s=$w.CreateShortcut((Join-Path $d 'Optimus ZIP Reader.lnk')); $s.TargetPath=(Join-Path $env:USERPROFILE 'optimus\launchers\RUN_ZIPS.bat'); $s.IconLocation=(Join-Path $env:USERPROFILE 'optimus\launchers\zips.ico'); $s.WorkingDirectory=(Join-Path $env:USERPROFILE 'optimus\launchers'); $s.Save()"

echo.
echo  ============================================================
echo   DONE! A new Desktop icon "Optimus ZIP Reader" is ready.
echo   Double-click it -> a browser opens (log in if asked) -> it reads each
echo   ZIP off the AT^&T backend and ranks the freshest green+gold areas.
echo   No panning. Results: 'Fresh ZIPs' sheet tab + fresh_zips.csv +
echo   green+gold addresses in fresh_addresses.csv.
echo  ============================================================
echo.
pause
