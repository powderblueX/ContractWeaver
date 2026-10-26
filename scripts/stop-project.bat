@echo off
REM Stop project-owned processes and transient caches; preserve configuration and contracts.
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-project.ps1" %*
set "taskExit=%ERRORLEVEL%"
if not "%taskExit%"=="0" pause
exit /b %taskExit%
