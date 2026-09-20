"""Shared engine helpers."""
from __future__ import annotations

import gc
from pathlib import Path
from typing import Callable

StatusCb = Callable[[str], None] | None


def empty_cuda_cache() -> str:
    try:
        import torch
    except ImportError:
        return "PyTorch not installed"
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
        alloc = torch.cuda.memory_allocated() / (1024 ** 3)
        reserved = torch.cuda.memory_reserved() / (1024 ** 3)
        return f"CUDA cache cleared (alloc {alloc:.2f} GB, reserved {reserved:.2f} GB)"
    return "No CUDA device"


def save_wav_soundfile(path: Path, audio, sample_rate: int = 48000) -> None:
    """Save tensor/ndarray to WAV without torchcodec."""
    import numpy as np
    import soundfile as sf

    try:
        import torch
    except ImportError:
        torch = None  # type: ignore

    wav = audio
    if isinstance(wav, (tuple, list)):
        wav = wav[0]
    if isinstance(wav, dict):
        for key in ("audio", "waveform", "samples", "wav"):
            if key in wav:
                wav = wav[key]
                break
    if torch is not None and isinstance(wav, torch.Tensor):
        wav = wav.detach().float().cpu()
        if wav.ndim == 3:
            wav = wav[0]
        if wav.ndim == 2 and wav.shape[0] <= 8:
            wav = wav.transpose(0, 1)
        arr = wav.numpy()
    else:
        arr = np.asarray(wav, dtype=np.float32)
        if arr.ndim == 2 and arr.shape[0] <= 8:
            arr = arr.T
    # peak normalize lightly to avoid clips
    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
    if peak > 1.0:
        arr = arr / peak
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), arr.astype(np.float32, copy=False), int(sample_rate), subtype="PCM_16")


MOSS_MIN_VRAM_GB = 16.0
MOSS_COMFORT_VRAM_GB = 24.0
GGUF_MIN_VRAM_GB = 12.0
WOOSH_MIN_VRAM_GB = 6.0
WOOSH_FLOW_MIN_VRAM_GB = 10.0


def probe_vram() -> dict:
    """Return GPU VRAM info without loading any SFX model.

    Keys: ok, cuda, name, total_gb, free_gb, message
    """
    try:
        import torch
    except ImportError:
        return {
            "ok": False,
            "cuda": False,
            "name": "",
            "total_gb": 0.0,
            "free_gb": 0.0,
            "message": "PyTorch not installed",
        }
    if not torch.cuda.is_available():
        return {
            "ok": False,
            "cuda": False,
            "name": "",
            "total_gb": 0.0,
            "free_gb": 0.0,
            "message": "No CUDA GPU detected",
        }
    try:
        idx = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(idx)
        total = float(props.total_memory) / (1024 ** 3)
        free, _ = torch.cuda.mem_get_info(idx)
        free_gb = float(free) / (1024 ** 3)
        name = getattr(props, "name", f"cuda:{idx}") or f"cuda:{idx}"
        return {
            "ok": True,
            "cuda": True,
            "name": str(name),
            "total_gb": round(total, 2),
            "free_gb": round(free_gb, 2),
            "message": f"{name}: {total:.1f} GB VRAM ({free_gb:.1f} GB free)",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "cuda": True,
            "name": "",
            "total_gb": 0.0,
            "free_gb": 0.0,
            "message": f"CUDA probe failed: {e}",
        }


def moss_vram_status(force_enable: bool = False, info: dict | None = None) -> dict:
    """Whether MOSS should be offered.

    unlocked: enough total VRAM (>=16 GB) or user force-enabled
    comfortable: >=24 GB (Resolve + MOSS kept loaded is realistic)
    """
    info = info if info is not None else probe_vram()
    total = float(info.get("total_gb") or 0.0)
    enough = bool(info.get("ok")) and round(total) >= int(MOSS_MIN_VRAM_GB)
    comfortable = bool(info.get("ok")) and round(total) >= int(MOSS_COMFORT_VRAM_GB)
    unlocked = enough or bool(force_enable)
    if not info.get("cuda"):
        tip = "MOSS needs an NVIDIA GPU. Use SA3 Small-SFX."
    elif not enough and not force_enable:
        tip = (
            f"MOSS needs ~{MOSS_MIN_VRAM_GB:.0f} GB VRAM (you have {total:.1f} GB). "
            f"SA3 is the daily driver. At {MOSS_MIN_VRAM_GB:.0f} GB: close Resolve, generate, Unload, then Send. "
            f"~{MOSS_COMFORT_VRAM_GB:.0f} GB is comfortable with Resolve open."
        )
    elif enough and not comfortable:
        tip = (
            f"MOSS OK at {total:.1f} GB - close Resolve while generating, then Unload before reopening. "
            f"~{MOSS_COMFORT_VRAM_GB:.0f} GB is comfortable keeping both open."
        )
    else:
        tip = f"MOSS comfortable at {total:.1f} GB with Resolve open."
    return {
        "info": info,
        "enough": enough,
        "comfortable": comfortable,
        "unlocked": unlocked,
        "forced": bool(force_enable) and not enough,
        "tip": tip,
        "min_gb": MOSS_MIN_VRAM_GB,
        "comfort_gb": MOSS_COMFORT_VRAM_GB,
    }


