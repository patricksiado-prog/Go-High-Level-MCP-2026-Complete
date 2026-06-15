@echo off
REM ===========================================================================
REM  OPTIMUS.bat  --  THE ONE FILE / ON-SWITCH.  Double-click it (or run in cmd).
REM
REM  This file is now PERMANENT -- you never need to re-download it again.
REM  All it does is: install the basics (first time), pull the latest code from
REM  GitHub, then hand off to go.bat (which lives in the repo and updates itself
REM  every time). So every fix -- even to how it runs -- arrives automatically.
REM
REM  First run sets things up and logs you into the map once. After that it's
REM  just your ON button: run it, position the map, press Enter, it scans.
REM ===========================================================================
setlocal EnableDelayedExpansion
set "HOME_DIR=%USERPROFILE%\optimus"
set "REPO=%HOME_DIR%\repo"
set "OPT=%REPO%\optimus"
set "URL=https://github.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete.git"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "CREDS_ID=1upYH4h2VsmOwO82v9CVjMpE6IzV-5dIs"

title OPTIMUS Fiber Hunter
echo.
echo  ============================================================
echo     OPTIMUS  --  updating and turning on the fiber hunter
echo  ============================================================
echo.
if not exist "%HOME_DIR%" mkdir "%HOME_DIR%"

echo [1/5] Git...
where git >nul 2>&1 || (
    winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
    set "PATH=%PATH%;%ProgramFiles%\Git\cmd"
)

echo [2/5] Python...
where python >nul 2>&1
if errorlevel 1 (
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    echo.
    echo   Python was just installed. CLOSE this window and run OPTIMUS again
    echo   so Windows can see Python.
    pause & exit /b 0
)

echo [3/5] Getting the latest code from GitHub...
if exist "%REPO%\.git" (
    git -C "%REPO%" fetch origin & git -C "%REPO%" checkout %BRANCH% & git -C "%REPO%" pull origin %BRANCH%
) else (
    git clone --branch %BRANCH% %URL% "%REPO%" || (echo If a GitHub login popped up, sign in and run OPTIMUS again. & pause & exit /b 1)
)

echo [4/5] Packages + browser...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install --upgrade -r "%OPT%\install\requirements.txt"
python -m playwright install chromium

echo [5/5] Google key (so leads write to your sheet)...
python -c "import os,urllib.request,json; p=os.path.join(os.path.expanduser('~'),'optimus','google_creds.json'); urllib.request.urlretrieve('https://drive.google.com/uc?export=download&id=%CREDS_ID%', p); d=json.load(open(p)); assert d.get('project_id')=='fiberscanner-493900'; print('   key OK ->', p)" 2>nul || echo    (key not auto-downloaded -- the hunter will use any good copy already here.)

REM Hand off to the always-updating run logic in the repo. Behavior changes land
REM here automatically via the git pull above -- this on-switch never goes stale.
call "%OPT%\install\go.bat"
