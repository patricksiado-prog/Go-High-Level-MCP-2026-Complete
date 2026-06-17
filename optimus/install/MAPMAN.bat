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
echo       A browser window opens -- let it work. If Google ever shows a
echo       "before you continue" page, click Accept once and it continues.
python maps_scraper.py

echo.
echo [3/3] Splitting commercial vs residential into the Google Sheet...
python commercial_split.py split --businesses businesses.csv

echo.
echo  Done. Open your sheet -- new 'Commercial Leads' and 'Residential Leads' tabs.
pause
