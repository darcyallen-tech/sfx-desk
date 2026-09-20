@echo off
cd /d "%~dp0.."
if not exist .venv\Scripts\activate.bat (
  echo No .venv found. Run scripts\setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
set PYTHONPATH=%CD%
set TORCHDYNAMO_DISABLE=1
set TORCH_COMPILE_DISABLE=1
set TORCHINDUCTOR_DISABLE=1
set HF_HUB_DISABLE_PROGRESS_BARS=1
set TQDM_DISABLE=1
pythonw -m app.main
if errorlevel 1 (
  echo Launch failed - retrying with console...
  python -m app.main
  pause
)
