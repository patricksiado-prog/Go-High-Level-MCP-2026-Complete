@echo off
REM ===========================================================================
REM  MAPMAN.bat -- commercial vs residential split + business phones.
REM  Asks for ZIPs, then: builds the search list -> scrapes Google Maps with the
REM  built-in Python scraper (NO download, uses the browser OPTIMUS installed) ->
REM  splits your captured fiber leads into the sheet:
REM    Commercial Leads (Category, Email, Name, Address, Phone)  |  Residential.
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

echo.
echo [2/3] Scraping Google Maps for businesses (this is the slow part)...
REM Prefer gosom (the proven MIT scraper) if the exe is here; otherwise fall back
REM to the built-in Python scraper so it still runs with no download.
set "SCRAPER="
if exist "%OPT%\google-maps-scraper.exe" set "SCRAPER=%OPT%\google-maps-scraper.exe"
if not defined SCRAPER if exist "%USERPROFILE%\optimus\google-maps-scraper.exe" set "SCRAPER=%USERPROFILE%\optimus\google-maps-scraper.exe"
if not defined SCRAPER ( where google-maps-scraper.exe >nul 2>&1 && set "SCRAPER=google-maps-scraper.exe" )
if defined SCRAPER (
    echo   Using gosom: %SCRAPER%
    REM -depth 10 = full ~120 results per search; -email crawls sites for an email.
    "%SCRAPER%" -input queries.txt -results businesses.csv -depth 10 -email -c 2
) else (
    echo   gosom not installed -- using the built-in Python scraper instead.
    echo   ^(To use gosom: put google-maps-scraper.exe in %OPT%, then run again.^)
    python maps_scraper.py
)

echo.
echo [3/3] Splitting commercial vs residential into the Google Sheet...
python commercial_split.py split --businesses businesses.csv

echo.
echo  Done. Open your sheet -- new 'Commercial Leads' and 'Residential Leads' tabs.
pause
