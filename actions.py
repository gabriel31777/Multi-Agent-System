"""Action factories used by agents.

Group number: 22
Creation date: 2026-03-18
Members: 
    - Gabriel	Anjos Moura
    - Vinícius	da Mata e Mota
    - Nicholas	Oliveira Rodrigues Bragança
"""

from __future__ import annotations


def idle() -> dict:
    return {"type": "idle"}


def move(destination: tuple[int, int]) -> dict:
    return {"type": "move", "destination": destination}


def pick_waste(waste_id: int | None = None) -> dict:
    return {"type": "pick", "waste_id": waste_id}


def transform() -> dict:
    return {"type": "transform"}


def drop() -> dict:
    return {"type": "drop"}


def dispose() -> dict:
    return {"type": "dispose"}
