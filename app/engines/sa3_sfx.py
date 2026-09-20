"""Stable Audio 3 Small-SFX engine (light VRAM).

Official API:
  from stable_audio_3 import StableAudioModel
  model = StableAudioModel.from_pretrained("small-sfx")
  audio = model.generate(prompt=..., duration=seconds)

Post-trained recipe: steps=8, cfg~1.0 (CFG/neg ignored on post-trained).
Peak VRAM for small is ~1.7-2.4 GB.

Note: from_pretrained only accepts short ids like "small-sfx",
NOT full HF paths like "stabilityai/stable-audio-3-small-sfx".
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from app.engines.base import StatusCb, empty_cuda_cache, save_wav_soundfile

_MODEL = None
MODEL_ID = "small-sfx"


class Sa3Unavailable(RuntimeError):
    pass


def is_loaded() -> bool:
    return _MODEL is not None


def unload() -> str:
    global _MODEL
    _MODEL = None
    msg = empty_cuda_cache()
    return f"SA3 Small-SFX unloaded. {msg}"


def _load(status: StatusCb = None):
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if status:
        status("Loading Stable Audio 3 Small-SFX...")
    try:
        from stable_audio_3 import StableAudioModel
    except ImportError as e:
        raise Sa3Unavailable(
            "stable_audio_3 not installed.\n"
            "  pip install git+https://github.com/Stability-AI/stable-audio-3.git\n"
            "  huggingface-cli login\n"
            "  Accept license: https://huggingface.co/stabilityai/stable-audio-3-small-sfx"
        ) from e
    try:
        # Must be short id — full HF repo paths raise Unknown model
        _MODEL = StableAudioModel.from_pretrained(MODEL_ID)
    except Exception as e:
        raise Sa3Unavailable(
            f"Failed to load '{MODEL_ID}'.\n"
            "Accept the HF license and run: huggingface-cli login\n"
            f"Details: {e}"
        ) from e
    return _MODEL


def generate(
    prompt: str,
    seconds: float = 4.0,
    steps: int = 8,
    cfg_scale: float = 1.0,
    negative_prompt: str = "",
    status_cb: StatusCb = None,
) -> Path:
    del negative_prompt, cfg_scale  # post-trained small-sfx ignores these

    def status(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    model = _load(status)
    seconds = max(1.0, min(float(seconds), 120.0))
    steps = max(4, min(int(steps), 32))
    status(f"SA3-SFX generating ({seconds:.1f}s, {steps} steps)...")

    try:
        audio = model.generate(prompt=prompt, duration=float(seconds), steps=int(steps))
    except TypeError:
        try:
            audio = model.generate(prompt=prompt, duration=float(seconds), num_steps=int(steps))
        except TypeError:
            audio = model.generate(prompt=prompt, duration=float(seconds))

    sr = (
        getattr(model, "sample_rate", None)
        or getattr(model, "sampling_rate", None)
        or getattr(getattr(model, "config", None), "sample_rate", None)
        or 44100
    )
    out = Path(tempfile.gettempdir()) / "sfx_desk_last.wav"
    status("Saving WAV...")
    save_wav_soundfile(out, audio, int(sr))
    status("Done (SA3 Small-SFX)")
    return out
