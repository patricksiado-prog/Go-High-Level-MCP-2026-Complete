@echo off
REM ===========================================================================
REM  RUN_HIDE_SCOUT.bat  --  remove the SCOUT's discovery tabs from the SHARED
REM  team sheet ("ATT FIBER LEADS"), so the guys don't see your fresh green.
REM  Removes ONLY: Fiber Scout, Fresh Leads, Fresh ZIPs.
REM  SAFE: every tab is BACKED UP to a local CSV (in %USERPROFILE%\optimus\
REM  sheet_backups_...) before it's deleted, and it SHOWS you what it will do
REM  first -- nothing is deleted until you type Y. Pipeline/dialing tabs are
REM  never touched. Going forward the scout writes to your PRIVATE sheet.
REM ===========================================================================
title Optimus -- Hide Scout Tabs From Team
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
curl -L -s -o "clean_sheet.py"          "%RAW%/clean_sheet.py"
curl -L -s -o "precise_fiber_hunter.py" "%RAW%/precise_fiber_hunter.py"
curl -L -s -o "optimus_dot_detect.py"   "%RAW%/optimus_dot_detect.py"
curl -L -s -o "backend_classifier.py"   "%RAW%/backend_classifier.py"
curl -L -s -o "build_codes.json"        "%RAW%/build_codes.json"

echo.
echo ============================================================
echo   Scanning the team sheet for scout tabs (nothing deleted yet)
echo ============================================================
py clean_sheet.py --scout-only 2>nul || python clean_sheet.py --scout-only
echo.
set /p GO="Remove those scout tabs from the TEAM sheet? (backed up first) [Y/N]: "
if /I "%GO%"=="Y" (
  py clean_sheet.py --scout-only --yes 2>nul || python clean_sheet.py --scout-only --yes
) else (
  echo Skipped -- nothing was changed.
)
echo.
echo Done. The scout now writes to your PRIVATE sheet going forward.
pause
