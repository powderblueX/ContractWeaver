@echo off
REM Stop project processes and remove reproducible dependencies/builds, not user data.
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-project.ps1" -RemoveEnvironment
set "taskExit=%ERRORLEVEL%"
if not "%taskExit%"=="0" pause
exit /b %taskExit%
