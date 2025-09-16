@echo off
setlocal
cd /d "%~dp0"

set PY=.\.venv\Scripts\python.exe

if not exist ".venv\Scripts\python.exe" (
  echo Virtuelle Umgebung nicht gefunden. Bitte zuerst .venv erstellen/aktivieren.
  pause
  exit /b 1
)

echo [1/3] Scrape Monitor...
%PY% untis_monitor_scrape.py || goto :err

echo [2/3] Normalisiere...
%PY% untis_normalize.py || goto :err

echo [3/3] Filtere Klasse 8c...
%PY% untis_filter.py -c 8c || goto :err

echo.
echo Fertig. Dateien erstellt:
echo   - untis_subst_normalized.csv / .json
echo   - untis_subst_8c.csv / .json
pause
exit /b 0

:err
echo.
echo FEHLER. Bitte Meldung oben prüfen.
pause
exit /b 1
