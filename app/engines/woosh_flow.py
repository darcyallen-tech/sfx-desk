"""Sony Woosh-Flow full T2A engine (in-process torch).

Weights (CC BY-NC 4.0) live under %USERPROFILE%\\woosh-models\\checkpoints\\
matching the moss-gguf USERPROFILE pattern (overridable in settings).

Needs:
  checkpoints/Woosh-AE/
  checkpoints/TextConditionerA/
  checkpoints/Woosh-Flow/

Lazy-loads on first Generate. Unload frees VRAM via empty_cuda_cache.
Defaults: 50 steps, CFG 4.5, renoise 0.0 (ODE path; renoise reserved/ignored).
"""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from app.engines.base import StatusCb, empty_cuda_cache, save_wav_soundfile

HF_REPO = "AEmotionStudio/woosh-models"
DEFAULT_ROOT = Path.home() / "woosh-models"
REQUIRED_COMPONENTS = ("Woosh-AE", "TextConditionerA", "Woosh-Flow")
SAMPLE_RATE = 48000
LATENT_CHANNELS = 128
# ~100 latent frames ~= 1 s at 48 kHz after AE
FRAMES_PER_SEC = 100.0

_MODEL = None
_DEVICE: str | None = None


class WooshUnavailable(RuntimeError):
    pass


def _load_overrides() -> str:
    root = os.environ.get("SFX_DESK_WOOSH_ROOT", "").strip().strip('"')
    try:
        from woosh.components.base import LoadConfig
        try:
            from woosh.model.ldm import LatentDiffusionModel
        except ImportError:
            from woosh.model.latent_diffusion import LatentDiffusionModel
    except ImportError as e:
        raise WooshUnavailable(
            "woosh package not installed.\n"
            "  pip install -e git+https://github.com/SonyResearch/Woosh.git@v1.0.0#egg=woosh\n"
            "  (or run scripts\\setup_woosh.bat)\n"
            f"Details: {e}"
        ) from e

    status_msg(f"Loading Woosh Flow from {root}...")
    device = _pick_device()
    # Nested configs reference checkpoints/TextConditionerA + Woosh-AE relative to root
    with _chdir(root):
        ldm = LatentDiffusionModel(LoadConfig(path="checkpoints/Woosh-Flow"))
        ldm = ldm.eval().to(device)

    _MODEL = ldm
    _DEVICE = device
    status_msg(f"Woosh Flow ready on {device}")
    return _MODEL


def _integrate_fixed_steps(model, noise, cond, *, num_steps: int, cfg: float, device: str):
    """Fixed-step Euler CFG integrate. Mirrors Sony flowmatching_integrate CFG math."""
    import torch
    from torchdiffeq import odeint

    no_cond = model.get_cond(
        {"audio": noise, "description": [""]},
        no_dropout=True,
        device=device,
        no_cond=True,
    )

    nfe = 0

    def f(t, y):
        nonlocal nfe
        nfe += 1
        res = model._denoise_dict_no_param(y, 1 - t, cond)["x_hat"]
        res_nc = model._denoise_dict_no_param(y, 1 - t, no_cond)["x_hat"]
        return res + cfg * (res - res_nc)

    steps = max(1, min(int(num_steps), 100))
    t = torch.linspace(0, 1, steps + 1, device=noise.device, dtype=noise.dtype)
    fakes = odeint(f, noise, t, method="euler")[-1]
    return fakes, nfe


def generate(
    prompt: str,
    seconds: float = 4.0,
    steps: int = 50,
    cfg_scale: float = 4.5,
    negative_prompt: str = "",  # noqa: ARG001 — Flow demo path has no neg prompt
    status_cb: StatusCb = None,
    seed: int | None = None,
    renoise: float = 0.0,  # noqa: ARG001 — reserved; ODE path has no renoise
) -> Path:
    """Generate a WAV via full Flow-matching (default 50 steps, CFG 4.5)."""
    import torch

    def status(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    prompt = (prompt or "").strip()
    if not prompt:
        raise WooshUnavailable("Prompt is empty.")

    model = _load(status)
    device = _DEVICE or _pick_device()
    seconds = max(1.0, min(float(seconds), 10.0))
    steps = max(1, min(int(steps), 100))
    cfg = max(0.0, min(float(cfg_scale), 15.0))
    frames = _seconds_to_frames(seconds)

    status(
        f"Woosh Flow generating ({seconds:.1f}s -> {frames} frames, "
        f"{steps} steps, cfg={cfg:g})..."
    )

    if seed is not None and int(seed) >= 0:
        torch.manual_seed(int(seed))
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(int(seed))

    noise = torch.randn(1, LATENT_CHANNELS, frames, device=device)
    cond = model.get_cond(
        {"audio": None, "description": [prompt]},
        no_dropout=True,
        device=device,
    )

    with torch.inference_mode():
        try:
            latents, nfe = _integrate_fixed_steps(
                model, noise, cond, num_steps=steps, cfg=cfg, device=device
            )
            status(f"Flow integrate done ({nfe} NFEs)")
        except Exception as e:
            status(f"Fixed-step integrate failed ({e}); trying adaptive ODE...")
            from woosh.inference.flowmatching_sampler import flowmatching_integrate

            result = flowmatching_integrate(
                model,
                noise=noise,
                cond=cond,
                cfg=cfg,
                device=device,
                method="dopri5",
                atol=0.001,
                rtol=0.001,
            )
            latents = result[0] if isinstance(result, tuple) else result
        audio = model.autoencoder.inverse(latents)

    out = Path(tempfile.gettempdir()) / "sfx_desk_last.wav"
    status("Saving WAV...")
    save_wav_soundfile(out, audio, SAMPLE_RATE)
    status("Done (Woosh Flow)")
    return out
