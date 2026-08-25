@echo off
rem CLEAN_SHEET.bat -- double-click sheet cleanup for the ATT FIBER LEADS sheet.
rem Shows a DRY RUN first (deletes nothing), then asks before doing it for real.
rem Real run: migrates TEST-Gold rows into 'Gold Confirmed', backs every tab up
rem to a local CSV, then deletes only DEBUG/TEST tabs. Pipeline tabs protected.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (set PY=python) else (set PY=py -3)

echo ============================================
echo   OPTIMUS SHEET CLEANUP  --  DRY RUN FIRST
echo ============================================
%PY% clean_sheet.py
echo.
set /p GO=Type YES to migrate gold, back up, and delete the tabs listed above:
if /i not "%GO%"=="YES" (
    echo Nothing changed.
    pause
    exit /b 0
)
%PY% clean_sheet.py --yes
echo.
pause
