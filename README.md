# SFX Desk

Always-on-top desktop SFX generator for **DaVinci Resolve** (free or Studio).

**Free and open source (MIT).** No price tag. If you want to support development:

> **Donate (PayPal):** _add your PayPal.me link here_

Supported path for v1: **Windows + NVIDIA CUDA**.

---

## Quick start (Windows)

1. Install [Python 3.12](https://www.python.org/downloads/) (check **Add to PATH**).
2. Clone this repo.
3. Double-click **`scripts\setup_windows.bat`**  
   - Creates `.venv`  
   - Installs PyTorch CUDA + SA3  
   - Opens the SA3 license page  
   - Runs **`hf auth login`** — prefer the **browser** option, or paste a **read** token from [HF tokens](https://huggingface.co/settings/tokens)  
   - Use **your** Hugging Face account. Never commit a token.
4. Accept the gated model license:  
   https://huggingface.co/stabilityai/stable-audio-3-small-sfx
5. Launch with **`scripts\run_windows.bat`**

More detail: [SETUP.md](SETUP.md)

---

## Engines

| Engine | VRAM | Role |
|--------|------|------|
| **SA3 Small-SFX** (default) | ~2–4 GB | Daily driver — fine with Resolve open |
| **MOSS-SoundEffect v2** | ~13–14 GB alone | Optional quality; see VRAM rules |

### MOSS VRAM (plain English)

- **Under 16 GB:** MOSS locked (optional **Force MOSS**). Use SA3.
- **~16 GB:** Close Resolve → generate → **Unload** → open Resolve → **Send**.
- **~20–24 GB:** Comfortable with Resolve open + MOSS kept loaded.

---

## Resolve Send

Works on **free Resolve and Studio**.  
Preferences → System → General → **External scripting: Local**.  
Imports into Media Pool bin `SFX Desk` only (no timeline drop). Multi-select supported.

---

## What this repo does *not* include

- Your Hugging Face token  
- Downloaded model weights  
- Local library / WAVs / `settings.json`  
- A paid unlock  

Everyone brings their own HF account and accepts Stability’s license themselves.

---

## License

MIT — see [LICENSE](LICENSE).  
Third-party models (SA3, MOSS) have their **own** licenses; you must accept those on Hugging Face.
