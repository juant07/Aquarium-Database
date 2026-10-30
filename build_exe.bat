@echo off
setlocal
cd /d "%~dp0"

set PYCMD=python
where py >nul 2>&1 && set PYCMD=py -3

echo Python controleren...
%PYCMD% -c "import sys; v=sys.version_info; sys.exit(0 if v >= (3, 8) and v < (3, 13) else 1)" >nul 2>&1
if errorlevel 1 (
  echo Deze Python is niet geschikt. Nodig: Python 3.8 t/m 3.12
  echo (3.13+ mist de module cgi waarmee de app werkt)
  echo Kies een andere versie op https://www.python.org/downloads/ en draai dit script opnieuw.
  pause
  exit /b 1
)

echo 1) PyInstaller installeren
%PYCMD% -m pip install --upgrade pyinstaller
if errorlevel 1 (
  echo pip mislukt.
  pause
  exit /b 1
)

echo 2) Aquarium.exe bouwen
%PYCMD% -m PyInstaller --onefile --name Aquarium --clean plants.py
if errorlevel 1 (
  echo build mislukt.
  pause
  exit /b 1
)

copy /y icon.png dist\ >nul 2>&1
copy /y manifest.json dist\ >nul 2>&1

echo.
echo KLAAR: dist\Aquarium.exe
echo.
echo Delen met clubleden:  zip de map dist\  - meteen verstuurd via mail/WhatsApp/Dropbox.
echo Bij het lid: uitpakken, dubbelklik Aquarium.exe. Geen Python nodig.
echo   - data staat naast de exe: plants.db, photos\
echo   - meldingen: zet notify.json ernaast. Zonder bestand werkt alles, zonder meldingen.
echo     ntfy: gratis, geen account - topic kiezen, ntfy-app op de gsm installeren, abonneren.
echo     HA: eigen long-lived token - NOOIT meegeven aan leden (volledige toegang tot je HA).
echo   - poort 8377: Windows vraagt mogelijk om een firewall-toestemming, toestaan
echo   - melding van Windows Defender over een onbekende exe is normaal bij PyInstaller,
echo     rechtsklikken - eigenschappen - "Unblock" of de exe laten analyseren.
pause
