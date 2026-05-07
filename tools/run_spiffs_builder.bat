@echo off
setlocal
set ROOT=%~dp0
if exist "%ROOT%..\.venv\Scripts\python.exe" (
  "%ROOT%..\.venv\Scripts\python.exe" "%ROOT%spiffs_builder_gui.py"
  goto :eof
)
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py "%ROOT%spiffs_builder_gui.py"
  goto :eof
)
python "%ROOT%spiffs_builder_gui.py"
