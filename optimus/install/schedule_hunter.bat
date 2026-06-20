@echo off
REM ===========================================================================
REM  SCHEDULE HUNTER - make the scan run automatically on a schedule.
REM  Double-click ONCE. It registers a Windows Task that runs run_hunter.bat
REM  every day at 2:00 AM (edit the time below). Remove it anytime with:
REM       schtasks /delete /tn OptimusHunter /f
REM ===========================================================================
setlocal
set "RUNNER=%USERPROFILE%\optimus\repo\optimus\install\run_hunter.bat"
set "WHEN=02:00"

if not exist "%RUNNER%" (
    echo run_hunter.bat not found at %RUNNER% - pull the latest code first.
    pause & exit /b 1
)

schtasks /create /tn OptimusHunter /tr "\"%RUNNER%\"" /sc daily /st %WHEN% /f
if errorlevel 1 (
    echo Could not create the task. Try running this file as Administrator.
    pause & exit /b 1
)
echo.
echo Scheduled: OptimusHunter runs daily at %WHEN%.
echo   See it:    schtasks /query /tn OptimusHunter
echo   Run now:   schtasks /run /tn OptimusHunter
echo   Remove:    schtasks /delete /tn OptimusHunter /f
echo.
pause
