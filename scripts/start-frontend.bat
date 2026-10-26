@echo off
REM Start only the local frontend development server.
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-frontend.ps1" %*
set "taskExit=%ERRORLEVEL%"
exit /b %taskExit%
