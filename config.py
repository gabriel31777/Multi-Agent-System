"""Configuration constants for the robot mission project.

Group number: 22
Creation date: 2026-03-18
Members: 
    - Gabriel	Anjos Moura
    - Vinícius	da Mata e Mota
    - Nicholas	Oliveira Rodrigues Bragança
"""

DEFAULT_PARAMS = {
    "width": 15,
    "height": 10,
    "n_green_robots": 4,
    "n_yellow_robots": 3,
    "n_red_robots": 2,
    "initial_green_waste": 24,
    "max_steps": 300,
}

ZONE_COLORS = {
    "z1": "#d9fdd3",
    "z2": "#fff3bf",
    "z3": "#ffd6d6",
}

RADIOACTIVITY_BOUNDS = {
    "z1": (0.00, 0.33),
    "z2": (0.33, 0.66),
    "z3": (0.66, 1.00),
}

ROBOT_COLORS = {
    "green": "#2f9e44",
    "yellow": "#f59f00",
    "red": "#e03131",
}

WASTE_COLORS = {
    "green": "#40c057",
    "yellow": "#fcc419",
    "red": "#fa5252",
}