def moss_gguf_vram_status(force_enable: bool = False, info: dict | None = None) -> dict:
    """Whether MOSS GGUF should be offered. Needs ~12 GB."""
    info = info if info is not None else probe_vram()
    total = float(info.get("total_gb") or 0.0)
    enough = bool(info.get("ok")) and round(total) >= int(GGUF_MIN_VRAM_GB)
    unlocked = enough or bool(force_enable)
    if not info.get("cuda"):
        tip = "MOSS GGUF needs an NVIDIA GPU. Use SA3 Small-SFX."
    elif not enough and not force_enable:
        tip = (
            f"MOSS GGUF needs ~{GGUF_MIN_VRAM_GB:.0f} GB VRAM (you have {total:.1f} GB). "
            "SA3 is the daily driver; GGUF is the slow quality option."
        )
    else:
        tip = (
            f"MOSS GGUF OK at {total:.1f} GB - much slower than SA3 "
            "(often minutes). Unload stops moss-tts-server."
        )
    return {
        "info": info,
        "enough": enough,
        "unlocked": unlocked,
        "forced": bool(force_enable) and not enough,
        "tip": tip,
        "min_gb": GGUF_MIN_VRAM_GB,
    }


def woosh_vram_status(force_enable: bool = False, info: dict | None = None) -> dict:
    """Whether Woosh DFlow should be offered. Peak ~6 GB; 16 GB card OK."""
    info = info if info is not None else probe_vram()
    total = float(info.get("total_gb") or 0.0)
    enough = bool(info.get("ok")) and round(total) >= int(WOOSH_MIN_VRAM_GB)
    unlocked = enough or bool(force_enable)
    if not info.get("cuda"):
        tip = "Woosh DFlow needs an NVIDIA GPU. Use SA3 Small-SFX."
    elif not enough and not force_enable:
        tip = (
            f"Woosh DFlow needs ~{WOOSH_MIN_VRAM_GB:.0f} GB VRAM (you have {total:.1f} GB). "
            "SA3 is the daily driver."
        )
    else:
        tip = (
            f"Woosh DFlow OK at {total:.1f} GB — distilled T2A (4 steps). "
            "Free-text prompts; Unload frees VRAM. Weights: CC BY-NC 4.0."
        )
    return {
        "info": info,
        "enough": enough,
        "unlocked": unlocked,
        "forced": bool(force_enable) and not enough,
        "tip": tip,
        "min_gb": WOOSH_MIN_VRAM_GB,
    }


def woosh_flow_vram_status(force_enable: bool = False, info: dict | None = None) -> dict:
    """Whether Woosh Flow should be offered. Soft gate ~10 GB; 16 GB card OK."""
    info = info if info is not None else probe_vram()
    total = float(info.get("total_gb") or 0.0)
    enough = bool(info.get("ok")) and round(total) >= int(WOOSH_FLOW_MIN_VRAM_GB)
    unlocked = enough or bool(force_enable)
    if not info.get("cuda"):
        tip = "Woosh Flow needs an NVIDIA GPU. Use SA3 Small-SFX."
    elif not enough and not force_enable:
        tip = (
            f"Woosh Flow needs ~{WOOSH_FLOW_MIN_VRAM_GB:.0f} GB VRAM (you have {total:.1f} GB). "
            "Try Woosh DFlow (~6 GB) or SA3."
        )
    else:
        tip = (
            f"Woosh Flow OK at {total:.1f} GB — full T2A (50 steps, CFG 4.5). "
            "Free-text prompts; Unload frees VRAM. Weights: CC BY-NC 4.0."
        )
    return {
        "info": info,
        "enough": enough,
        "unlocked": unlocked,
        "forced": bool(force_enable) and not enough,
        "tip": tip,
        "min_gb": WOOSH_FLOW_MIN_VRAM_GB,
    }
