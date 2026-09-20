# SFX Desk setup guide (hand-holding)

You need: a Windows PC, an **NVIDIA** GPU, internet, and a free [Hugging Face](https://huggingface.co) account.

## 1. Python

1. Download **Python 3.12** from https://www.python.org/downloads/
2. Run the installer.
3. Check **Add python.exe to PATH**.
4. Finish install.

## 2. Get SFX Desk

```bat
git clone https://github.com/darcyallen-tech/sfx-desk.git
cd sfx-desk
```

(Or download the ZIP from GitHub and unzip.)

## 3. One-click setup

Double-click:

```text
scripts\setup_windows.bat
```

It will:

1. Create a local `.venv` folder (your private Python env)
2. Install **PyTorch** with CUDA
3. Install SFX Desk + **Stable Audio 3 Small-SFX**
4. Open the **license page** in your browser
5. Ask you to log into Hugging Face

### Hugging Face login — browser vs token

When `hf auth login` runs you usually get a choice:

- **Browser (recommended):** opens Hugging Face, you approve, done. No need to copy a long key.
- **Token:** create a **Read** token at https://huggingface.co/settings/tokens and paste it when asked.

Use **your** account. Do not share tokens. Do not put tokens in the repo or screenshots.

Also click **Agree** on the model page (gated weights):

https://huggingface.co/stabilityai/stable-audio-3-small-sfx

If login fails later, run:

```text
scripts\hf_login.bat
```

## 4. Launch

```text
scripts\run_windows.bat
```

You should see **SA3 Small-SFX** as the default engine. Generate a short whoosh to confirm.

## 5. Resolve

1. Open DaVinci Resolve (free is fine).
2. Preferences → System → General → External scripting → **Local**.
3. Open a project.
4. In SFX Desk: **Send** (or Auto-send) → clips land in bin `SFX Desk`.

## Optional: MOSS (heavy)

MOSS is **not** installed by the default setup. It needs ~16 GB VRAM minimum and a separate install from the [OpenMOSS MOSS-TTS](https://github.com/OpenMOSS/MOSS-TTS) `moss_soundeffect_v2` docs.

On 16 GB cards: close Resolve while generating, then Unload, then Send.  
~24 GB is comfortable with Resolve open.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python` not found | Reinstall Python 3.12 with PATH checked |
| CUDA not available | Update NVIDIA driver; re-run setup (torch CUDA wheels) |
| SA3 download 401/403 | Accept license + `scripts\hf_login.bat` |
| Resolve Send fails | Resolve open, project open, External scripting = Local |
| First gen slow | Normal (model download / compile). Later gens are faster with **Keep** on |

## Privacy

- Tokens live in your HF cache / login — not in this git repo.
- Library WAVs and `settings.json` stay on your machine under `%USERPROFILE%\SFX Desk\`.
