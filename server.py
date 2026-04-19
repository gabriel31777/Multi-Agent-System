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
from mesa.visualization import SolaraViz
from mesa.visualization.utils import update_counter

show_green_lines = solara.reactive(True)
show_yellow_lines = solara.reactive(True)
show_red_lines = solara.reactive(True)
enable_communication_ui = solara.reactive(True)
enable_propose_messages_ui = solara.reactive(True)

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
        robot_color = ROBOT_COLORS[agent.robot_type]
        carrying = getattr(agent, "carrying", [])

        if carrying:
            carried_item = carrying[0]
            carried_type = getattr(carried_item, "waste_type", None)
            carried_color = WASTE_COLORS.get(carried_type, robot_color)

            return {
                "color": carried_color,
                "size": 120,
                "marker": "H",
                "edgecolors": robot_color,
                "linewidths": 2.2,
            }

        return {
            "color": robot_color,
            "size": 70,
            "marker": "o",
            "edgecolors": "black",
            "linewidths": 0.8,
        }
    return {"color": "black", "size": 20}


# MetricsSummary component
@solara.component
def MetricsSummary(model):
    update_counter.get()

    current_step = getattr(model, "steps", 0)
    remaining_waste = model.count_remaining_waste()
    disposed_waste = model.disposed_waste
    total_distance = model.total_distance
    efficiency = model.efficiency()

    with solara.Column():
        with solara.Columns([1, 1]):
            with solara.Card("Remaining waste"):
                solara.Markdown(f"## {remaining_waste}")
            with solara.Card("Efficiency"):
                #solara.Text("Disposed waste per unit of travelled distance")
                solara.Markdown(f"## {efficiency:.3f}")

        with solara.Columns([1, 1]):
            with solara.Card("Disposed waste"):
                solara.Markdown(f"## {disposed_waste}")

            with solara.Card("Total distance"):
                solara.Markdown(f"## {total_distance}")

@solara.component
def VisualizationControls(model):
    # match UI toggle with model default
    if getattr(model, "steps", 0) == 0:
        comm_default = bool(getattr(model, "enable_communication", True))
        if enable_communication_ui.value != comm_default:
            enable_communication_ui.value = comm_default
        model_default = bool(getattr(model, "enable_propose_messages", True))
        if enable_propose_messages_ui.value != model_default:
            enable_propose_messages_ui.value = model_default

    model.enable_communication = bool(enable_communication_ui.value)
    model.enable_propose_messages = bool(enable_propose_messages_ui.value)

    message_service = getattr(model, "message_service", None)
    if message_service is not None:
        if hasattr(message_service, "set_drop_all_messages"):
            message_service.set_drop_all_messages(not enable_communication_ui.value)
        if hasattr(message_service, "set_drop_propose_messages"):
            message_service.set_drop_propose_messages(
                (not enable_communication_ui.value) or (not enable_propose_messages_ui.value)
            )

    with solara.Sidebar():
        with solara.Card("Trajectory Visualization", margin=0, elevation=0):
            solara.Checkbox(label="Green Trajectories", value=show_green_lines)
            solara.Checkbox(label="Yellow Trajectories", value=show_yellow_lines)
            solara.Checkbox(label="Red Trajectories", value=show_red_lines)
        with solara.Card("Communication", margin=0, elevation=0):
            solara.Checkbox(label="Enable communication", value=enable_communication_ui)
            solara.Checkbox(label="Enable PROPOSE messages", value=enable_propose_messages_ui)
            

