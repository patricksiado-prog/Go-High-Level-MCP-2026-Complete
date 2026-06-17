@echo off
REM ===========================================================================
REM  GOOGLE MAPS BUSINESS SCRAPER -- git-based launcher.
REM  Double-click it. First time: installs Git + Python + the browser engine and
REM  clones the code from GitHub. EVERY run after that it CHECKS GITHUB for the
REM  latest scraper (git fetch + reset) before running -- so updates are always
REM  live, automatically. Needs access to the GitHub repo (be a collaborator).
REM ===========================================================================
title Google Maps Business Scraper
setlocal EnableDelayedExpansion
set "HOME_DIR=%USERPROFILE%\maps_scraper"
set "REPO=%HOME_DIR%\repo"
set "OPT=%REPO%\optimus"
set "PY=%OPT%\standalone\maps_scraper_standalone.py"
set "URL=https://github.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete.git"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "CREDS=%HOME_DIR%\google_creds.json"
set "CREDSID=1upYH4h2VsmOwO82v9CVjMpE6IzV-5dIs"
if not exist "%HOME_DIR%" mkdir "%HOME_DIR%"

echo.
echo  ============================================================
echo     GOOGLE MAPS BUSINESS SCRAPER
echo  ============================================================
echo.

echo [1/4] Git...
where git >nul 2>&1 || (
    winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
    set "PATH=%PATH%;%ProgramFiles%\Git\cmd"
)

echo [2/4] Python...
where python >nul 2>&1
if errorlevel 1 (
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    echo.
    echo    Python was just installed. CLOSE this window and run this file
    echo    ONE more time so Windows can see Python.
    pause & exit /b 0
)

echo [3/4] Checking GitHub for the latest scraper...
if exist "%REPO%\.git" (
    git -C "%REPO%" fetch origin %BRANCH%
    git -C "%REPO%" reset --hard origin/%BRANCH%
) else (
    git clone --branch %BRANCH% %URL% "%REPO%" || (echo If a GitHub login popped up, sign in and run this file again. & pause & exit /b 1)
)

echo [4/4] Packages + browser + key...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install --upgrade playwright gspread google-auth
python -m playwright install chromium
python -c "import urllib.request; urllib.request.urlretrieve('https://drive.google.com/uc?export=download^&id=%CREDSID%', r'%CREDS%')" 2>nul || echo    (key not downloaded -- CSV output still works fine.)

echo.
echo  Starting the scraper. A browser opens -- enter your ZIPs when asked.
echo.
python "%PY%"
echo.
echo  Finished. Your CSV is in:  %HOME_DIR%\repo\optimus\standalone\businesses.csv
pause
