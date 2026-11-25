@echo off
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    echo Run Install.ps1 to set up File Converter first.
    pause
    exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launch.pyw" -- %*
