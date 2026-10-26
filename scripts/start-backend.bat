@echo off
REM Start only the local backend; keep this launcher attached for scoped shutdown.
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-backend.ps1" %*
set "taskExit=%ERRORLEVEL%"
exit /b %taskExit%
