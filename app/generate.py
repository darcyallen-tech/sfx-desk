"""Multi-engine SFX generation (MOSS v2 + SA3 Small-SFX + MOSS GGUF)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.engines.base import empty_cuda_cache

StatusCb = Callable[[str], None] | None

ENGINES = {
    "moss": "MOSS-SoundEffect v2 (quality)",
    "sa3": "Stable Audio 3 Small-SFX (light VRAM)",
    "moss_gguf": "MOSS-SoundEffect GGUF (slower, ~12GB+)",
}

# Default steps per engine
DEFAULT_STEPS = {"moss": 50, "sa3": 8, "moss_gguf": 12}
DEFAULT_CFG = {"moss": 4.0, "sa3": 1.0, "moss_gguf": 4.0}


def unload_torch_engines() -> str:
    """Unload SA3/MOSS torch weights and clear CUDA.

    Call on the UI/main thread before starting a GGUF worker.
    Does not touch moss-tts-server.
    """
    msgs: list[str] = []
    try:
        from app.engines import moss

        msgs.append(moss.unload())
    except Exception as e:  # noqa: BLE001
        msgs.append(f"MOSS unload: {e}")
    try:
        from app.engines import sa3_sfx

        msgs.append(sa3_sfx.unload())
    except Exception as e:  # noqa: BLE001
        msgs.append(f"SA3 unload: {e}")
    msgs.append(empty_cuda_cache())
    return " | ".join(msgs)


def unload_gguf_server() -> str:
    """Stop moss-tts-server only (no torch.cuda)."""
    try:
        from app.engines import moss_gguf

        return moss_gguf.unload()
    except Exception as e:  # noqa: BLE001
        return f"MOSS GGUF unload: {e}"


def unload_all() -> str:
    msgs = []
    try:
        from app.engines import moss

        msgs.append(moss.unload())
    except Exception as e:  # noqa: BLE001
        msgs.append(f"MOSS unload: {e}")
    try:
        from app.engines import sa3_sfx

        msgs.append(sa3_sfx.unload())
    except Exception as e:  # noqa: BLE001
        msgs.append(f"SA3 unload: {e}")
    msgs.append(unload_gguf_server())
    msgs.append(empty_cuda_cache())
    return " | ".join(msgs)


def generate_sfx(
    prompt: str,
    seconds: float = 4.0,
    steps: int | None = None,
    cfg_scale: float | None = None,
    negative_prompt: str = "",
    engine: str = "moss",
    keep_loaded: bool = True,
    status_cb: StatusCb = None,
) -> Path:
    engine = (engine or "moss").strip().lower()
    if engine not in ENGINES:
        raise ValueError(f"Unknown engine: {engine}")

    if steps is None:
        steps = DEFAULT_STEPS[engine]
    if cfg_scale is None:
        cfg_scale = DEFAULT_CFG[engine]

    def status(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    try:
        if engine == "moss":
            from app.engines import moss

            path = moss.generate(
                prompt,
                seconds=seconds,
                steps=int(steps),
                cfg_scale=float(cfg_scale),
                negative_prompt=negative_prompt,
                status_cb=status_cb,
            )
        elif engine == "moss_gguf":
            from app.engines import moss_gguf

            # Torch unload + empty_cuda_cache must already have run on the
            # UI/main thread before this worker started. Calling torch.cuda
            # here while moss-tts-server owns the GPU causes ACCESS_VIOLATION
            # (0xC0000005) in python312.dll during CUDA graph warmup.
            path = moss_gguf.generate(
                prompt,
                seconds=seconds,
                steps=int(steps),
                cfg_scale=float(cfg_scale),
                negative_prompt=negative_prompt,
                status_cb=status_cb,
            )
        else:
            from app.engines import sa3_sfx

            path = sa3_sfx.generate(
                prompt,
                seconds=seconds,
                steps=int(steps),
                cfg_scale=float(cfg_scale),
                negative_prompt=negative_prompt,
                status_cb=status_cb,
            )
    finally:
        if not keep_loaded:
            status("Unloading model to free VRAM...")
            if engine == "moss_gguf":
                # Stop server only — no torch.cuda from the worker thread.
                status(unload_gguf_server())
            else:
                unload_all()

    return path
