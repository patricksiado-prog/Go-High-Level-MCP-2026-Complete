@echo off
title Optimus Maps Scraper
if exist "%USERPROFILE%\maps_scraper\maps_scraper_standalone.py" (
  cd /d "%USERPROFILE%\maps_scraper"
  py maps_scraper_standalone.py 2>nul || python maps_scraper_standalone.py
  goto :eof
)
echo First-time setup -- installing everything, then launching...
curl -L -o "%TEMP%\IS.bat" "https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/claude/optimus-map-tools-setup-6dcl6o/optimus/install/INSTALL_SCRAPER.bat"
call "%TEMP%\IS.bat"
