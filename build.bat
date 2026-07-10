@echo off
rem A.T.L.A.S. build — thin wrapper around build.py (icon -> exe -> installer).
rem Requires Python 3.11+ and (for the installer step) Inno Setup 6 on PATH.
setlocal
cd /d "%~dp0"
if not exist .venv ( python -m venv .venv || goto :fail )
call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip || goto :fail
python -m pip install --quiet -r requirements.txt pyinstaller || goto :fail
python build.py %* || goto :fail
echo.
echo Done. Installer + checksums are in dist\release\.
exit /b 0
:fail
echo BUILD FAILED — see output above.
exit /b 1
