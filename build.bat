@echo off
rem ============================================================
rem  A.T.L.A.S. build script — produces dist\ATLAS.exe + user files
rem  Requires: Python 3.11+ on PATH. Everything else is fetched.
rem ============================================================
setlocal
cd /d "%~dp0"

echo [1/5] Creating build venv...
if not exist .venv (
    python -m venv .venv || goto :fail
)
call .venv\Scripts\activate.bat

echo [2/5] Installing dependencies...
python -m pip install --quiet --upgrade pip || goto :fail
python -m pip install --quiet -r requirements.txt pyinstaller || goto :fail

echo [3/5] Quick sanity check (imports + plugin load)...
python -c "import compileall,sys; sys.exit(0 if compileall.compile_dir('src', quiet=1) and compileall.compile_dir('plugins', quiet=1) else 1)" || goto :fail

echo [4/5] Freezing with PyInstaller...
pyinstaller --noconfirm --clean atlas.spec || goto :fail

echo [5/5] Staging user-editable files next to the exe...
xcopy /e /i /y plugins dist\plugins >nul
xcopy /e /i /y skills dist\skills >nul

for %%F in (dist\ATLAS.exe) do echo Built %%F (%%~zF bytes)
echo.
echo Done. Ship the dist\ folder, or just ATLAS.exe (it self-heals
echo settings.json, apps.json, plugins\ and skills\ on first run).
exit /b 0

:fail
echo BUILD FAILED — see output above.
exit /b 1
