@echo off
rem GHL_TO_SHEET.bat -- pull the worked leads out of GoHighLevel and into the
rem 'GHL Worked Leads' tab: phone, notes, tags, whether the number is textable.
rem
rem That tab is NOT hunter-owned. The hunter never writes it, so it is the ONE
rem tab you can safely sort, colour and add dispositions to. The DISPOSITION,
rem SOLD? and 'Notes From Rep' columns are yours -- re-running keeps whatever
rem was typed there.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (set PY=python) else (set PY=py -3)

echo ============================================
echo   GHL  ->  SHEET      (DRY RUN FIRST)
echo ============================================
%PY% ghl_to_sheet.py
echo.
set /p GO=Type YES to write the 'GHL Worked Leads' tab:
if /i not "%GO%"=="YES" (
    echo Nothing changed.
    pause
    exit /b 0
)
%PY% ghl_to_sheet.py --yes
echo.
pause
