@echo off
rem FREE_SPACE.bat -- the sheet hit Google's 10,000,000 cell limit and writes
rem are failing. This makes room. Shows a DRY RUN first and changes nothing
rem until you type YES.
rem
rem The safe win: a tab is billed for its whole GRID, not the rows you filled.
rem Shrinking an over-allocated grid returns cells and deletes no data.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (set PY=python) else (set PY=py -3)

echo ============================================
echo   OPTIMUS -- FREE SHEET SPACE   (DRY RUN)
echo ============================================
%PY% free_space.py
echo.
set /p GO=Type YES to shrink over-allocated tabs (no data deleted):
if /i not "%GO%"=="YES" (
    echo Nothing changed.
    pause
    exit /b 0
)
%PY% free_space.py --yes
echo.
echo If that did not free enough, the TEST-* tabs can go too:
set /p GO2=Type YES to ALSO delete the frozen TEST-* tabs:
if /i "%GO2%"=="YES" %PY% free_space.py --drop-test --yes
echo.
pause
