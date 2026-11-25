@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1"
set "converterExitCode=%errorlevel%"
if "%converterExitCode%"=="0" (
    echo Open File Converter from the Start menu or use Open File Converter.cmd.
)
echo.
pause
exit /b %converterExitCode%
