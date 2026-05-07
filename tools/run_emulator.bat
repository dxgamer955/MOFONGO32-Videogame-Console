@echo off
setlocal
set SCRIPT=%~dp0mofongo_emulator.py

REM Prefer the Windows Python launcher if available.
where py >nul 2>nul
if %errorlevel%==0 (
  py -3.14 "%SCRIPT%"
  if %errorlevel%==0 exit /b 0
  py -3 "%SCRIPT%"
  if %errorlevel%==0 exit /b 0
)

REM Fallback to python on PATH.
where python >nul 2>nul
if %errorlevel%==0 (
  python "%SCRIPT%"
  exit /b 0
)

echo Python not found. Install Python 3.10+ or use the Python launcher.
pause
