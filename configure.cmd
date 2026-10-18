@echo off
chcp 65001 >nul
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Configure %*
set "startup_exit=%errorlevel%"
if not "%startup_exit%"=="0" pause
exit /b %startup_exit%
