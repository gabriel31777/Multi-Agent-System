"""Passive objects for the robot mission.

Group number: 22
Creation date: 2026-03-18
Members: 
    - Gabriel	Anjos Moura
    - Vinícius	da Mata e Mota
    - Nicholas	Oliveira Rodrigues Bragança
"""

from __future__ import annotations

from mesa import Agent


class RadioactivityCell(Agent):
    def __init__(self, model, zone: str, level: float):
        super().__init__(model)
        self.zone = zone
        self.level = level

    def step(self):
        return None


class WasteDisposalZone(Agent):
    def __init__(self, model, zone: str = "z3"):
        super().__init__(model)
        self.zone = zone

    def step(self):
        return None


class Waste(Agent):
    def __init__(self, model, waste_type: str):
        super().__init__(model)
        self.waste_type = waste_type
        self.orphan = False

    def step(self):
        return None
