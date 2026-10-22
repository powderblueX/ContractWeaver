@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-project.ps1" -RemoveEnvironment
set "taskExit=%ERRORLEVEL%"
if not "%taskExit%"=="0" pause
exit /b %taskExit%
