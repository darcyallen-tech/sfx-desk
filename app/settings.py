"""Persist SFX Desk UI prefs under ~/SFX Desk."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path.home() / "SFX Desk" / "settings.json"

DEFAULTS: dict[str, Any] = {
    "geometry": "340x560",
    "skinny_geometry": "340x320",
    "skinny": False,
    "engine": "SA3 Small-SFX",
    "keep_loaded": True,
    "always_on_top": True,
    "auto_send": False,
    "moss_force_enable": False,
    "moss_gguf_server": "",
    "moss_gguf_model": "",
    "moss_gguf_port": 8765,
    "duration": 4.0,
    "kind": "whoosh",
    "texture": "airy",
    "space": "dry",
    "mic": "natural",
    "speed": "fast",
    "intensity": "medium",
    "extra": "",
    "prompt_height": 72,
    "category": "all",
    "fav_only": False,
    "check_updates": True,
    "skipped_update": "",
    "last_update_check": "",
}

_ENGINE_ALLOWLIST = ("SA3 Small-SFX", "MOSS v2", "MOSS GGUF (SLOWER)")


def _sanitize_geometry(value: str, fallback: str) -> str:
    try:
        raw = str(value)
        size = raw.split("+")[0]
        w, h = size.lower().split("x", 1)
        wi, hi = int(float(w)), int(float(h))
        if wi < 280 or hi < 250:
            return fallback
        if "+" in raw:
            return f"{wi}x{hi}+" + raw.split("+", 1)[1]
        return f"{wi}x{hi}"
    except Exception:
        return fallback


def load() -> dict[str, Any]:
    data = dict(DEFAULTS)
    try:
        if SETTINGS_PATH.exists():
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update({k: raw[k] for k in DEFAULTS if k in raw})
    except Exception:
        pass
    data["geometry"] = _sanitize_geometry(str(data.get("geometry")), DEFAULTS["geometry"])
    data["skinny_geometry"] = _sanitize_geometry(
        str(data.get("skinny_geometry")), DEFAULTS["skinny_geometry"]
    )
    eng = str(data.get("engine") or DEFAULTS["engine"])
    if eng not in _ENGINE_ALLOWLIST:
        data["engine"] = DEFAULTS["engine"]
    return data


def save(data: dict[str, Any]) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        out = {k: data.get(k, DEFAULTS[k]) for k in DEFAULTS}
        SETTINGS_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    except Exception:
        pass
