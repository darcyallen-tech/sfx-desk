"""MOSS-SoundEffect GGUF via openmoss moss-tts-server (slower, ~12 GB+)."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
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
_LOCK = threading.Lock()
_GEN_LOCK = threading.Lock()
_ERR_LOG = DEFAULT_ROOT / "sfxdesk-server.err.log"


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
        f"{DEFAULT_ROOT}\\\\runtime\\\\{SERVER_EXE}, or set moss_gguf_server / "
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
        f"(ilintar/moss-soundeffect-gguf), place under {DEFAULT_ROOT}\\\\weights\\\\, "
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



def _creationflags_no_window() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _exe_running() -> bool:
    """True if moss-tts-server.exe is in the process list (no console flash)."""
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {SERVER_EXE}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=_creationflags_no_window(),
        )
        out = (r.stdout or "").lower()
        return SERVER_EXE.lower() in out
    except Exception:
        return False


def server_active() -> bool:
    """True if we track a live proc, health responds, or the exe is running."""
    if _PROC is not None and _PROC.poll() is None:
        return True
    try:
        if health_ok(timeout=0.4):
            return True
    except Exception:
        pass
    return _exe_running()


def _kill_servers() -> None:
    global _PROC
    tracked_live = _PROC is not None and _PROC.poll() is None
    if not tracked_live and not _exe_running():
        # Nothing to kill — skip taskkill (avoids CMD flash on every Woosh gen).
        _PROC = None
        return
    if tracked_live:
        try:
            _PROC.terminate()
            try:
                _PROC.wait(timeout=5)
            except Exception:
                _PROC.kill()
        except Exception:
            pass
        _PROC = None
    # Orphan / stubborn process
    if _exe_running():
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", SERVER_EXE],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                creationflags=_creationflags_no_window(),
            )
        except Exception:
            pass



def unload() -> str:
    """Stop moss-tts-server so VRAM frees (Unload button / pre-Woosh)."""
    global _PROC, _BASE_URL
    with _LOCK:
        if not server_active():
            _PROC = None
            _BASE_URL = None
            return "MOSS GGUF server already stopped"
        _kill_servers()
        _BASE_URL = None
    return "MOSS GGUF server stopped"


def ensure_server(status_cb: StatusCb = None, *, force_restart: bool = False) -> str:
    """Start or reuse moss-tts-server. Call only from generate() — never at app startup."""
    global _PROC, _BASE_URL
    port = resolve_port()
    base = f"http://{DEFAULT_HOST}:{port}"

    def status(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    with _LOCK:
        if not force_restart and health_ok(base):
            _BASE_URL = base
            return base

        if force_restart or not health_ok(base, timeout=1.0):
            status("Restarting MOSS GGUF server...")
            _kill_servers()
            time.sleep(1.0)

        server = resolve_server_exe()
        model = resolve_model()
        # Sidecar must sit beside the backbone as <stem>.extras.gguf
        extras = model.with_name(model.name.replace(".gguf", ".extras.gguf"))
        if not extras.is_file():
            raise MossGgufUnavailable(
                f"Missing sidecar {extras.name} next to {model.name}. "
                "Both GGUF files from the HF repo are required."
            )

        status(f"Starting MOSS GGUF server ({server.name})...")
        DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)
        err_f = open(_ERR_LOG, "ab", buffering=0)  # noqa: SIM115
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
            stderr=err_f,
            creationflags=creationflags,
        )
        deadline = time.time() + 180
        while time.time() < deadline:
            if _PROC.poll() is not None:
                raise MossGgufUnavailable(
                    f"moss-tts-server exited early (code {_PROC.returncode}). "
                    f"See {_ERR_LOG}"
                )
            if health_ok(base, timeout=1.5):
                _BASE_URL = base
                status("MOSS GGUF server ready")
                return base
            time.sleep(1.0)
        raise MossGgufUnavailable(
            f"Timed out waiting for moss-tts-server /health. See {_ERR_LOG}"
        )


def _post_sfx(
    base: str,
    prompt: str,
    seconds: float,
    steps: int,
    cfg_scale: float,
    sigma_shift: float,
    seed: int,
) -> bytes:
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
    with urllib.request.urlopen(req, timeout=900) as resp:
        return resp.read()


def generate(
    prompt: str,
    seconds: float = 4.0,
    steps: int = 12,
    cfg_scale: float = 4.0,
    negative_prompt: str = "",  # noqa: ARG001
    status_cb: StatusCb = None,
    sigma_shift: float = 5.0,
    seed: int = -1,
) -> Path:
    def status(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    if not _GEN_LOCK.acquire(blocking=False):
        raise MossGgufUnavailable(
            "MOSS GGUF is already generating. Wait for it to finish "
            "(decode often takes 1–2+ minutes)."
        )
    try:
        base = ensure_server(status_cb=status_cb)
        status(
            f"MOSS GGUF generating ({float(seconds):.1f}s, {int(steps)} steps) — "
            "decode is slow, leave it alone..."
        )
        try:
            wav_bytes = _post_sfx(
                base, prompt, seconds, steps, cfg_scale, sigma_shift, seed
            )
        except (ConnectionResetError, urllib.error.URLError, TimeoutError) as e:
            # Server often dies mid-decode if VRAM is contested or a second
            # /sfx hits the single-threaded process.
            status("MOSS GGUF server dropped — restarting once and retrying...")
            base = ensure_server(status_cb=status_cb, force_restart=True)
            try:
                wav_bytes = _post_sfx(
                    base, prompt, seconds, steps, cfg_scale, sigma_shift, seed
                )
            except Exception as e2:  # noqa: BLE001
                raise MossGgufUnavailable(
                    f"MOSS GGUF request failed after restart: {e2}. "
                    "Unload SA3/MOSS first (free VRAM), use fewer steps, "
                    f"and check {_ERR_LOG}. First error: {e}"
                ) from e2
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:400]
            raise MossGgufUnavailable(
                f"MOSS GGUF /sfx failed ({e.code}): {detail}"
            ) from e

        if not wav_bytes or len(wav_bytes) < 44:
            raise MossGgufUnavailable("MOSS GGUF returned empty/invalid WAV")

        fd, tmp = tempfile.mkstemp(suffix=".wav", prefix="sfxdesk_gguf_")
        os.close(fd)
        path = Path(tmp)
        path.write_bytes(wav_bytes)
        status(f"MOSS GGUF done ({len(wav_bytes)} bytes)")
        return path
    finally:
        _GEN_LOCK.release()
