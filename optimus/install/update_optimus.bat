@echo off
REM ===========================================================================
REM  OPTIMUS GITHUB UPDATER - pulls the latest tools + Python package updates.
REM  Double-click any time. Safe: your google_creds.json, att_profile login,
REM  and captured data are outside the repo and never touched.
REM ===========================================================================
setlocal
set "OPTIMUS_HOME=%USERPROFILE%\Optimus"
set "REPO_DIR=%OPTIMUS_HOME%\repo"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"

echo.
echo  ==== OPTIMUS UPDATER ====
if not exist "%REPO_DIR%\.git" (
    echo  Repo not found at %REPO_DIR% - run install_optimus.bat first.
    pause & exit /b 1
)

echo [1/3] Pulling latest code from GitHub...
git -C "%REPO_DIR%" fetch origin
git -C "%REPO_DIR%" checkout %BRANCH%
git -C "%REPO_DIR%" pull origin %BRANCH%

echo [2/3] Updating Python packages...
python -m pip install --upgrade -r "%REPO_DIR%\optimus\install\requirements.txt" --quiet
python -m playwright install chromium >nul 2>&1

echo [3/3] Setup check...
python "%REPO_DIR%\optimus\install\check_setup.py"

echo.
echo  Up to date.
pause
