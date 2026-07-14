@echo off
setlocal

set "LAUNCH_SCRIPT=%~dp0launch.ps1"
where pwsh.exe >nul 2>&1
if not errorlevel 1 (
    pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%LAUNCH_SCRIPT%" %*
    exit /b %ERRORLEVEL%
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%LAUNCH_SCRIPT%" %*
exit /b %ERRORLEVEL%
