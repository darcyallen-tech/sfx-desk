@echo off
cd /d "%~dp0.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
echo Open the SA3 license page, then log in with YOUR Hugging Face account.
echo Prefer the browser option when hf auth login asks.
start "" "https://huggingface.co/stabilityai/stable-audio-3-small-sfx"
pause
hf auth login
if errorlevel 1 huggingface-cli login
pause
