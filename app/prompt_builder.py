"""Assemble SFX prompts from builder axes.

MOSS v2: free-form sensory captions (EN/ZH). Duration is a pipeline param.
SA3 Small-SFX: source + action + production; optional TrackType: SFX.
"""
from __future__ import annotations

TYPES = [
    "whoosh", "swoosh", "riser", "faller", "impact", "hit",
    "click", "scrape", "rumble", "ambience", "drone", "reverse",
]
TEXTURES = [
    "airy", "soft", "sharp", "metallic", "organic", "wooden",
    "glass", "digital", "distorted", "cinematic",
]
SPACES = ["dry", "roomy", "hall", "outdoor", "distant"]
SPEEDS = ["slow", "medium", "fast"]

DEFAULT_NEGATIVE = "speech, dialogue, music, melody, song, singing, hiss, static"

SPACE_PHRASE = {
    "dry": "dry close-up, little reverb",
    "roomy": "in a small room with light reflections",
    "hall": "in a large hall with long reverb",
    "outdoor": "outdoors in open air",
    "distant": "heard from a distance, muffled and far",
}
SPEED_PHRASE = {
    "slow": "slow and drawn out",
    "medium": "steady medium pace",
    "fast": "fast and abrupt",
}

# SA3 production / mic language
SPACE_SA3 = {
    "dry": "close-miked, dry room, little reverb",
    "roomy": "small room reflections, natural mic",
    "hall": "large hall reverb, distant mic",
    "outdoor": "outdoor open air, ambient bleed",
    "distant": "distant perspective, muffled and far",
}
SPEED_SA3 = {
    "slow": "slow attack with long decay",
    "medium": "measured pacing and natural decay",
    "fast": "fast attack with abrupt decay",
}


def build_prompt(
    kind: str,
    texture: str,
    space: str,
    speed: str,
    extra: str = "",
    engine: str = "moss",
) -> str:
    kind = (kind or "whoosh").strip().lower()
    texture = (texture or "airy").strip().lower()
    space = (space or "dry").strip().lower()
    speed = (speed or "medium").strip().lower()
    extra = (extra or "").strip()
    engine = (engine or "moss").strip().lower()

    if engine == "sa3":
        # Official SA3 SFX recipe: source + action + production; TrackType:SFX helps
        space_bit = SPACE_SA3.get(space, space)
        speed_bit = SPEED_SA3.get(speed, speed)
        prompt = (
            f"TrackType: SFX, a {texture} {kind}, {speed_bit}, {space_bit}, "
            f"clear foley one-shot, no music, no speech"
        )
        if extra:
            prompt = f"{prompt}, {extra}"
        return prompt

    article = "an" if kind[:1] in "aeiou" else "a"
    space_bit = SPACE_PHRASE.get(space, space)
    speed_bit = SPEED_PHRASE.get(speed, speed)
    prompt = (
        f"{article} {texture} {kind}, {speed_bit}, {space_bit}, "
        f"clear sound design, no speech"
    )
    if extra:
        prompt = f"{prompt}, {extra}"
    return prompt


def default_negative_prompt() -> str:
    return DEFAULT_NEGATIVE
