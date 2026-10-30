@echo off
setlocal
cd /d "%~dp0"

set PYCMD=python
where py >nul 2>&1 && set PYCMD=py -3

echo Python controleren... / Checking Python...
%PYCMD% -c "import sys; v=sys.version_info; sys.exit(0 if v >= (3, 8) and v < (3, 13) else 1)" >nul 2>&1
if errorlevel 1 (
  echo Deze Python is niet geschikt. Nodig: Python 3.8 t/m 3.12
  echo This Python is not suitable. Needed: Python 3.8 up to 3.12
  echo (3.13+ mist de module cgi waarmee de app werkt / 3.13+ lacks the cgi module the app uses)
  echo Kies een andere versie op https://www.python.org/downloads/ en draai dit script opnieuw.
  echo Pick another version at https://www.python.org/downloads/ and run this script again.
  pause
  exit /b 1
)

echo 1) PyInstaller installeren / installing
%PYCMD% -m pip install --upgrade pyinstaller
if errorlevel 1 (
  echo pip mislukt. / pip failed.
  pause
  exit /b 1
)

echo 2) Aquarium.exe bouwen / building
%PYCMD% -m PyInstaller --onefile --name Aquarium --clean plants.py
if errorlevel 1 (
  echo build mislukt. / build failed.
  pause
  exit /b 1
)

copy /y icon.png dist\ >nul 2>&1
copy /y manifest.json dist\ >nul 2>&1

echo.
echo KLAAR: dist\Aquarium.exe  /  DONE: dist\Aquarium.exe
echo.
echo Delen met clubleden / sharing with club members: zip de map dist\ (zip the dist\ folder)
echo Bij het lid / at the member: uitpakken, dubbelklik Aquarium.exe. Geen Python nodig.
echo                                                     unzip, double-click Aquarium.exe. No Python needed.
echo   - data staat naast de exe / data sits next to the exe: plants.db, photos\
echo   - meldingen / notifications: zet notify.json ernaast. Zonder bestand werkt alles, zonder meldingen.
echo                                 put notify.json next to it. Without the file all works, just no notifications.
echo     ntfy: gratis / free, geen account / no account - topic kiezen, ntfy-app installeren, abonneren.
echo     HA: eigen long-lived token - NOOIT meegeven aan leden / NEVER give it to members (full HA access).
echo   - poort 8377 / port 8377: Windows vraagt mogelijk om firewall-toestemming / may ask for firewall permission, allow it
echo   - Defender-melding over een onbekende exe is normaal / a Defender warning about an unknown exe is normal,
echo     rechtsklikken - eigenschappen - "Unblock" / right-click - properties - "Unblock", or let Defender scan it.
pause
