@echo off
title Optimus Fiber Hunter
if exist "%USERPROFILE%\optimus_hunter\precise_fiber_hunter.py" (
  cd /d "%USERPROFILE%\optimus_hunter"
  py precise_fiber_hunter.py 2>nul || python precise_fiber_hunter.py
  goto :eof
)
if exist "%USERPROFILE%\optimus\repo\optimus\precise_fiber_hunter.py" (
  cd /d "%USERPROFILE%\optimus\repo\optimus"
  python precise_fiber_hunter.py 2>nul || py precise_fiber_hunter.py
  goto :eof
)
echo First-time setup -- installing everything, then launching...
curl -L -o "%TEMP%\IH.bat" "https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/claude/optimus-map-tools-setup-6dcl6o/optimus/install/INSTALL_HUNTER.bat"
call "%TEMP%\IH.bat"
