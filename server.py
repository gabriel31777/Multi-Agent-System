"""Solara visualization for the robot mission.

Group number: 22
Creation date: 2026-03-18
Members: 
    - Gabriel	Anjos Moura
    - Vinícius	da Mata e Mota
    - Nicholas	Oliveira Rodrigues Bragança
"""

from __future__ import annotations

import solara
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from mesa.visualization import SolaraViz, make_plot_component, make_space_component
from mesa.visualization.utils import update_counter

# Handle both package imports and direct execution
try:
    from .config import DEFAULT_PARAMS, ROBOT_COLORS, WASTE_COLORS
    from .model import RobotMissionModel
    from .objects import RadioactivityCell, Waste, WasteDisposalZone
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from config import DEFAULT_PARAMS, ROBOT_COLORS, WASTE_COLORS
    from model import RobotMissionModel
    from objects import RadioactivityCell, Waste, WasteDisposalZone


def agent_portrayal(agent):
    if isinstance(agent, RadioactivityCell):
        return {"color": "#ced4da", "size": 8, "alpha": 0.15}
    if isinstance(agent, WasteDisposalZone):
        return {"color": "#495057", "size": 90, "marker": "s"}
    if isinstance(agent, Waste):
        return {"color": WASTE_COLORS[agent.waste_type], "size": 28, "marker": "D"}
    if hasattr(agent, "robot_type"):
        return {"color": ROBOT_COLORS[agent.robot_type], "size": 70, "marker": "o"}
    return {"color": "black", "size": 20}

@solara.component
def GridZones(model):
    update_counter.get()

    fig = Figure(figsize=(8, 5))
    ax = fig.subplots()

    width = model.grid.width
    height = model.grid.height

    # Desenha o fundo colorido de cada célula
    for x in range(width):
        for y in range(height):
            zone_color = model.get_zone_color((x, y))

            rect = Rectangle(
                (x - 0.5, y - 0.5),   # canto inferior esquerdo
                1,                    # largura da célula
                1,                    # altura da célula
                facecolor=zone_color,
                edgecolor="gray",
                linewidth=1,
                linestyle=":",
                alpha=0.35
            )
            ax.add_patch(rect)

    # Desenha os agentes por cima
    for agent in model.agents:
        pos = getattr(agent, "pos", None)
        if pos is None:
            continue
        portrayal = agent_portrayal(agent)
        x, y = pos

        ax.scatter(
            x, y,
            s=portrayal.get("size", 80),
            c=portrayal.get("color", "blue"),
            marker=portrayal.get("marker", "o"),
            edgecolors="black",
            linewidths=0.8,
            zorder=10,
        )

    ax.set_xlim(-0.5, width - 0.5)
    ax.set_ylim(-0.5, height - 0.5)
    ax.set_xticks(range(width))
    ax.set_yticks(range(height))
    ax.set_aspect("equal")

    # Grid pontilhado
    ax.grid(True, linestyle=":", color="gray", alpha=0.8)

    solara.FigureMatplotlib(fig)

@solara.component
def WastePlot(model):
    update_counter.get()

    df = model.datacollector.get_model_vars_dataframe()

    fig = Figure(figsize=(8, 5))
    ax = fig.subplots()

    if not df.empty:
        if "Green waste" in df.columns:
            ax.plot(df.index, df["Green waste"], label="Green waste", color="green")
        if "Yellow waste" in df.columns:
            ax.plot(df.index, df["Yellow waste"], label="Yellow waste", color="gold")
        if "Red waste" in df.columns:
            ax.plot(df.index, df["Red waste"], label="Red waste", color="red")
        if "Disposed waste" in df.columns:
            ax.plot(df.index, df["Disposed waste"], label="Disposed waste", color="black")

    ax.set_title("Waste evolution")
    ax.set_xlabel("Step")
    ax.set_ylabel("Quantity")
    ax.legend()
    ax.grid(True, alpha=0.3)

    solara.FigureMatplotlib(fig)

@solara.component

def MissionHistogram(model):
    update_counter.get()
    fig = Figure()
    ax = fig.subplots()
    cargo_values = [len(robot.carrying) for robot in model.robot_agents()]
    ax.hist(cargo_values, bins=[-0.5, 0.5, 1.5, 2.5])
    ax.set_xlabel("Cargo carried by robots")
    ax.set_ylabel("Number of robots")
    solara.FigureMatplotlib(fig)


model_params = {
    "width": {
        "type": "SliderInt",
        "value": DEFAULT_PARAMS["width"],
        "label": "Grid width",
        "min": 10,
        "max": 50,
        "step": 1,
    },
    "height": {
        "type": "SliderInt",
        "value": DEFAULT_PARAMS["height"],
        "label": "Grid height",
        "min": 10,
        "max": 50,
        "step": 1,
    },
    "n_green_robots": {
        "type": "SliderInt",
        "value": DEFAULT_PARAMS["n_green_robots"],
        "label": "Green robots",
        "min": 1,
        "max": 10,
        "step": 1,
    },
    "n_yellow_robots": {
        "type": "SliderInt",
        "value": DEFAULT_PARAMS["n_yellow_robots"],
        "label": "Yellow robots",
        "min": 1,
        "max": 10,
        "step": 1,
    },
    "n_red_robots": {
        "type": "SliderInt",
        "value": DEFAULT_PARAMS["n_red_robots"],
        "label": "Red robots",
        "min": 1,
        "max": 10,
        "step": 1,
    },
    "initial_green_waste": {
        "type": "SliderInt",
        "value": DEFAULT_PARAMS["initial_green_waste"],
        "label": "Initial green waste",
        "min": 6,
        "max": 60,
        "step": 1,
    },
    "max_steps": DEFAULT_PARAMS["max_steps"],
}

model = RobotMissionModel()
SpaceGraph = GridZones

page = SolaraViz(
    model,
    components=[SpaceGraph, WastePlot, MissionHistogram],
    model_params=model_params,
    name="Robot Mission MAS 2026",
)

page
