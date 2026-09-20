"""Quiet GitHub Releases update check for SFX Desk (no tokens, no deps)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

OWNER = "darcyallen-tech"
REPO = "sfx-desk"
_API_LATEST = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/latest"


@dataclass
class UpdateInfo:
    tag: str
    html_url: str
    name: Optional[str] = None


def parse_version(s: str) -> tuple[int, int, int]:
    """Parse a version string into (major, minor, patch). Strips a leading 'v'."""
    text = (s or "").strip()
    if text.lower().startswith("v"):
        text = text[1:]
    parts = re.split(r"[^0-9]+", text)
    nums = [int(p) for p in parts if p.isdigit()]
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def is_newer(remote: str, local: str) -> bool:
    """True if remote version is strictly newer than local."""
    try:
        return parse_version(remote) > parse_version(local)
    except Exception:
        return False


def check_for_update(current_version: str, timeout: float = 5) -> Optional[UpdateInfo]:
    """
    Fetch the latest GitHub Release. Returns UpdateInfo if a newer non-draft,
    non-prerelease exists; otherwise None. Never raises; quiet on any error.
    """
    try:
        req = urllib.request.Request(
            _API_LATEST,
            headers={
                "User-Agent": f"SFX-Desk/{current_version}",
                "Accept": "application/vnd.github+json",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        if data.get("draft") or data.get("prerelease"):
            return None
        tag = str(data.get("tag_name") or "").strip()
        if not tag:
            return None
        if not is_newer(tag, current_version):
            return None
        html_url = str(data.get("html_url") or "").strip()
        if not html_url:
            html_url = f"https://github.com/{OWNER}/{REPO}/releases/tag/{tag}"
        name = data.get("name")
        name_s = str(name).strip() if name else None
        return UpdateInfo(tag=tag, html_url=html_url, name=name_s or None)
    except Exception:
        return None
