@echo off
title Star Citizen Voice Control - setup
rem  Named "START HERE" rather than "INSTALL" because Windows hides file
rem  extensions by default: a tester extracted the zip, went looking for a
rem  ".exe", and could not find one -- because Windows was showing the program
rem  as "StarCitizenVoiceControl" with no extension at all. A file called
rem  START HERE needs no extension to be understood.
cd /d "%~dp0"

echo.
echo   STAR CITIZEN VOICE CONTROL
echo   Made by Obly.  Free to use, free to pass on.
echo   ============================================
echo.

if not exist "StarCitizenVoiceControl.exe" (
  echo   The program is not in this folder.
  echo.
  echo   Two things do this, and they need different fixes:
  echo.
  echo   1. You ran this from INSIDE the zip. Windows shows you a preview of
  echo      a zip that looks like a folder, but the files are not really
  echo      there yet. Right-click the zip, choose "Extract All", and run
  echo      this again from the extracted folder.
  echo.
  echo   2. Your antivirus removed it. This program is not signed -- signing
  echo      costs a few hundred a year and this is free -- and it types on
  echo      your keyboard for you, which is exactly what antivirus software
  echo      is built to be suspicious of. If it was quarantined, restore it
  echo      and allow the folder.
  echo.
  pause
  exit /b 1
)

echo   Making a desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Star Citizen Voice Control.lnk');" ^
  "$s.TargetPath='%~dp0StarCitizenVoiceControl.exe';" ^
  "$s.WorkingDirectory='%~dp0';" ^
  "$s.IconLocation='%~dp0StarCitizenVoiceControl.exe,0';" ^
  "$s.Description='Voice control for Star Citizen - by Obly';" ^
  "$s.Save()"

if errorlevel 1 (
  echo   Could not make the shortcut. No harm done -- open the program
  echo   directly instead: it is the file called StarCitizenVoiceControl.
) else (
  echo   Done. It is on your desktop.
)

echo.
echo   Starting it now. The first launch takes a few seconds while the
echo   speech recogniser loads. Windows may say "Windows protected your PC"
echo   the first time -- that notice appears for every unsigned program,
echo   not because anything is wrong. Click "More info", then "Run anyway".
echo.
start "" "%~dp0StarCitizenVoiceControl.exe"

timeout /t 8 >nul
exit /b 0
