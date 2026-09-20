"""Entry point for SFX Desk."""
from __future__ import annotations

import os
import sys

# Must run before torch / MOSS import — Windows has no Triton for torch.compile
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
os.environ.setdefault("TORCHINDUCTOR_DISABLE", "1")
# pythonw has no console — HF/tqdm crash with NoneType.write without this
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")


def _ensure_stdio() -> None:
    """pythonw sets stdout/stderr to None; redirect to a log file."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_dir = os.path.join(os.path.expanduser("~"), "SFX Desk")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "sfx_desk.log")
    stream = open(log_path, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = stream  # type: ignore[assignment]
    if sys.stderr is None:
        sys.stderr = stream  # type: ignore[assignment]


_ensure_stdio()


def main() -> None:
    from app.ui import SfxDeskApp

    app = SfxDeskApp()
    app.mainloop()


if __name__ == "__main__":
    main()
