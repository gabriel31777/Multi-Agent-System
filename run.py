"""Simple launcher for the robot mission.

Group number: 22
Creation date: 2026-03-18
Members: 
    - Gabriel	Anjos Moura
    - Vinícius	da Mata e Mota
    - Nicholas	Oliveira Rodrigues Bragança
"""

from __future__ import annotations

from .model import RobotMissionModel


if __name__ == "__main__":
    model = RobotMissionModel()
    while model.running:
        model.step()
    print("Simulation finished")
    print(model.summary())
