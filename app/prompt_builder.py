"""Assemble SFX prompts from builder axes.

MOSS v2: free-form sensory captions (EN/ZH). Duration is a pipeline param.
SA3 Small-SFX: source + action + production; optional TrackType: SFX.
"""
from __future__ import annotations

TYPES = [
    "whoosh",
    "swoosh",
    "riser",
    "faller",
    "impact",
    "hit",
    "thud",
    "boom",
    "click",
    "scrape",
    "rumble",
    "ambience",
    "drone",
    "reverse",
    "cloth",
    "water",
    "fire",
    "wind",
    "footsteps",
    "door",
    "glitch",
    "ui",
]
TEXTURES = [
    "airy",
    "soft",
    "sharp",
    "metallic",
    "organic",
    "wooden",
    "glass",
    "digital",
    "distorted",
    "cinematic",
    "gritty",
    "wet",
    "brittle",
    "rubbery",
    "analog",
    "synthetic",
]
# Acoustic environment only (mic distance is separate)
SPACES = [
    "dry",
    "roomy",
    "hall",
    "outdoor",
    "studio",
    "cave",
    "street",
    "bathroom",
]
MICS = ["close", "natural", "distant"]
SPEEDS = ["slow", "medium", "fast", "instant"]
INTENSITIES = ["soft", "medium", "hard", "brutal"]

DEFAULT_NEGATIVE = "speech, dialogue, music, melody, song, singing, hiss, static"

SPACE_PHRASE = {
    "dry": "dry close-up room, little reverb",
    "roomy": "in a small room with light reflections",
    "hall": "in a large hall with long reverb",
    "outdoor": "outdoors in open air",
    "studio": "in a treated studio space",
    "cave": "in a resonant cave-like space",
    "street": "on an open street with city ambience",
    "bathroom": "in a tiled bathroom with short bright reflections",
}
MIC_PHRASE = {
    "close": "close microphone perspective",
    "natural": "natural microphone distance",
    "distant": "distant microphone, muffled and far",
}
SPEED_PHRASE = {
    "slow": "slow and drawn out",
    "medium": "steady medium pace",
    "fast": "fast and abrupt",
    "instant": "instant transient hit",
}
INTENSITY_PHRASE = {
    "soft": "gentle and understated",
    "medium": "balanced intensity",
    "hard": "punchy and forceful",
    "brutal": "heavy, aggressive, high impact",
}

# SA3 production / mic language
SPACE_SA3 = {
    "dry": "dry room, little reverb",
    "roomy": "small room reflections",
    "hall": "large hall reverb",
    "outdoor": "outdoor open air, ambient bleed",
    "studio": "treated studio room",
    "cave": "cave-like long reflections",
    "street": "street exterior ambience",
    "bathroom": "tiled room, short bright reverb",
}
MIC_SA3 = {
    "close": "close-miked",
    "natural": "natural mic",
    "distant": "distant mic, muffled and far",
}
SPEED_SA3 = {
    "slow": "slow attack with long decay",
    "medium": "measured pacing and natural decay",
    "fast": "fast attack with abrupt decay",
    "instant": "instant attack with short decay",
}
INTENSITY_SA3 = {
    "soft": "soft low-energy",
    "medium": "medium-weight",
    "hard": "hard high-energy",
    "brutal": "brutal heavy-impact",
}


def migrate_space_mic(space: str, mic: str | None = None) -> tuple[str, str]:
    """Map legacy space=distant (mic distance) into space + mic."""
    space = (space or "dry").strip().lower()
    mic = (mic or "natural").strip().lower()
    if space == "distant":
        # Old axis used distant as mic distance
        return "dry", "distant"
    if space not in SPACES:
        space = "dry"
    if mic not in MICS:
        mic = "natural"
    return space, mic


def build_prompt(
    kind: str,
    texture: str,
    space: str,
    speed: str,
    extra: str = "",
    engine: str = "moss",
    mic: str = "natural",
    intensity: str = "medium",
) -> str:
    kind = (kind or "whoosh").strip().lower()
    texture = (texture or "airy").strip().lower()
    speed = (speed or "medium").strip().lower()
    intensity = (intensity or "medium").strip().lower()
    extra = (extra or "").strip()
    engine = (engine or "moss").strip().lower()
    space, mic = migrate_space_mic(space, mic)

    if engine == "sa3":
        space_bit = SPACE_SA3.get(space, space)
        mic_bit = MIC_SA3.get(mic, mic)
        speed_bit = SPEED_SA3.get(speed, speed)
        intensity_bit = INTENSITY_SA3.get(intensity, intensity)
        prompt = (
            f"TrackType: SFX, a {intensity_bit} {texture} {kind}, {speed_bit}, "
            f"{space_bit}, {mic_bit}, clear foley one-shot, no music, no speech"
        )
        if extra:
            prompt = f"{prompt}, {extra}"
        return prompt

    space_bit = SPACE_PHRASE.get(space, space)
    mic_bit = MIC_PHRASE.get(mic, mic)
    speed_bit = SPEED_PHRASE.get(speed, speed)
    intensity_bit = INTENSITY_PHRASE.get(intensity, intensity)
    # Article agrees with the word that follows it (intensity phrase), not kind.
    # Fixes "an punchy…" when kind is vowel-initial (impact/ambience) but intensity is not.
    lead = (intensity_bit or texture or kind).strip().split()[0].lower()
    article = "an" if lead[:1] in "aeiou" else "a"
    prompt = (
        f"{article} {intensity_bit} {texture} {kind}, {speed_bit}, {space_bit}, "
        f"{mic_bit}, clear sound design, no speech"
    )
    if extra:
        prompt = f"{prompt}, {extra}"
    return prompt


def default_negative_prompt() -> str:
    return DEFAULT_NEGATIVE
