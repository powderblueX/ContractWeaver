@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-frontend.ps1" %*
set "taskExit=%ERRORLEVEL%"
exit /b %taskExit%
