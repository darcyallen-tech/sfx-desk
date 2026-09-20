"""CLI smoke: one short Woosh DFlow gen + nvidia-smi peak if available."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def nvidia_used_mb() -> float | None:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=10,
        )
        return float(out.strip().splitlines()[0])
    except Exception:
        return None


def main() -> int:
    from app.engines import woosh_dflow

    prompt = "a fast airy whoosh, outdoor open air, clear sound design, no speech"
    seconds = 3.0
    print(f"root={woosh_dflow.resolve_root()}")
    print(f"missing={woosh_dflow.missing_components()}")
    before = nvidia_used_mb()
    t0 = time.perf_counter()
    peak = before

    def cb(m: str) -> None:
        nonlocal peak
        print(f"  status: {m}")
        used = nvidia_used_mb()
        if used is not None and (peak is None or used > peak):
            peak = used

    path = woosh_dflow.generate(
        prompt, seconds=seconds, steps=4, cfg_scale=4.0, status_cb=cb
    )
    elapsed = time.perf_counter() - t0
    after = nvidia_used_mb()
    size = path.stat().st_size if path.is_file() else 0
    print(f"wav={path} bytes={size}")
    print(f"wall_s={elapsed:.2f}")
    print(f"vram_before_mb={before} peak_mb={peak} after_mb={after}")
    print(woosh_dflow.unload())
    freed = nvidia_used_mb()
    print(f"vram_after_unload_mb={freed}")
    if elapsed >= 60:
        print("WARN: warm/cold wall >= 60s product cut rule")
        return 2
    return 0 if size > 1000 else 1


if __name__ == "__main__":
    raise SystemExit(main())
