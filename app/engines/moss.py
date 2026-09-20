"""MOSS-SoundEffect v2.0 engine."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

from app.engines.base import StatusCb, empty_cuda_cache, save_wav_soundfile

_MODEL = None
MODEL_ID = "OpenMOSS-Team/MOSS-SoundEffect-v2.0"


class MossUnavailable(RuntimeError):
    pass


def is_loaded() -> bool:
    return _MODEL is not None


def unload() -> str:
    global _MODEL
    _MODEL = None
    msg = empty_cuda_cache()
    return f"MOSS unloaded. {msg}"


def _disable_compile(pipe) -> None:
    try:
        import torch
        torch._dynamo.config.disable = True  # type: ignore[attr-defined]
    except Exception:
        pass
    for name in ("dit", "transformer", "model", "unet", "backbone"):
        mod = getattr(pipe, name, None)
        if mod is None:
            continue
        orig = getattr(mod, "_orig_mod", None)
        if orig is not None:
            try:
                setattr(pipe, name, orig)
            except Exception:
                pass


def _load(status: StatusCb = None):
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if status:
        status("Loading MOSS-SoundEffect v2.0...")
    try:
        import torch
    except ImportError as e:
        raise MossUnavailable("PyTorch is not installed.") from e

    try:
        torch._dynamo.config.disable = True  # type: ignore[attr-defined]
    except Exception:
        pass

    pipe_cls = None
    err = None
    for mod_name, attr in (
        ("moss_soundeffect_v2", "MossSoundEffectPipeline"),
        ("moss_soundeffect_v2.pipeline_moss_soundeffect", "MossSoundEffectPipeline"),
        ("moss_soundeffect_v2.pipeline", "MossSoundEffectPipeline"),
    ):
        try:
            mod = __import__(mod_name, fromlist=[attr])
            pipe_cls = getattr(mod, attr)
            break
        except Exception as e:
            err = e
    if pipe_cls is None:
        raise MossUnavailable(
            "moss_soundeffect_v2 not installed. See README (MOSS-TTS / moss_soundeffect_v2)."
        ) from err

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    _MODEL = pipe_cls.from_pretrained(MODEL_ID, torch_dtype=dtype, device=device)
    _disable_compile(_MODEL)
    return _MODEL


def generate(
    prompt: str,
    seconds: float = 4.0,
    steps: int = 50,
    cfg_scale: float = 4.0,
    negative_prompt: str = "",
    status_cb: StatusCb = None,
) -> Path:
    def status(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    pipe = _load(status)
    _disable_compile(pipe)
    seconds = max(1.0, min(float(seconds), 30.0))
    steps = max(10, int(steps))
    status(f"MOSS generating ({seconds:.1f}s, {steps} steps)...")

    attempts = [
        dict(
            prompt=prompt,
            seconds=seconds,
            num_inference_steps=steps,
            cfg_scale=float(cfg_scale),
            negative_prompt=negative_prompt or "",
        ),
        dict(
            prompt=prompt,
            seconds=seconds,
            num_inference_steps=steps,
            cfg_scale=float(cfg_scale),
        ),
        dict(prompt=prompt, seconds=seconds, num_inference_steps=steps, cfg_scale=float(cfg_scale)),
        dict(prompt=prompt, seconds=seconds),
    ]
    audio = None
    last_err = None
    for kw in attempts:
        try:
            audio = pipe(**kw)
            break
        except TypeError as e:
            last_err = e
            continue
    if audio is None:
        try:
            audio = pipe(prompt, seconds=seconds)
        except Exception as e:
            raise RuntimeError(f"MOSS pipeline call failed: {last_err or e}") from e

    sr = (
        getattr(getattr(pipe, "config", None), "sampling_rate", None)
        or getattr(pipe, "sample_rate", None)
        or 48000
    )
    out = Path(tempfile.gettempdir()) / "sfx_desk_last.wav"
    status("Saving WAV...")
    save_wav_soundfile(out, audio, int(sr))
    status("Done (MOSS)")
    return out
