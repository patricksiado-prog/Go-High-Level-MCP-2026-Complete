@echo off
REM ===========================================================================
REM  START DIALER.bat  --  one permanent link. Loads the combined fiber business
REM  leads (the hunter's "Fiber Green Biz" / "Upgrade Orange Biz" tabs) into your
REM  GoHighLevel power dialer, best business first. Every run it pulls the latest
REM  code from GitHub, so it auto-updates with nothing for you to do but keep the
REM  link.
REM
REM  IT DOES NOT PLACE CALLS. It stages + orders the work in GHL; you open GHL's
REM  power dialer and a live person calls each one. (That's the TCPA-safe design.)
REM ===========================================================================
setlocal EnableDelayedExpansion
set "HOME_DIR=%USERPROFILE%\optimus"
set "REPO=%HOME_DIR%\repo"
set "OPT=%REPO%\optimus"
set "URL=https://github.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete.git"
set "BRANCH=claude/optimus-map-tools-setup-6dcl6o"
set "CREDS_ID=1upYH4h2VsmOwO82v9CVjMpE6IzV-5dIs"
REM TOKEN FROM THE BUSYBEE: callers never paste the GHL token. Fill in your Railway
REM busybee URL + the DIALER_TOKEN_KEY you set in Railway, and the dialer pulls the
REM token from there. Leave blank to fall back to a one-time prompt.
set "GHL_TOKEN_URL=https://YOUR-BUSYBEE.up.railway.app/pit-token?key=YOUR_DIALER_TOKEN_KEY"

title OPTIMUS Dialer Loader
echo.
echo  ============================================================
echo     OPTIMUS DIALER  --  leads into your GHL power dialer
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
    echo   Python was just installed. CLOSE this window and run START DIALER again
    echo   so Windows can see Python.
    pause & exit /b 0
)

echo [3/5] Getting the latest code from GitHub...
if exist "%REPO%\.git" (
    git -C "%REPO%" fetch origin & git -C "%REPO%" checkout %BRANCH% & git -C "%REPO%" pull origin %BRANCH%
) else (
    git clone --branch %BRANCH% %URL% "%REPO%" || (echo Could not reach GitHub. Check your internet. & pause & exit /b 1)
)

echo [4/5] Packages...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install --upgrade requests gspread google-auth

echo [5/5] Google key (so it can read your lead tabs)...
python -c "import os,urllib.request,json; p=os.path.join(os.path.expanduser('~'),'optimus','google_creds.json'); urllib.request.urlretrieve('https://drive.google.com/uc?export=download&id=%CREDS_ID%', p); d=json.load(open(p)); assert d.get('project_id')=='fiberscanner-493900'; print('   key OK')" 2>nul || echo    (key not auto-downloaded -- it will use any good copy already here.)

cd /d "%OPT%" || (echo Could not find %OPT% & pause & exit /b 1)
echo.
echo  Reading your green/orange business leads, scoring them, and staging the
echo  power-dialer queue. It shows a PREVIEW first and asks before loading.
echo.
REM First run will ask for your GHL token (pit-...) once and remember it.
python dialer_loader.py
echo.
echo  Done. Open GoHighLevel -^> power dialer to work the queue.
pause
