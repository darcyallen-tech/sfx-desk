@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
title SFX Desk - setup Woosh DFlow
echo.
echo Installs the Sony woosh Python package into .venv (optional engine).
echo Core SA3 setup must already be done (scripts\setup_windows.bat).
echo.

if not exist .venv\Scripts\activate.bat (
  echo ERROR: .venv missing. Run scripts\setup_windows.bat first.
if not defined SFX_DESK_NONINTERACTIVE pause
  exit /b 1
)
call .venv\Scripts\activate.bat

echo Installing woosh deps...
pip install -r requirements-woosh.txt
if errorlevel 1 goto :fail

echo Installing woosh package from SonyResearch/Woosh@v1.0.0 ...
pip install --no-deps "woosh @ git+https://github.com/SonyResearch/Woosh.git@v1.0.0"
if errorlevel 1 goto :fail

echo.
python -c "from woosh.model.flowmap_from_pretrained import FlowMapFromPretrained; print('woosh import OK')"
if errorlevel 1 goto :fail

echo.
echo If weights are not downloaded yet, run scripts\download_woosh_weights.bat
echo Then launch scripts\run_windows.bat and pick Woosh DFlow.
if not defined SFX_DESK_NONINTERACTIVE pause
exit /b 0

:fail
echo setup_woosh failed.
if not defined SFX_DESK_NONINTERACTIVE pause
exit /b 1
