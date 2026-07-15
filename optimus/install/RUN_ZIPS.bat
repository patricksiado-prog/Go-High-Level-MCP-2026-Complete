@echo off
REM ===========================================================================
REM  RUN_ZIPS.bat  --  desktop launcher for the Optimus ZIP Reader.
REM  THE DIRECT READER: reads each ZIP's fiber dots straight off the AT&T
REM  backend (no panning), ranks the freshest green+gold ZIPs, and saves the
REM  green+gold addresses. AUTO-UPDATES every run.
REM ===========================================================================
title Optimus ZIP Reader
setlocal
set "APP=%USERPROFILE%\optimus_hunter"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "RAW=https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/%BRANCH%/optimus"

if not exist "%APP%\precise_fiber_hunter.py" (
  echo First-time setup -- installing Optimus ^(Python + tools^), one time...
  curl -L -o "%TEMP%\IO.bat" "%RAW%/install/INSTALL_OPTIMUS.bat"
  call "%TEMP%\IO.bat"
)

cd /d "%APP%"
echo Checking for updates...
curl -L -s -o "zip_reader.py"           "%RAW%/zip_reader.py"
curl -L -s -o "optimus_dot_detect.py"   "%RAW%/optimus_dot_detect.py"
curl -L -s -o "precise_fiber_hunter.py" "%RAW%/precise_fiber_hunter.py"
curl -L -s -o "optimus_api_capture.py"  "%RAW%/optimus_api_capture.py"
curl -L -s -o "hunter_fixes.py"         "%RAW%/hunter_fixes.py"
curl -L -s -o "backend_classifier.py"   "%RAW%/backend_classifier.py"
curl -L -s -o "build_codes.json"        "%RAW%/build_codes.json"

echo.
echo Optimus ZIP Reader -- reads fresh fiber straight from the AT^&T backend.
echo A browser opens; log in if asked. It then reads each ZIP automatically and
echo ranks the freshest (most green+gold). No panning.
echo.
echo   - default Houston metro-edge ZIP list, OR pass your own:
echo       double-click = default list
echo       or run:  py zip_reader.py 77493 77433 77515
echo.
py zip_reader.py %* 2>nul || python zip_reader.py %*
echo.
echo Done. Fresh ZIPs -> 'Fresh ZIPs' sheet tab + fresh_zips.csv
echo Green+gold addresses -> fresh_addresses.csv
pause
