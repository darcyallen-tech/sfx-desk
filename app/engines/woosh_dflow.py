"""Sony Woosh-DFlow distilled T2A engine (in-process torch).

Weights (CC BY-NC 4.0) live under %USERPROFILE%\\woosh-models\\checkpoints\\
matching the moss-gguf USERPROFILE pattern (overridable in settings).

Needs:
  checkpoints/Woosh-AE/
  checkpoints/TextConditionerA/
  checkpoints/Woosh-DFlow/

Lazy-loads on first Generate. Unload frees VRAM via empty_cuda_cache.
"""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from app.engines.base import StatusCb, empty_cuda_cache, save_wav_soundfile

HF_REPO = "AEmotionStudio/woosh-models"
DEFAULT_ROOT = Path.home() / "woosh-models"
REQUIRED_COMPONENTS = ("Woosh-AE", "TextConditionerA", "Woosh-DFlow")
SAMPLE_RATE = 48000
LATENT_CHANNELS = 128
# ~100 latent frames ~= 1 s at 48 kHz after AE
FRAMES_PER_SEC = 100.0
DEFAULT_RENOISE = [0.0, 0.5, 0.5, 0.3]

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
        if not folder.is_dir() or not weights.is_file() or not cfg.is_file():
            missing.append(name)
    return missing


def is_loaded() -> bool:
    return _MODEL is not None


def unload() -> str:
    global _MODEL, _DEVICE
    _MODEL = None
    _DEVICE = None
    msg = empty_cuda_cache()
    return f"Woosh DFlow unloaded. {msg}"


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
    # Keep within DiT rope / max_seq_len envelope used by public configs (501 ~5s)
    return max(100, min(1001, frames))


def _load(status: StatusCb = None):
    global _MODEL, _DEVICE
    if _MODEL is not None:
        return _MODEL

    # Mutual exclusion with full Flow (same AE/conditioner VRAM)
    try:
        from app.engines import woosh_flow

        if woosh_flow.is_loaded():
            if status:
                status("Unloading Woosh Flow before DFlow...")
            woosh_flow.unload()
    except Exception:
        pass

    def status_msg(msg: str) -> None:
        if status:
            status(msg)

    root = resolve_root()
    missing = missing_components(root)
    if missing:
        raise WooshUnavailable(
            "Woosh DFlow weights missing: "
            + ", ".join(missing)
            + f".\nDownload into {root}\\\\checkpoints\\\\ "
            f"(HF: {HF_REPO}) or run scripts\\\\download_woosh_weights.bat.\n"
            "Override with settings key woosh_models_root / "
            "SFX_DESK_WOOSH_ROOT."
        )

    try:
        from woosh.components.base import LoadConfig
        from woosh.model.flowmap_from_pretrained import FlowMapFromPretrained
    except ImportError as e:
        raise WooshUnavailable(
            "woosh package not installed.\n"
            "  pip install -e git+https://github.com/SonyResearch/Woosh.git@v1.0.0#egg=woosh\n"
            "  (or run scripts\\setup_woosh.bat)\n"
            f"Details: {e}"
        ) from e

    status_msg(f"Loading Woosh DFlow from {root}...")
    device = _pick_device()
    # Nested configs reference checkpoints/TextConditionerA + Woosh-AE relative to root
    with _chdir(root):
        ldm = FlowMapFromPretrained(LoadConfig(path="checkpoints/Woosh-DFlow"))
        ldm = ldm.eval().to(device)

    _MODEL = ldm
    _DEVICE = device
    status_msg(f"Woosh DFlow ready on {device}")
    return _MODEL


def generate(
    prompt: str,
    seconds: float = 4.0,
    steps: int = 4,
    cfg_scale: float = 4.0,
    negative_prompt: str = "",  # noqa: ARG001 — DFlow has no neg prompt path
    status_cb: StatusCb = None,
    seed: int | None = None,
) -> Path:
    """Generate a WAV via distilled FlowMap Euler (default 4 steps)."""
    import torch

    from woosh.inference.flowmap_sampler import sample_euler

    def status(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    prompt = (prompt or "").strip()
    if not prompt:
        raise WooshUnavailable("Prompt is empty.")

    model = _load(status)
    device = _DEVICE or _pick_device()
    seconds = max(1.0, min(float(seconds), 10.0))
    steps = max(1, min(int(steps), 8))
    cfg = max(0.0, min(float(cfg_scale), 9.0))
    frames = _seconds_to_frames(seconds)

    # Match Sony demo renoise schedule when using 4 steps; otherwise constant 0.5
    if steps == 4:
        renoise: float | list[float] = list(DEFAULT_RENOISE)
    else:
        renoise = 0.5

    status(
        f"Woosh DFlow generating ({seconds:.1f}s -> {frames} frames, "
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
        latents = sample_euler(
            model=model,
            noise=noise,
            cond=cond,
            num_steps=steps,
            renoise=renoise,
            cfg=cfg,
        )
        audio = model.autoencoder.inverse(latents)

    out = Path(tempfile.gettempdir()) / "sfx_desk_last.wav"
    status("Saving WAV...")
    save_wav_soundfile(out, audio, SAMPLE_RATE)
    status("Done (Woosh DFlow)")
    return out
