@echo off
REM ===========================================================================
REM  OPTIMUS - SET UP A NEW COMPUTER  (one double-click)
REM ---------------------------------------------------------------------------
REM  Installs the whole fiber toolkit on a fresh Windows PC:
REM    - MapMan            (fiber_precise_pipeline.py  - backend capture)
REM    - Fiber Hunter      (fiber_zone_scanner.py      - fast new-zone sweep)
REM    - Dot Extractor     (optimus_dot_detect.py      - shared dot detector)
REM    - Precise Hunter    (precise_fiber_hunter.py    - exact addresses + --net)
REM    - enrich_phones / business_score / ghl_loader
REM  ...plus Git, Python, all packages, Playwright Chromium, and the Google
REM  creds file. Safe to re-run (it just updates).
REM ===========================================================================
setlocal EnableDelayedExpansion
set "HOME=%USERPROFILE%\optimus"
set "REPO=%HOME%\repo"
set "URL=https://github.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete.git"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "CREDS_ID=1upYH4h2VsmOwO82v9CVjMpE6IzV-5dIs"

echo.
echo  =====================================================
echo    OPTIMUS FIBER TOOLKIT - NEW COMPUTER SETUP
echo  =====================================================
echo.
if not exist "%HOME%" mkdir "%HOME%"

echo [1/7] Git...
where git >nul 2>&1 || (
    winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
    set "PATH=%PATH%;%ProgramFiles%\Git\cmd"
)

echo [2/7] Python...
where python >nul 2>&1
if errorlevel 1 (
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    echo.
    echo   Python was just installed. CLOSE this window and double-click this
    echo   file again so Windows picks up Python.
    pause & exit /b 0
)

echo [3/7] Getting the code...
if exist "%REPO%\.git" (
    git -C "%REPO%" fetch origin & git -C "%REPO%" checkout %BRANCH% & git -C "%REPO%" pull origin %BRANCH%
) else (
    git clone --branch %BRANCH% %URL% "%REPO%" || (echo If a GitHub login popped up, sign in and re-run. & pause & exit /b 1)
)

echo [4/7] Python packages...
python -m pip install --upgrade pip
python -m pip install --upgrade -r "%REPO%\optimus\install\requirements.txt"

echo [5/7] Chromium browser...
python -m playwright install chromium

echo [6/7] Google creds (downloads the file, no typing)...
python -c "import os,urllib.request; p=os.path.join(os.path.expanduser('~'),'optimus','google_creds.json'); urllib.request.urlretrieve('https://drive.google.com/uc?export=download&id=%CREDS_ID%', p); print('  creds ->', p)" || echo   (creds download skipped - tools still run, sheet writes off until added)

echo [7/7] Launchers + check...
copy /Y "%REPO%\optimus\install\update_optimus.bat" "%HOME%\update_optimus.bat" >nul 2>&1
copy /Y "%REPO%\optimus\install\run_hunter.bat" "%HOME%\run_hunter.bat" >nul 2>&1
python "%REPO%\optimus\install\check_setup.py"

echo.
echo  =====================================================
echo    DONE. Tools are in: %REPO%\optimus
echo  =====================================================
echo.
echo   FIRST TIME ONLY - log into the AT&T map once:
echo       cd /d "%REPO%\optimus"
echo       python precise_fiber_hunter.py --login
echo     (log in, get the map showing, press Enter)
echo.
echo   THEN to run hands-free anytime, just double-click:
echo       %HOME%\run_hunter.bat
echo.
echo   To update later: double-click  %HOME%\update_optimus.bat
echo.
pause
