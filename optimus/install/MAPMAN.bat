@echo off
REM ===========================================================================
REM  MAPMAN.bat -- commercial vs residential split + business phones.
REM  Asks for ZIPs, builds the search list, runs the open-source Google Maps
REM  scraper, then splits your captured fiber leads into the sheet:
REM    Commercial Leads (name + phone)  |  Residential Leads (door-knock).
REM  One-time: download the scraper exe (link shown below if it's missing).
REM ===========================================================================
setlocal EnableDelayedExpansion
set "OPT=%USERPROFILE%\optimus\repo\optimus"
cd /d "%OPT%" || (echo Could not find %OPT% - run OPTIMUS once first. & pause & exit /b 1)

echo.
echo  ============================================================
echo    MAPMAN  --  commercial vs residential + business phones
echo  ============================================================
echo.
set /p ZIPS="Enter ZIP codes to scan (comma-separated, e.g. 77027,77019): "
if "%ZIPS%"=="" (echo No ZIPs entered. & pause & exit /b 1)

echo.
echo [1/3] Building the business search list...
python commercial_split.py make-queries --zips %ZIPS% || (pause & exit /b 1)

REM locate the scraper exe: this folder, the optimus home, or PATH
set "SCRAPER="
if exist "%OPT%\google-maps-scraper.exe" set "SCRAPER=%OPT%\google-maps-scraper.exe"
if not defined SCRAPER if exist "%USERPROFILE%\optimus\google-maps-scraper.exe" set "SCRAPER=%USERPROFILE%\optimus\google-maps-scraper.exe"
if not defined SCRAPER ( where google-maps-scraper.exe >nul 2>&1 && set "SCRAPER=google-maps-scraper.exe" )
if not defined SCRAPER (
    echo.
    echo   *** One-time setup: the Google Maps scraper isn't installed yet. ***
    echo   1^) Open https://github.com/gosom/google-maps-scraper/releases/latest
    echo   2^) Download the Windows zip, unzip it
    echo   3^) Put  google-maps-scraper.exe  in this folder:
    echo        %OPT%
    echo   Then run MAPMAN again.
    echo.
    pause & exit /b 1
)

echo.
echo [2/3] Scraping businesses with %SCRAPER% (this is the slow part)...
"%SCRAPER%" -input queries.txt -results businesses.csv -depth 1

echo.
echo [3/3] Splitting commercial vs residential into the Google Sheet...
python commercial_split.py split --businesses businesses.csv

echo.
echo  Done. Open your sheet -- new 'Commercial Leads' and 'Residential Leads' tabs.
pause
