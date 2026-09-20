"""Sony Woosh-Flow full T2A engine (in-process torch).

Weights (CC BY-NC 4.0) live under %USERPROFILE%\\woosh-models\\checkpoints\\
matching the moss-gguf USERPROFILE pattern (overridable in settings).

Needs:
  checkpoints/Woosh-AE/
  checkpoints/TextConditionerA/
  checkpoints/Woosh-Flow/

Lazy-loads on first Generate. Unload frees VRAM via empty_cuda_cache.
Defaults: 50 Euler steps, CFG 4.5, renoise 0.0 (ODE / flow-matching path).
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
        from app import settings as prefs

        data = prefs.load()
        root = str(data.get("woosh_models_root") or root).strip()
    except Exception:
        pass
    return root


def resolve_root() -> Path:
    override = _load_overrides()
    if override:
        return Path(override)
    return DEFAULT_ROOT


def checkpoints_dir(root: Path | None = None) -> Path:
    return (root or resolve_root()) / "checkpoints"


def missing_components(root: Path | None = None) -> list[str]:
    ckpt = checkpoints_dir(root)
    missing: list[str] = []
    for name in REQUIRED_COMPONENTS:
        folder = ckpt / name
        weights = folder / "weights.safetensors"
        cfg = folder / "config.yaml"
        cfg_alt = folder / "config.yml"
        if (
            not folder.is_dir()
            or not weights.is_file()
            or not (cfg.is_file() or cfg_alt.is_file())
        ):
            missing.append(name)
    return missing


def is_loaded() -> bool:
    return _MODEL is not None


def unload() -> str:
    global _MODEL, _DEVICE
    _MODEL = None
    _DEVICE = None
    msg = empty_cuda_cache()
    return f"Woosh Flow unloaded. {msg}"


@contextmanager
def _chdir(path: Path):
    prev = Path.cwd()
    os.chdir(str(path))
    try:
        yield
    finally:
        os.chdir(str(prev))


def _pick_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _seconds_to_frames(seconds: float) -> int:
    seconds = max(1.0, min(float(seconds), 10.0))
    frames = int(round(seconds * FRAMES_PER_SEC))
    return max(100, min(1001, frames))


def _load(status: StatusCb = None):
    global _MODEL, _DEVICE
    if _MODEL is not None:
        return _MODEL

    # Mutual exclusion with distilled DFlow (same AE/conditioner VRAM)
    try:
        from app.engines import woosh_dflow

        if woosh_dflow.is_loaded():
            if status:
                status("Unloading Woosh DFlow before Flow...")
            woosh_dflow.unload()
    except Exception:
        pass

    def status_msg(msg: str) -> None:
        if status:
            status(msg)

    root = resolve_root()
    missing = missing_components(root)
    if missing:
        raise WooshUnavailable(
            "Woosh Flow weights missing: "
            + ", ".join(missing)
            + f".\nDownload into {root}\\\\checkpoints\\\\ "
            f"(HF: {HF_REPO}) — need Woosh-Flow (+ AE + TextConditionerA).\n"
            "Override with settings key woosh_models_root / "
            "SFX_DESK_WOOSH_ROOT."
        )

    try:
        from woosh.components.base import LoadConfig
        from woosh.model.ldm import LatentDiffusionModel
    except ImportError as e:
        raise WooshUnavailable(
            "woosh package not installed.\n"
            "  pip install -e git+https://github.com/SonyResearch/Woosh.git@v1.0.0#egg=woosh\n"
            "  (or run scripts\\setup_woosh.bat)\n"
            f"Details: {e}"
        ) from e

    status_msg(f"Loading Woosh Flow from {root}...")
    device = _pick_device()
    with _chdir(root):
        ldm = LatentDiffusionModel(LoadConfig(path="checkpoints/Woosh-Flow"))
        ldm = ldm.eval().to(device)

    _MODEL = ldm
    _DEVICE = device
    status_msg(f"Woosh Flow ready on {device}")
    return _MODEL


def _integrate_fixed_steps(model, noise, cond, *, num_steps: int, cfg: float, device: str):
    """Fixed-step Euler CFG integrate (matches Sony flowmatching_integrate math)."""
    import torch

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
    # Manual Euler so we honor the requested step count (odeint euler with
    # only endpoints would not expose intermediate steps cleanly).
    y = noise
    dt = 1.0 / steps
    for i in range(steps):
        t_i = torch.tensor(i * dt, device=noise.device, dtype=noise.dtype)
        y = y + dt * f(t_i, y)
    return y, nfe


def generate(
    prompt: str,
    seconds: float = 4.0,
    steps: int = 50,
    cfg_scale: float = 4.5,
    negative_prompt: str = "",  # noqa: ARG001 — Flow path has no neg prompt wiring yet
    status_cb: StatusCb = None,
    seed: int | None = None,
    renoise: float = 0.0,  # noqa: ARG001 — ODE path; reserved for API parity with DFlow
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
                return_steps=True,
            )
            latents = result[0] if isinstance(result, tuple) else result
        audio = model.autoencoder.inverse(latents)

    out = Path(tempfile.gettempdir()) / "sfx_desk_last.wav"
    status("Saving WAV...")
    save_wav_soundfile(out, audio, SAMPLE_RATE)
    status("Done (Woosh Flow)")
    return out
