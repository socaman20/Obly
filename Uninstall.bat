@echo off
setlocal EnableExtensions
title Star Citizen Voice Control - uninstall

rem  What Windows runs when someone clicks Uninstall in Apps & features, and
rem  what a person can double-click directly. It removes the program, both
rem  shortcuts and the registry entry -- and asks, separately, whether to keep
rem  the commands they wrote. Deleting somebody's own work without asking is
rem  not tidiness, it is data loss.

set "APPNAME=Star Citizen Voice Control"
set "TARGET=%~dp0"
set "MINE=%LOCALAPPDATA%\%APPNAME%"
set "EXE=StarCitizenVoiceControl.exe"

echo.
echo   UNINSTALL - %APPNAME%
echo   ================================================
echo.
echo   This will remove:
echo     the program at  %TARGET%
echo     the desktop shortcut
echo     the Start menu entry
echo     its entry in Apps ^& features
echo.

choice /C YN /N /M "   Go ahead? [Y/N] "
if errorlevel 2 (
  echo   Nothing was changed.
  timeout /t 3 >nul
  exit /b 0
)

echo.
echo   Closing it if it is running...
taskkill /IM "%EXE%" /F >nul 2>&1
timeout /t 2 >nul

echo   Removing shortcuts...
del "%USERPROFILE%\Desktop\%APPNAME%.lnk" >nul 2>&1
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\%APPNAME%.lnk" >nul 2>&1

echo   Removing it from Apps ^& features...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\StarCitizenVoiceControl" /f >nul 2>&1

rem ------------------------------------------------------ their own files
if exist "%MINE%" (
  echo.
  echo   Your own files are kept separately, and they are still there:
  echo     %MINE%
  echo.
  echo     my_commands.json   commands you wrote
  echo     my_routes.json     destinations you plotted
  echo.
  choice /C YN /N /M "   Delete those as well? [Y/N] "
  if errorlevel 2 (
    echo   Keeping them. Reinstalling later will pick them up again.
  ) else (
    rd /s /q "%MINE%" >nul 2>&1
    echo   Deleted.
  )
)

rem  A batch file cannot delete the folder it is running from, so hand that
rem  last step to a second process that starts after this one has exited.
echo.
echo   Removing the program...
start "" /min cmd /c "timeout /t 3 >nul & rd /s /q ""%TARGET%"" & exit"

echo.
echo   Done. Thanks for trying it.
echo.
timeout /t 4 >nul
endlocal
exit /b 0