@solara.component
def GridZones(model):
    update_counter.get()

    fig = Figure(figsize=(8, 5))
    ax = fig.subplots()

    width = model.grid.width
    height = model.grid.height

    # draw the colored background for each cell
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

    # draw agents on top
    for agent in model.agents:
        pos = getattr(agent, "pos", None)
        if pos is None:
            continue
            
        # Draw robot internal paths
        rtype = getattr(agent, "robot_type", None)
        
        do_show = False
        if rtype == "green" and show_green_lines.value:
            do_show = True
        elif rtype == "yellow" and show_yellow_lines.value:
            do_show = True
        elif rtype == "red" and show_red_lines.value:
            do_show = True
            
        if do_show:
            knowledge = getattr(agent, "knowledge", {})
            x, y = pos
            
            # Memory of wastes
            visible = knowledge.get("visible_waste_positions", {}).get(rtype, [])
            orphans = knowledge.get("orphan_waste_positions", {}).get(rtype, [])
            target_wastes = visible + orphans
            
            if rtype == "green":
                mem_color = "#2e7d32"
            elif rtype == "yellow":
                mem_color = "#d4a919"
            else:
                mem_color = "#c62828"
                
            for mx, my in target_wastes:
                ax.plot([x, mx], [y, my], color=mem_color, linestyle=":", linewidth=0.8, alpha=0.5, zorder=5)

            # Planned Trajectory
            current_goal = knowledge.get("current_goal")
            goal_type = knowledge.get("goal_type")
            if current_goal:
                gx, gy = current_goal
                if goal_type == "patrol":
                    ax.plot([x, gx], [y, gy], color="blue", linestyle="--", linewidth=1.2, alpha=0.6, zorder=6)
                else:
                    ax.plot([x, gx], [y, gy], color="magenta", linestyle="-", linewidth=1.5, alpha=0.8, zorder=6)

        portrayal = agent_portrayal(agent)
        x, y = pos

        ax.scatter(
            x, y,
            s=portrayal.get("size", 80),
            c=portrayal.get("color", "blue"),
            marker=portrayal.get("marker", "o"),
            edgecolors=portrayal.get("edgecolors", "black"),
            linewidths=portrayal.get("linewidths", 0.8),
            zorder=10,
        )

    ax.set_xlim(-0.5, width - 0.5)
    ax.set_ylim(-0.5, height - 0.5)
    ax.set_xticks(range(width))
    ax.set_yticks(range(height))
    ax.set_aspect("equal")

    # dotted grid
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
def DistancePlot(model):
    update_counter.get()

    df = model.datacollector.get_model_vars_dataframe()

    fig = Figure(figsize=(8, 5))
    ax = fig.subplots()

    if not df.empty and "Total distance" in df.columns:
        ax.plot(df.index, df["Total distance"], label="Total distance", color="black")

    ax.set_title("Total distance over time")
    ax.set_xlabel("Step")
    ax.set_ylabel("Distance")
    ax.legend()
    ax.grid(True, alpha=0.3)

    solara.FigureMatplotlib(fig)


@solara.component
def EfficiencyPlot(model):
    update_counter.get()

    df = model.datacollector.get_model_vars_dataframe()

    fig = Figure(figsize=(8, 5))
    ax = fig.subplots()

    if not df.empty and "Efficiency" in df.columns:
        ax.plot(df.index, df["Efficiency"], label="Efficiency", color="#1f77b4")

    ax.set_title("Efficiency over time")
    ax.set_xlabel("Step")
    ax.set_ylabel("Disposed waste / distance")
    ax.legend()
    ax.grid(True, alpha=0.3)

    solara.FigureMatplotlib(fig)


@solara.component
def RobotVisitsHeatmap(model):
    update_counter.get()

    fig = Figure(figsize=(8, 5))
    ax = fig.subplots()

    visit_counts = getattr(
        model,
        "visit_counts",
        [[0 for _ in range(model.grid.width)] for _ in range(model.grid.height)],
    )
    heatmap = ax.imshow(visit_counts, origin="lower", aspect="auto", cmap="Blues")
    ax.set_title("Robot visits heatmap")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    fig.colorbar(heatmap, ax=ax, label="Visits")

    solara.FigureMatplotlib(fig)


@solara.component
def CommunicationMetrics(model):
    update_counter.get()

    robots = model.robot_agents()
    history = []
    message_service = getattr(model, "message_service", None)
    if message_service is not None and hasattr(message_service, "get_message_history"):
        history = message_service.get_message_history()

    active_handoffs = 0
    pending_handoffs = 0
    peer_claims = 0
    for robot in robots:
        knowledge = getattr(robot, "knowledge", {})
        if isinstance(knowledge.get("active_handoff"), dict):
            active_handoffs += 1
        pending_handoffs += len(knowledge.get("pending_handoffs", {}))
        peer_claims += len(knowledge.get("peer_target_claims", {}))

    with solara.Column():
        with solara.Columns([1, 1]):
            with solara.Card("Messages logged"):
                solara.Markdown(f"## {len(history)}")
            with solara.Card("Active handoffs"):
                solara.Markdown(f"## {active_handoffs}")

        with solara.Columns([1, 1]):
            with solara.Card("Pending handoffs"):
                solara.Markdown(f"## {pending_handoffs}")

            with solara.Card("Target claims tracked"):
                solara.Markdown(f"## {peer_claims}")


def _fmt_pos(pos) -> str:
    if isinstance(pos, (tuple, list)) and len(pos) == 2:
        return f"({pos[0]},{pos[1]})"
    return "-"


