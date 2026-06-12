@echo off
REM ===========================================================================
REM  OPTIMUS FIBER TOOLKIT - ONE-CLICK INSTALLER  v1.0
REM ---------------------------------------------------------------------------
REM  Installs everything the map tools need on a Windows machine (the HP):
REM    - precise_fiber_hunter.py   (clicks every dot -> exact address)
REM    - fiber_zone_scanner.py     (fiber hunter / zone scanner)
REM    - optimus_dot_detect.py     (dot extractor - shared detector)
REM    - fiber_precise_pipeline.py (MapMan capture path / API capture)
REM    - business_score.py + ghl_loader.py (score -> GHL -> dialer queue)
REM  plus Git, Python, all Python packages, and Playwright's Chromium.
REM
REM  Safe to re-run any time - it updates instead of reinstalling.
REM  The GitHub updater is update_optimus.bat (created next to the repo).
REM ===========================================================================
setlocal
set "OPTIMUS_HOME=%USERPROFILE%\Optimus"
set "REPO_DIR=%OPTIMUS_HOME%\repo"
set "REPO_URL=https://github.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete.git"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"

echo.
echo  ============================================
echo   OPTIMUS FIBER TOOLKIT INSTALLER
echo  ============================================
echo.
if not exist "%OPTIMUS_HOME%" mkdir "%OPTIMUS_HOME%"

echo [1/6] Checking Git...
where git >nul 2>&1
if errorlevel 1 (
    echo        Git not found - installing via winget...
    winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo  ERROR: couldn't install Git automatically.
        echo  Install it from https://git-scm.com/download/win then re-run this.
        pause & exit /b 1
    )
    set "PATH=%PATH%;%ProgramFiles%\Git\cmd"
)

echo [2/6] Checking Python...
where python >nul 2>&1
if errorlevel 1 (
    echo        Python not found - installing 3.12 via winget...
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo  ERROR: couldn't install Python automatically.
        echo  Install it from https://www.python.org/downloads/ (check "Add to PATH"^) then re-run.
        pause & exit /b 1
    )
    echo        Close this window and RE-RUN the installer so the new
    echo        Python is on PATH.
    pause & exit /b 0
)

echo [3/6] Getting the latest code from GitHub...
if exist "%REPO_DIR%\.git" (
    git -C "%REPO_DIR%" fetch origin
    git -C "%REPO_DIR%" checkout %BRANCH%
    git -C "%REPO_DIR%" pull origin %BRANCH%
) else (
    git clone --branch %BRANCH% %REPO_URL% "%REPO_DIR%"
    if errorlevel 1 (
        echo  NOTE: if a login window opened, sign in to GitHub and re-run.
        pause & exit /b 1
    )
)

echo [4/6] Python packages (this also pulls any Python package updates)...
python -m pip install --upgrade pip
python -m pip install --upgrade -r "%REPO_DIR%\optimus\install\requirements.txt"

echo [5/6] Chromium browser for Playwright...
python -m playwright install chromium

echo [6/6] Creating the updater + checking the setup...
copy /Y "%REPO_DIR%\optimus\install\update_optimus.bat" "%OPTIMUS_HOME%\update_optimus.bat" >nul
python "%REPO_DIR%\optimus\install\check_setup.py"

echo.
echo  ============================================
echo   INSTALL COMPLETE
echo  ============================================
echo   Tools folder:   %REPO_DIR%\optimus
echo   To update:      double-click %OPTIMUS_HOME%\update_optimus.bat
echo.
echo   IMPORTANT - Google Sheets token:
echo   put your service-account file at
echo       %OPTIMUS_HOME%\google_creds.json
echo   (the checker above says if it's already in place)
echo.
echo   First runs:
echo       cd %REPO_DIR%\optimus
echo       python precise_fiber_hunter.py --login
echo       python precise_fiber_hunter.py --zip 77027 --dry
echo.
pause
