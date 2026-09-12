@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0source\packaging\Repair-CodexRuntime.ps1" -Repair
echo.
pause
