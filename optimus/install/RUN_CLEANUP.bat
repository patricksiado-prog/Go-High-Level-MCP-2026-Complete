@echo off
REM ===========================================================================
REM  RUN_CLEANUP.bat  --  clean the ATT FIBER LEADS sheet (SAFE).
REM  1) removes DUPLICATE rows (keeps the first of each) from the pipeline tabs
REM  2) optionally removes the debug/log tabs
REM  Scans and SHOWS you the counts first; deletes nothing until you type Y.
REM  Pipeline tabs are never deleted -- only duplicate rows are removed.
REM ===========================================================================
title Optimus Sheet Cleanup
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
curl -L -s -o "dedupe_sheet.py"         "%RAW%/dedupe_sheet.py"
curl -L -s -o "clean_sheet.py"          "%RAW%/clean_sheet.py"
curl -L -s -o "precise_fiber_hunter.py" "%RAW%/precise_fiber_hunter.py"
curl -L -s -o "optimus_dot_detect.py"   "%RAW%/optimus_dot_detect.py"
curl -L -s -o "backend_classifier.py"   "%RAW%/backend_classifier.py"
curl -L -s -o "build_codes.json"        "%RAW%/build_codes.json"
curl -L -s -o "optimus_api_capture.py"  "%RAW%/optimus_api_capture.py"
curl -L -s -o "hunter_fixes.py"         "%RAW%/hunter_fixes.py"

echo.
echo ============================================================
echo   STEP 1: scanning for DUPLICATE rows BY PHONE (nothing deleted yet)
echo ============================================================
py dedupe_sheet.py --by-phone 2>nul || python dedupe_sheet.py --by-phone
echo.
set /p GO="Delete those duplicate rows? (keeps the first of each phone) [Y/N]: "
if /I "%GO%"=="Y" ( py dedupe_sheet.py --by-phone --yes 2>nul || python dedupe_sheet.py --by-phone --yes )

echo.
echo ============================================================
echo   STEP 2: debug/log tabs (optional)
echo ============================================================
py clean_sheet.py 2>nul || python clean_sheet.py
echo.
set /p GO2="Also delete those debug tabs? [Y/N]: "
if /I "%GO2%"=="Y" ( py clean_sheet.py --yes 2>nul || python clean_sheet.py --yes )

echo.
echo Done. Pipeline tabs untouched; only duplicate rows / debug tabs removed.
pause
