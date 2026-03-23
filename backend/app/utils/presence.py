from __future__ import annotations

from uuid import uuid4

PALETTE = [
    "#ff6b35",
    "#2a9d8f",
    "#1d3557",
    "#e76f51",
    "#457b9d",
    "#6d597a",
    "#8ab17d",
    "#e9c46a",
]

ADJECTIVES = [
    "swift",
    "bold",
    "steady",
    "curious",
    "tidy",
    "calm",
    "sharp",
    "quiet",
]

ANIMALS = [
    "otter",
    "fox",
    "falcon",
    "lynx",
    "orca",
    "panda",
    "heron",
    "badger",
]


def generate_color(seed: str) -> str:
    return PALETTE[abs(hash(seed)) % len(PALETTE)]


def generate_guest_name() -> str:
    token = uuid4().hex
    adjective = ADJECTIVES[int(token[:2], 16) % len(ADJECTIVES)]
    animal = ANIMALS[int(token[2:4], 16) % len(ANIMALS)]
    return f"{adjective}-{animal}"
