@echo off
title Star Citizen Voice Control - setup
rem  There is no installer because there is nothing to install: the program
rem  runs from this folder and writes nothing to Windows. All this does is
rem  put a shortcut on the desktop and start it once, so "install" means the
rem  same thing here as it does anywhere else.
cd /d "%~dp0"

echo.
echo   STAR CITIZEN VOICE CONTROL
echo   Made by Obly.  Free to use, free to pass on.
echo   ============================================
echo.

if not exist "StarCitizenVoiceControl.exe" (
  echo   Something is missing: StarCitizenVoiceControl.exe is not in this folder.
  echo.
  echo   If you ran this straight out of the zip, Windows was showing you a
  echo   preview, not the real files. Extract the whole folder somewhere
  echo   first -- your Desktop is fine -- then run this again.
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
  echo   Could not make the shortcut. No harm done -- just double-click
  echo   StarCitizenVoiceControl.exe instead.
) else (
  echo   Done. It's on your desktop.
)

echo.
echo   Starting it now. The first launch takes a few seconds while the
echo   speech recogniser loads -- after that it opens straight away.
echo.
start "" "%~dp0StarCitizenVoiceControl.exe"

timeout /t 6 >nul
exit /b 0
