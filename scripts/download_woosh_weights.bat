@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
title SFX Desk - download Woosh weights
echo.
echo Downloads Sony Woosh DFlow T2A weights (CC BY-NC 4.0) from
echo   Hugging Face: AEmotionStudio/woosh-models
echo into %%USERPROFILE%%\woosh-models\checkpoints\
echo Only: Woosh-AE + TextConditionerA + Woosh-DFlow  (~3.7 GB)
echo.

set ROOT=%USERPROFILE%\woosh-models
if not "%SFX_DESK_WOOSH_ROOT%"=="" set ROOT=%SFX_DESK_WOOSH_ROOT%

if exist .venv\Scripts\activate.bat (
  call .venv\Scripts\activate.bat
) else (
  echo WARNING: no .venv — using system Python. Prefer scripts\setup_windows.bat first.
)

where hf >nul 2>&1
if errorlevel 1 (
  python -m pip install -q "huggingface_hub[cli]>=0.24.0"
)

echo Target: %ROOT%
mkdir "%ROOT%" 2>nul

echo Pulling checkpoints (resume-safe)...
hf download AEmotionStudio/woosh-models checkpoints/Woosh-AE --local-dir "%ROOT%"
if errorlevel 1 goto :fail
hf download AEmotionStudio/woosh-models checkpoints/TextConditionerA --local-dir "%ROOT%"
if errorlevel 1 goto :fail
hf download AEmotionStudio/woosh-models checkpoints/Woosh-DFlow --local-dir "%ROOT%"
if errorlevel 1 goto :fail

echo.
echo Done. Layout:
dir /s /b "%ROOT%\checkpoints\Woosh-AE\weights.safetensors"
dir /s /b "%ROOT%\checkpoints\TextConditionerA\weights.safetensors"
dir /s /b "%ROOT%\checkpoints\Woosh-DFlow\weights.safetensors"
echo.
echo Next: scripts\setup_woosh.bat  then pick "Woosh DFlow" in SFX Desk.
if not defined SFX_DESK_NONINTERACTIVE pause
exit /b 0

:fail
echo Download failed. Check network / hf auth (public mirror usually needs no token).
if not defined SFX_DESK_NONINTERACTIVE pause
exit /b 1
