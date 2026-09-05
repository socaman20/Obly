@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Star Citizen Voice Control - setup
cd /d "%~dp0"

rem  A REAL INSTALL, WITHOUT AN ADMIN PROMPT
rem  --------------------------------------
rem  Copies the program to one predictable place on C:, makes shortcuts, and
rem  registers itself so it shows up in Windows' own "Apps & features" list
rem  with a working Uninstall button -- the same as any other program.
rem
rem  It goes under AppData\Local\Programs rather than Program Files because
rem  writing to Program Files needs an administrator, and a free tool that
rem  demands elevation is a free tool people do not run. Visual Studio Code,
rem  Discord and Slack all install per-user for exactly this reason.

set "APPNAME=Star Citizen Voice Control"
set "TARGET=%LOCALAPPDATA%\Programs\%APPNAME%"
set "EXE=StarCitizenVoiceControl.exe"

echo.
echo   STAR CITIZEN VOICE CONTROL
echo   Made by Obly.  Free to use, free to pass on.
echo   ==============================================
echo.

if not exist "%EXE%" (
  echo   The program is not in this folder.
  echo.
  echo   1. You ran this from INSIDE the zip. Windows shows the inside of a
  echo      zip as if it were a folder, but the files are not on your disk
  echo      yet. Right-click the zip, choose "Extract All", then run this
  echo      again from the extracted folder.
  echo.
  echo   2. Your antivirus removed it. This program is not code-signed and it
  echo      types on your keyboard for you, which is exactly what antivirus
  echo      software watches for. Check your quarantine and allow the folder.
  echo.
  pause
  exit /b 1
)

rem ---------------------------------------------------------------- WebView2
set "WV2="
for %%K in (
  "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
  "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
  "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
) do reg query %%K /v pv >nul 2>&1 && set "WV2=yes"

if not defined WV2 (
  echo   One thing is missing: Microsoft's WebView2 runtime, which draws this
  echo   program's window. Windows 11 has it; Windows 10 often does not. The
  echo   installer is in this folder, so this takes about a minute.
  echo.
  if exist "MicrosoftEdgeWebview2Setup.exe" (
    echo   Installing it...
    start /wait "" "MicrosoftEdgeWebview2Setup.exe" /silent /install
  ) else (
    echo   Downloading it from Microsoft...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "try { Invoke-WebRequest 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile \"$env:TEMP\wv2.exe\" -UseBasicParsing; Start-Process -Wait \"$env:TEMP\wv2.exe\" -ArgumentList '/silent','/install'; exit 0 } catch { exit 1 }"
  )
  echo   Done.
  echo.
)

rem ------------------------------------------------------------------ install
echo   Installing to:
echo     %TARGET%
echo.

rem  Not into the folder we are running from, if that is already the target.
if /I "%~dp0"=="%TARGET%\" (
  echo   Already installed here -- just starting it.
  goto :launch
)

if exist "%TARGET%\%EXE%" (
  echo   An older copy is there. Replacing it...
  taskkill /IM "%EXE%" /F >nul 2>&1
  timeout /t 2 >nul
)

if not exist "%TARGET%" mkdir "%TARGET%" 2>nul
if not exist "%TARGET%" (
  echo   Could not create that folder. Running from here instead.
  set "TARGET=%~dp0"
  goto :shortcuts
)

rem  /E every folder, /PURGE removes files an old version left behind, /NJH
rem  /NJS /NDL /NC /NS keeps the output to one readable line.
robocopy "%~dp0." "%TARGET%" /E /PURGE /NFL /NDL /NJH /NJS /NC /NS /NP >nul
if errorlevel 8 (
  echo   The copy failed. Running from this folder instead.
  set "TARGET=%~dp0"
) else (
  echo   Copied.
)

:shortcuts
echo   Making shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$w=New-Object -ComObject WScript.Shell;" ^
  "foreach($p in @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'))){" ^
  "  $s=$w.CreateShortcut((Join-Path $p '%APPNAME%.lnk'));" ^
  "  $s.TargetPath=(Join-Path '%TARGET%' '%EXE%');" ^
  "  $s.WorkingDirectory='%TARGET%';" ^
  "  $s.IconLocation=(Join-Path '%TARGET%' '%EXE%')+',0';" ^
  "  $s.Description='Voice control for Star Citizen - by Obly';" ^
  "  $s.Save() }"

rem  Register in Apps & features, so Windows itself offers to remove it and
rem  nobody has to remember where it went.
set "UNKEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\StarCitizenVoiceControl"
reg add "%UNKEY%" /v DisplayName     /t REG_SZ /d "%APPNAME%" /f >nul 2>&1
reg add "%UNKEY%" /v DisplayVersion  /t REG_SZ /d "4.4.0" /f >nul 2>&1
reg add "%UNKEY%" /v Publisher       /t REG_SZ /d "Obly" /f >nul 2>&1
reg add "%UNKEY%" /v InstallLocation /t REG_SZ /d "%TARGET%" /f >nul 2>&1
reg add "%UNKEY%" /v DisplayIcon     /t REG_SZ /d "%TARGET%\%EXE%" /f >nul 2>&1
reg add "%UNKEY%" /v UninstallString /t REG_SZ /d "\"%TARGET%\Uninstall.bat\"" /f >nul 2>&1
reg add "%UNKEY%" /v NoModify        /t REG_DWORD /d 1 /f >nul 2>&1
reg add "%UNKEY%" /v NoRepair        /t REG_DWORD /d 1 /f >nul 2>&1

echo   Done. It is on your desktop, in your Start menu, and in
echo   Settings - Apps if you ever want to remove it.
echo.

:launch
echo   Checking this copy...
"%TARGET%\%EXE%" --selftest >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Something is not right. Open  selftest-result.txt  in
  echo     %TARGET%
  echo   and send it to Obly -- it names exactly what is missing.
  echo.
  choice /C YN /N /M "   Start it anyway? [Y/N] "
  if errorlevel 2 exit /b 1
) else (
  echo   Everything checks out.
)

echo.
echo   Starting it. The first launch takes a few seconds while the speech
echo   recogniser loads. Windows may say "Windows protected your PC" -- that
echo   appears for every unsigned program. More info, then Run anyway.
echo.
start "" "%TARGET%\%EXE%"
timeout /t 8 >nul
endlocal
exit /b 0
