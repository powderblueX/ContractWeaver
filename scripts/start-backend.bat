@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-backend.ps1" %*
set "taskExit=%ERRORLEVEL%"
exit /b %taskExit%
