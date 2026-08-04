@echo off
REM ===========================================================================
REM  STOP_OPTIMUS.bat  --  the OFF switch for the whole toolkit.
REM  Closes the Fiber Hunter, the Maps Scraper, their background write-workers,
REM  and ONLY the Optimus browser windows (matched by our own profile folders).
REM  Your normal Chrome / Edge and any other Python are left completely alone.
REM  Double-click anytime to turn everything off. Nothing is uninstalled.
REM ===========================================================================
title Optimus - STOP (turn everything off)
echo.
echo  Turning Optimus OFF -- Hunter, Scraper, background workers, and the
echo  Optimus browser windows only. Your normal Chrome is safe.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$self=$PID; $markers=@('precise_fiber_hunter','maps_scraper_standalone','fiber_zone_scanner','fiber_precise_pipeline','att_profile','maps_profile','optimus_hunter','maps_scraper'); $n=0; Get-CimInstance Win32_Process | ForEach-Object { $p=$_; if ($p.ProcessId -ne $self -and $p.CommandLine) { foreach ($m in $markers) { if ($p.CommandLine.ToLower().Contains($m)) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue; $n++ } catch {}; break } } } }; Write-Host ('  Stopped ' + $n + ' Optimus process(es).')"
echo.
echo  Optimus is OFF. To start again, double-click a desktop icon.
echo.
timeout /t 4 >nul