def _fmt_eta(eta) -> str:
    if eta is None:
        return "-"
    return str(eta)


def _md_escape(value) -> str:
    text = str(value)
    return text.replace("|", "\\|")


def _truncate(value, max_len: int = 70) -> str:
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "..."


@solara.component
def CommunicationMessages(model):
    update_counter.get()

    history = []
    message_service = getattr(model, "message_service", None)
    if message_service is not None and hasattr(message_service, "get_message_history"):
        history = message_service.get_message_history(limit=10)

    with solara.Card("Communication Messages (last 10)", margin=0):
        if not history:
            solara.Text("No messages yet.")
            return

        lines = [
            "| idx | step | from | to | kind | perf | pos | eta |",
            "|---:|---:|---|---|---|---|---|---:|",
        ]
        for msg in reversed(history):
            idx = str(msg.get("index", "-"))
            step = str(msg.get("step", "-"))
            source = str(msg.get("from", "-"))
            target = str(msg.get("to", "-"))
            kind = str(msg.get("kind") or "-")
            perf = str(msg.get("performative") or "-")
            pos = _fmt_pos(msg.get("pos"))
            eta = _fmt_eta(msg.get("eta"))
            lines.append(
                f"| {_md_escape(idx)} | {_md_escape(step)} | {_md_escape(source)} | "
                f"{_md_escape(target)} | {_md_escape(kind)} | {_md_escape(perf)} | "
                f"{_md_escape(pos)} | {_md_escape(eta)} |"
            )
        solara.Markdown("\n".join(lines))


def _robot_name(robot) -> str:
    if hasattr(robot, "get_name"):
        return robot.get_name()
    return f"{getattr(robot, 'robot_type', 'robot')}_{robot.unique_id}"


def _fmt_handoff_targets_compact(handoff_targets: list) -> str:
    if not handoff_targets:
        return "0"
    first = _fmt_pos(handoff_targets[0])
    total = len(handoff_targets)
    if total == 1:
        return f"1:{first}"
    return f"{total}:{first}+"


@solara.component
def CommunicationState(model):
    update_counter.get()
    robots = sorted(model.robot_agents(), key=lambda r: _robot_name(r))

    with solara.Card("Targets and Handoffs by Robot", margin=0):
        if not robots:
            solara.Text("No robots available.")
            return

        lines = [
            "| robot | pos | goal(type) | active_handoff | handoff_targets |",
            "|---|---|---|---|---|",
        ]
        for robot in robots:
            knowledge = getattr(robot, "knowledge", {})
            goal = _fmt_pos(knowledge.get("current_goal"))
            goal_type = knowledge.get("goal_type", "-")
            active_handoff = knowledge.get("active_handoff")
            active_pos = _fmt_pos(active_handoff.get("pos")) if isinstance(active_handoff, dict) else "-"
            handoff_targets = knowledge.get("handoff_targets", [])
            handoff_targets_txt = _fmt_handoff_targets_compact(handoff_targets)
            robot_name = _truncate(_robot_name(robot), 18)
            pos_txt = _truncate(_fmt_pos(getattr(robot, "pos", None)), 12)
            goal_txt = _truncate(f"{goal}({goal_type})", 18)
            active_txt = _truncate(active_pos, 12)
            targets_txt = _truncate(handoff_targets_txt, 12)
            lines.append(
                f"| {_md_escape(robot_name)} | {_md_escape(pos_txt)} | {_md_escape(goal_txt)} | "
                f"{_md_escape(active_txt)} | {_md_escape(targets_txt)} |"
            )
        solara.Markdown("\n".join(lines))


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
    "enable_propose_messages": {
        "type": "Checkbox",
        "value": False,
        "label": "Enable PROPOSE messages",
    },
    "enable_communication": {
        "type": "Checkbox",
        "value": True,
        "label": "Enable communication",
    },
    "max_steps": DEFAULT_PARAMS["max_steps"],
}

model = RobotMissionModel()
SpaceGraph = GridZones

page = SolaraViz(
    model,
    components=[
        (GridZones, 0),
        (MetricsSummary, 0),
        (WastePlot, 0),
        (MissionHistogram, 0),
        (VisualizationControls, 0),
        (GridZones, 1),
        (DistancePlot, 1),
        (EfficiencyPlot, 1),
        (RobotVisitsHeatmap, 1),
        (GridZones, 2),
        (CommunicationMetrics, 2),
        (CommunicationMessages, 2),
        (CommunicationState, 2),
    ],
    model_params=model_params,
    name="Robot Mission MAS 2026",
)
