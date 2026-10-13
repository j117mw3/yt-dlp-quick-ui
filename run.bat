@echo off
setlocal
set "APP_DIR=%~dp0"
set "PYTHON_EXE="

if exist "%APP_DIR%.venv\Scripts\python.exe" set "PYTHON_EXE=%APP_DIR%.venv\Scripts\python.exe"
if defined PYTHON_EXE goto preflight

where py.exe >nul 2>nul
if not errorlevel 1 goto resolve_py

where python.exe >nul 2>nul
if not errorlevel 1 goto resolve_python

echo Python 3 is required to run this source copy.
echo Install Python 3.10 or newer with Tcl/Tk, then run this file again.
echo You can also use the portable ZIP or setup EXE from the GitHub Releases page.
pause
exit /b 1

:resolve_py
for /f "delims=" %%P in ('py.exe -3 -c "import sys; print(sys.executable)" 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if defined PYTHON_EXE goto preflight
echo The Python launcher could not find Python 3.
echo Install Python 3.10 or newer with Tcl/Tk, then run this file again.
pause
exit /b 1

:resolve_python
for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if defined PYTHON_EXE goto preflight
echo Python 3 was not found.
echo Install Python 3.10 or newer with Tcl/Tk, then run this file again.
pause
exit /b 1

:preflight
"%PYTHON_EXE%" -c "import tkinter" >nul 2>nul
if errorlevel 1 (
  echo This Python installation does not include Tcl/Tk.
  echo Reinstall Python 3.10 or newer with Tcl/Tk enabled.
  pause
  exit /b 1
)

for %%P in ("%PYTHON_EXE%") do set "PYTHONW_EXE=%%~dpPpythonw.exe"
if not exist "%PYTHONW_EXE%" set "PYTHONW_EXE=%PYTHON_EXE%"
start "" /D "%APP_DIR%" "%PYTHONW_EXE%" "%APP_DIR%yt_dlp_quick_ui.py"
exit /b 0

