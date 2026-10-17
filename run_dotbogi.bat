@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m dotbogi %*
) else (
  python -m dotbogi %*
)
if errorlevel 1 pause
