"""Effects exposed to Home Assistant (app-derived mode groups 0-7 only)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .effect_table import EFFECT_TABLE


@dataclass(frozen=True)
class Effect:
    id: int
    label: str
    group: str
    flashing: bool


def _build() -> tuple[Effect, ...]:
    counts = Counter(label for _, _, label in EFFECT_TABLE)
    out = []
    for group, mid, label in EFFECT_TABLE:
        unique = f"{label} (#{mid})" if counts[label] > 1 else label  # app reuses some labels; ID keeps them distinct
        out.append(Effect(mid, unique, group, "strobe" in label.lower()))
    return tuple(out)


EFFECTS: tuple[Effect, ...] = _build()
_BY_ID = {e.id: e for e in EFFECTS}
_BY_LABEL = {e.label: e for e in EFFECTS}


def effects_for(allow_flashing: bool) -> list[Effect]:
    return [e for e in EFFECTS if allow_flashing or not e.flashing]


def effect_by_id(mode_id: int) -> Effect | None:
    return _BY_ID.get(mode_id)


def effect_by_label(label: str, allow_flashing: bool) -> Effect | None:
    e = _BY_LABEL.get(label)
    if e is None or (e.flashing and not allow_flashing):
        return None
    return e
