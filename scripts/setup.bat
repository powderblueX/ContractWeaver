@echo off
REM Initialize dependencies and missing configuration; preserve existing secrets.
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set "taskExit=%ERRORLEVEL%"
if not "%taskExit%"=="0" pause
exit /b %taskExit%
