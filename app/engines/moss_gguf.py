"""MOSS-SoundEffect GGUF via openmoss moss-tts-server (slower, ~12 GB+)."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.engines.base import StatusCb

DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"
SERVER_EXE = "moss-tts-server.exe"
MODEL_NAME = "moss-soundeffect-2.0.gguf"
DEFAULT_ROOT = Path.home() / "moss-gguf-test"

_PROC: subprocess.Popen | None = None
_BASE_URL: str | None = None


class MossGgufUnavailable(RuntimeError):
    pass


def _load_overrides() -> tuple[str, str, int]:
    server = os.environ.get("SFX_DESK_MOSS_GGUF_SERVER", "").strip().strip('"')
    model = os.environ.get("SFX_DESK_MOSS_GGUF_MODEL", "").strip().strip('"')
    port_raw = os.environ.get("SFX_DESK_MOSS_GGUF_PORT", "").strip()
    try:
        from app import settings as prefs

        data = prefs.load()
        server = str(data.get("moss_gguf_server") or server).strip()
        model = str(data.get("moss_gguf_model") or model).strip()
        if not port_raw:
            port_raw = str(data.get("moss_gguf_port") or "")
    except Exception:
        pass
    try:
        port = int(port_raw) if port_raw else DEFAULT_PORT
    except ValueError:
        port = DEFAULT_PORT
    return server, model, port


def resolve_server_exe() -> Path:
    server, _, _ = _load_overrides()
    candidates: list[Path] = []
    if server:
        candidates.append(Path(server))
    candidates.extend(
        [
            DEFAULT_ROOT / "runtime" / SERVER_EXE,
            Path.home() / "SFX Desk" / "moss-gguf" / "runtime" / SERVER_EXE,
        ]
    )
    for p in candidates:
        if p.is_file():
            return p
    raise MossGgufUnavailable(
        f"{SERVER_EXE} not found. Put the openmoss Windows CUDA build at "
        f"{DEFAULT_ROOT}\\runtime\\{SERVER_EXE}, or set moss_gguf_server / "
        "SFX_DESK_MOSS_GGUF_SERVER."
    )


def resolve_model() -> Path:
    _, model, _ = _load_overrides()
    candidates: list[Path] = []
    if model:
        candidates.append(Path(model))
    candidates.extend(
        [
            DEFAULT_ROOT / "weights" / MODEL_NAME,
            Path.home() / "SFX Desk" / "moss-gguf" / "weights" / MODEL_NAME,
        ]
    )
    for p in candidates:
        if p.is_file():
            return p
    raise MossGgufUnavailable(
        f"{MODEL_NAME} not found. Download from Hugging Face "
        f"(ilintar/moss-soundeffect-gguf), place under {DEFAULT_ROOT}\\weights\\, "
        "or set moss_gguf_model / SFX_DESK_MOSS_GGUF_MODEL."
    )


def resolve_port() -> int:
    _, _, port = _load_overrides()
    return port


def _base(port: int | None = None) -> str:
    if _BASE_URL:
        return _BASE_URL
    return f"http://{DEFAULT_HOST}:{port or resolve_port()}"


def _http_json(url: str, timeout: float = 3.0) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace") or "{}")


def health_ok(base: str | None = None, timeout: float = 2.0) -> bool:
    base = (base or _base()).rstrip("/")
    for path in ("/health", "/info"):
        try:
            _http_json(f"{base}{path}", timeout=timeout)
            return True
        except Exception:
            continue
    return False


def is_loaded() -> bool:
    return health_ok()


def unload() -> str:
    """Stop moss-tts-server so VRAM frees (Unload button)."""
    global _PROC, _BASE_URL
    msgs: list[str] = []
    if _PROC is not None and _PROC.poll() is None:
        try:
            _PROC.terminate()
            try:
                _PROC.wait(timeout=5)
            except Exception:
                _PROC.kill()
            msgs.append("MOSS GGUF server stopped")
        except Exception as e:  # noqa: BLE001
            msgs.append(f"MOSS GGUF stop: {e}")
        _PROC = None
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", SERVER_EXE],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        msgs.append(f"taskkill {SERVER_EXE}")
    except Exception as e:  # noqa: BLE001
        msgs.append(f"taskkill: {e}")
    _BASE_URL = None
    return " | ".join(msgs) if msgs else "MOSS GGUF not running"


def ensure_server(status_cb: StatusCb = None) -> str:
    global _PROC, _BASE_URL
    port = resolve_port()
    base = f"http://{DEFAULT_HOST}:{port}"
    if health_ok(base):
        _BASE_URL = base
        return base

    def status(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    server = resolve_server_exe()
    model = resolve_model()
    status(f"Starting MOSS GGUF server ({server.name})...")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    env = os.environ.copy()
    env["PATH"] = str(server.parent) + os.pathsep + env.get("PATH", "")
    _PROC = subprocess.Popen(
        [
            str(server),
            "--model",
            str(model),
            "--host",
            DEFAULT_HOST,
            "--port",
            str(port),
            "--n-gpu-layers",
            "-1",
        ],
        cwd=str(server.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    deadline = time.time() + 180
    while time.time() < deadline:
        if _PROC.poll() is not None:
            raise MossGgufUnavailable(
                f"moss-tts-server exited early (code {_PROC.returncode}). "
                "Check model path and CUDA DLLs beside the exe."
            )
        if health_ok(base, timeout=1.5):
            _BASE_URL = base
            status("MOSS GGUF server ready")
            return base
        time.sleep(1.0)
    raise MossGgufUnavailable("Timed out waiting for moss-tts-server /health")


def generate(
    prompt: str,
    seconds: float = 4.0,
    steps: int = 20,
    cfg_scale: float = 4.0,
    negative_prompt: str = "",  # noqa: ARG001
    status_cb: StatusCb = None,
    sigma_shift: float = 5.0,
    seed: int = -1,
) -> Path:
    def status(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    base = ensure_server(status_cb=status_cb)
    status(f"MOSS GGUF generating ({float(seconds):.1f}s, {int(steps)} steps)...")
    body: dict = {
        "text": prompt,
        "seconds": float(seconds),
        "steps": int(steps),
        "cfg_scale": float(cfg_scale),
        "sigma_shift": float(sigma_shift),
    }
    if seed is not None and int(seed) >= 0:
        body["seed"] = int(seed)
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}/sfx",
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "audio/wav,*/*",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            wav_bytes = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:400]
        raise MossGgufUnavailable(f"MOSS GGUF /sfx failed ({e.code}): {detail}") from e
    except Exception as e:  # noqa: BLE001
        raise MossGgufUnavailable(f"MOSS GGUF request failed: {e}") from e

    if not wav_bytes or len(wav_bytes) < 44:
        raise MossGgufUnavailable("MOSS GGUF returned empty/invalid WAV")

    fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="sfxdesk_gguf_")
    os.close(fd)
    path = Path(tmp)
    path.write_bytes(wav_bytes)
    status(f"MOSS GGUF done ({len(wav_bytes)} bytes)")
    return path
