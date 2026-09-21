"""Send WAV into DaVinci Resolve via External Scripting (not MagicScript)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_resolve_modules() -> None:
    api = os.environ.get(
        "RESOLVE_SCRIPT_API",
        r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting",
    )
    api = os.path.expandvars(api)
    modules = os.path.join(api, "Modules")
    if modules not in sys.path and os.path.isdir(modules):
        sys.path.append(modules)
    # Common absolute fallbacks
    for c in (
        r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules",
        r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Scripting\Modules",
    ):
        if c not in sys.path and os.path.isdir(c):
            sys.path.append(c)


def get_resolve():
    _ensure_resolve_modules()
    try:
        import DaVinciResolveScript as dvr
    except Exception as e:
        raise RuntimeError(
            "DaVinciResolveScript not found. Set External scripting to Local in "
            "Resolve Preferences > System > General, and ensure Scripting\\Modules is on PYTHONPATH."
        ) from e
    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        raise RuntimeError(
            "Resolve not reachable — is Resolve open and External scripting set to Local?"
        )
    return resolve


def project_open(resolve=None):
    resolve = resolve or get_resolve()
    return resolve.GetProjectManager().GetCurrentProject()


def send_wav_to_resolve(
    wav_path: str | Path,
    bin_name: str = "SFX Desk",
    place_on_timeline: bool = False,
    audio_track: int = 2,
) -> str:
    """Import one WAV into the Media Pool bin (bin only by default)."""
    return send_wavs_to_resolve(
        [wav_path],
        bin_name=bin_name,
        place_on_timeline=place_on_timeline,
        audio_track=audio_track,
    )


def send_wavs_to_resolve(
    wav_paths: list[str | Path],
    bin_name: str = "SFX Desk",
    place_on_timeline: bool = False,
    audio_track: int = 2,
) -> str:
    """Import one or more WAVs into Media Pool bin; optionally append to timeline."""
    seen: set[str] = set()
    paths: list[Path] = []
    for p in wav_paths:
        path = Path(p).resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    if not paths:
        raise ValueError("No WAV paths to import.")

    resolve = get_resolve()
    project = project_open(resolve)
    if not project:
        raise RuntimeError("No Resolve project is open.")

    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    folders = {f.GetName(): f for f in (root.GetSubFolderList() or [])}
    folder = folders.get(bin_name)
    if not folder:
        folder = media_pool.AddSubFolder(root, bin_name) or root
    media_pool.SetCurrentFolder(folder)

    items = media_pool.ImportMedia([str(p) for p in paths]) or []
    if not items:
        raise RuntimeError(f"ImportMedia failed: {[p.name for p in paths]}")
    if len(items) != len(paths):
        raise RuntimeError(
            f"ImportMedia returned {len(items)} items for {len(paths)} unique paths "
            f"(possible filename collision on disk): {[p.name for p in paths]}"
        )

    names = ", ".join(p.name for p in paths)
    if len(paths) == 1:
        msg = f"Imported to bin '{bin_name}': {paths[0].name}"
    else:
        msg = f"Imported {len(paths)} clips to bin '{bin_name}': {names}"

    if place_on_timeline:
        timeline = project.GetCurrentTimeline()
        if not timeline:
            msg += " (no timeline — Media Pool only)"
            return msg
        infos = [
            {
                "mediaPoolItem": mpi,
                "mediaType": 2,  # audio
                "trackIndex": int(audio_track),
            }
            for mpi in items
        ]
        got = media_pool.AppendToTimeline(infos)
        if not got:
            got = media_pool.AppendToTimeline(list(items))
        if got:
            msg += f" (appended to A{audio_track} / timeline)"
        else:
            msg += " (Media Pool only — append failed)"
    return msg

