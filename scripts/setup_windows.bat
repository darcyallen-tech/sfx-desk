@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
title SFX Desk Setup
echo.
echo ========================================
echo   SFX Desk setup (Windows + NVIDIA)
echo ========================================
echo.
echo This installs a local Python venv, PyTorch CUDA,
echo SA3 Small-SFX, and walks you through Hugging Face login.
echo Free / open source. You bring your OWN HF account + token.
echo.

where py >nul 2>&1
if errorlevel 1 (
  where python >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Python not found.
    echo Install Python 3.12 from https://www.python.org/downloads/
    echo Check "Add python.exe to PATH", then re-run this script.
    pause
    exit /b 1
  )
  set PY=python
) else (
  set PY=py -3.12
  %PY% -c "import sys" >nul 2>&1
  if errorlevel 1 set PY=py -3
)

echo Using: %PY%
%PY% -c "import sys; assert sys.version_info[:2] >= (3, 11), sys.version"
if errorlevel 1 (
  echo ERROR: Need Python 3.11+ ^(3.12 recommended^).
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating .venv ...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo ERROR: venv failed.
    pause
    exit /b 1
  )
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip wheel
if errorlevel 1 goto :fail

echo.
echo Installing PyTorch CUDA 12.8 wheels ...
pip install --index-url https://download.pytorch.org/whl/cu128 torch torchaudio
if errorlevel 1 (
  echo.
  echo CUDA 12.8 wheels failed ? trying cu124 ...
  pip install --index-url https://download.pytorch.org/whl/cu124 torch torchaudio
  if errorlevel 1 goto :fail
)

echo.
echo Installing SFX Desk requirements ...
pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo Installing Stable Audio 3 Small-SFX package ...
pip install "stable-audio-3 @ git+https://github.com/Stability-AI/stable-audio-3.git"
if errorlevel 1 goto :fail

echo.
echo ========================================
echo   Hugging Face access ^(YOUR account^)
echo ========================================
echo 1^) Accept the model license in your browser:
echo    https://huggingface.co/stabilityai/stable-audio-3-small-sfx
echo.
start "" "https://huggingface.co/stabilityai/stable-audio-3-small-sfx"
echo 2^) Log in so downloads work. Prefer the BROWSER flow when prompted.
echo    Or paste a read token from https://huggingface.co/settings/tokens
echo    Never commit a token to git.
echo.
pause
hf auth login
if errorlevel 1 (
  echo Trying legacy entrypoint ...
  huggingface-cli login
)

echo.
echo Checking CUDA ...
python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no GPU')"

echo.
echo ========================================
echo   Setup complete
echo ========================================
echo Run:  scripts\run_windows.bat
echo Optional MOSS: see SETUP.md ^(16 GB+ VRAM^)
echo.
pause
exit /b 0

:fail
echo.
echo Setup failed. See SETUP.md or open an issue.
pause
exit /b 1
