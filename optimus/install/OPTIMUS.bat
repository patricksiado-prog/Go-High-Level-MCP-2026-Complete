@echo off
REM ===========================================================================
REM  OPTIMUS.bat  --  THE ONE FILE.  Double-click it (or run it from cmd).
REM
REM  It does EVERYTHING, in order, and it's safe to run every time:
REM    1. Installs Git + Python the first time (if missing).
REM    2. Pulls the latest code from GitHub.
REM    3. Installs/updates the Python packages + the Chromium browser.
REM    4. Downloads the Google key so leads write to your sheet.
REM    5. First time only: opens the AT&T map so you log in once.
REM    6. Turns on the scan: one smooth, fast, non-stop run that writes leads
REM       to your Google Sheet and adds phone numbers free.
REM
REM  After the first run, this same file is just your ON switch -- run it and
REM  walk away. Close the windows to stop.
REM
REM  Change the target area: edit ZIP= below.
REM ===========================================================================
setlocal EnableDelayedExpansion
set "HOME_DIR=%USERPROFILE%\optimus"
set "REPO=%HOME_DIR%\repo"
set "OPT=%REPO%\optimus"
set "URL=https://github.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete.git"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "CREDS_ID=1upYH4h2VsmOwO82v9CVjMpE6IzV-5dIs"
set "ZIP=77027"

title OPTIMUS Fiber Hunter
echo.
echo  ============================================================
echo     OPTIMUS  --  setting up and turning on the fiber hunter
echo  ============================================================
echo.
if not exist "%HOME_DIR%" mkdir "%HOME_DIR%"

echo [1/6] Git...
where git >nul 2>&1 || (
    winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
    set "PATH=%PATH%;%ProgramFiles%\Git\cmd"
)

echo [2/6] Python...
where python >nul 2>&1
if errorlevel 1 (
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    echo.
    echo   Python was just installed. CLOSE this window and run OPTIMUS again
    echo   so Windows can see Python.
    pause & exit /b 0
)

echo [3/6] Getting the latest code...
if exist "%REPO%\.git" (
    git -C "%REPO%" fetch origin & git -C "%REPO%" checkout %BRANCH% & git -C "%REPO%" pull origin %BRANCH%
) else (
    git clone --branch %BRANCH% %URL% "%REPO%" || (echo If a GitHub login popped up, sign in and run OPTIMUS again. & pause & exit /b 1)
)

echo [4/6] Packages + browser...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install --upgrade -r "%OPT%\install\requirements.txt"
python -m playwright install chromium

echo [5/6] Google key (so leads write to your sheet)...
python -c "import os,urllib.request,json; p=os.path.join(os.path.expanduser('~'),'optimus','google_creds.json'); urllib.request.urlretrieve('https://drive.google.com/uc?export=download&id=%CREDS_ID%', p); d=json.load(open(p)); assert d.get('project_id')=='fiberscanner-493900'; print('   key OK ->', p)" 2>nul || echo    (key not auto-downloaded -- the hunter will use any good copy already here.)

cd /d "%OPT%" || (echo Could not find %OPT% & pause & exit /b 1)

echo [6/6] Starting up...
REM First time only: no saved AT&T login yet -> open the map so you sign in once.
if not exist "%OPT%\att_profile" (
    echo.
    echo   FIRST TIME: a browser will open. Log into AT^&T, get the Fiber Map
    echo   showing, then come back here and press Enter. You only do this once.
    echo.
    python precise_fiber_hunter.py --login
)

echo.
echo  ============================================================
echo     RUNNING.  Leave it going. Close the windows to stop.
echo     Target area: %ZIP%   (edit ZIP= in this file to change)
echo  ============================================================
echo.

REM Free phone enricher alongside, its own window (OSM only, no API cost).
start "Optimus Enrich (free)" cmd /c python enrich_phones.py --watch

:loop
REM One smooth, fast, non-stop scan that writes leads to your Google Sheet.
python precise_fiber_hunter.py --zip %ZIP% --net --auto --fast --loop 5
echo.
echo  (browser closed -- reopening in 10s. Close this window to stop for good.)
timeout /t 10 /nobreak >nul
goto loop
