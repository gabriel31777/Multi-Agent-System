"""Core Mesa model for the robot mission.

Group number: 22
Creation date: 2026-03-18
Members: 
    - Gabriel	Anjos Moura
    - Vinícius	da Mata e Mota
    - Nicholas	Oliveira Rodrigues Bragança
"""

from __future__ import annotations

from typing import Iterable

from mesa import Model
from mesa.datacollection import DataCollector
from mesa.space import MultiGrid

try:
    from .agents import GreenRobotAgent, RedRobotAgent, YellowRobotAgent
    from .config import DEFAULT_PARAMS, RADIOACTIVITY_BOUNDS
    from .objects import RadioactivityCell, Waste, WasteDisposalZone
except ImportError:
    from agents import GreenRobotAgent, RedRobotAgent, YellowRobotAgent
    from config import DEFAULT_PARAMS, RADIOACTIVITY_BOUNDS
    from objects import RadioactivityCell, Waste, WasteDisposalZone


class RobotMissionModel(Model):
    def __init__(
        self,
        width: int = DEFAULT_PARAMS["width"],
        height: int = DEFAULT_PARAMS["height"],
        n_green_robots: int = DEFAULT_PARAMS["n_green_robots"],
        n_yellow_robots: int = DEFAULT_PARAMS["n_yellow_robots"],
        n_red_robots: int = DEFAULT_PARAMS["n_red_robots"],
        initial_green_waste: int = DEFAULT_PARAMS["initial_green_waste"],
        initial_yellow_waste: int = DEFAULT_PARAMS["initial_yellow_waste"],
        initial_red_waste: int = DEFAULT_PARAMS["initial_red_waste"],
        max_steps: int = DEFAULT_PARAMS["max_steps"],
        seed: int | None = None,
    ):
        super().__init__(seed=seed)
        self.grid = MultiGrid(width, height, torus=False)
        self.width = width
        self.height = height
        self.max_steps = max_steps
        self.running = True
        self.disposed_waste = 0
        self.total_distance = 0
        self.disposal_pos = None
        self.zone_boundaries = self._build_zones()
        self.east_targets = self._build_east_targets()
        self.visit_counts = [[0 for _ in range(self.width)] for _ in range(self.height)]

        self._create_environment()
        self._create_initial_wastes(initial_green_waste, initial_yellow_waste, initial_red_waste)
        self._create_robots(n_green_robots, n_yellow_robots, n_red_robots)
        self._record_robot_visits()
        self.datacollector = self._build_datacollector()
        self.datacollector.collect(self)

    def _build_zones(self) -> dict[str, tuple[int, int]]:
        z1_end = max(0, self.width // 3 - 1)
        z2_end = max(z1_end + 1, (2 * self.width) // 3 - 1)
        return {
            "z1": (0, z1_end),
            "z2": (z1_end + 1, z2_end),
            "z3": (z2_end + 1, self.width - 1),
        }

    def _build_east_targets(self) -> dict[str, tuple[int, int]]:
        return {
            zone: (xmax, self.height // 2)
            for zone, (_, xmax) in self.zone_boundaries.items()
        }

    def zone_for_pos(self, pos: tuple[int, int]) -> str:
        x, _ = pos
        for zone, (xmin, xmax) in self.zone_boundaries.items():
            if xmin <= x <= xmax:
                return zone
        return "z3"

    def _create_environment(self):
        for x in range(self.width):
            for y in range(self.height):
                zone = self.zone_for_pos((x, y))
                low, high = RADIOACTIVITY_BOUNDS[zone]
                cell = RadioactivityCell(self, zone=zone, level=self.random.uniform(low, high))
                self.grid.place_agent(cell, (x, y))

        east_x = self.width - 1
        east_y = self.random.randrange(self.height)
        disposal = WasteDisposalZone(self)
        self.grid.place_agent(disposal, (east_x, east_y))
        self.disposal_pos = (east_x, east_y)

    def _random_pos_in_zone(self, zone: str) -> tuple[int, int]:
        xmin, xmax = self.zone_boundaries[zone]
        return (self.random.randint(xmin, xmax), self.random.randrange(self.height))

    def _create_initial_wastes(self, n_green_waste: int, n_yellow_waste: int, n_red_waste: int):
        for _ in range(n_green_waste):
            waste = Waste(self, waste_type="green")
            self.grid.place_agent(waste, self._random_pos_in_zone("z1"))

        for _ in range(n_yellow_waste):
            waste = Waste(self, waste_type="yellow")
            self.grid.place_agent(waste, self._random_pos_in_zone("z2"))
        
        for _ in range(n_red_waste):
            waste = Waste(self, waste_type="red")
            self.grid.place_agent(waste, self._random_pos_in_zone("z3"))

    def _create_robots(self, n_green: int, n_yellow: int, n_red: int):
        robot_specs = [
            (GreenRobotAgent, n_green, "z1"),
            (YellowRobotAgent, n_yellow, "z1"),
            (RedRobotAgent, n_red, "z2"),
        ]
        for cls, total, start_zone in robot_specs:
            for _ in range(total):
                agent = cls(self)
                self.grid.place_agent(agent, self._random_pos_in_zone(start_zone))

    def _record_visit(self, pos: tuple[int, int] | None):
        if pos is None:
            return
        x, y = pos
        if 0 <= x < self.width and 0 <= y < self.height:
            self.visit_counts[y][x] += 1

    def _record_robot_visits(self):
        for robot in self.robot_agents():
            self._record_visit(getattr(robot, "pos", None))

    def _build_datacollector(self) -> DataCollector:
        return DataCollector(
            model_reporters={
                "Green waste": lambda m: m.count_waste("green"),
                "Yellow waste": lambda m: m.count_waste("yellow"),
                "Red waste": lambda m: m.count_waste("red"),
                "Disposed waste": lambda m: m.disposed_waste,
                "Remaining waste": lambda m: m.count_remaining_waste(),
                "Total distance": lambda m: m.total_distance,
                "Efficiency": lambda m: m.efficiency(),
                "Active robots": lambda m: m.count_robots(),
                "Average cargo": lambda m: m.average_cargo(),
            },
            agent_reporters={
                "Type": lambda a: getattr(a, "robot_type", type(a).__name__),
                "Position": lambda a: getattr(a, "pos", None),
                "Cargo": lambda a: len(getattr(a, "carrying", [])),
            },
        )

    def waste_agents(self) -> list[Waste]:
        return [a for a in self.agents if isinstance(a, Waste) and getattr(a, "pos", None) is not None]

    def robot_agents(self):
        return [a for a in self.agents if hasattr(a, "robot_type")]

    def count_waste(self, waste_type: str) -> int:
        return sum(1 for a in self.waste_agents() if a.waste_type == waste_type)

    def count_robots(self) -> int:
        return len(self.robot_agents())

    def average_cargo(self) -> float:
        robots = self.robot_agents()
        if not robots:
            return 0.0
        return sum(len(r.carrying) for r in robots) / len(robots)

    def count_remaining_waste(self) -> int:
        """
        Counts all waste items that still exist in the system:
        - waste agents currently on the grid
        - waste units currently being carried by robots
        """
        grid_waste = len(self.waste_agents())
        carried_waste = sum(len(robot.carrying) for robot in self.robot_agents())
        return grid_waste + carried_waste

    def efficiency(self) -> float:
        """Disposed waste per unit of travelled distance."""
        if self.total_distance == 0:
            return 0.0
        return self.disposed_waste / self.total_distance

    def _serialize_cell(self, pos: tuple[int, int]) -> dict:
        contents = self.grid.get_cell_list_contents([pos])
        wastes = [a for a in contents if isinstance(a, Waste)]
        radio = next((a for a in contents if isinstance(a, RadioactivityCell)), None)
        disposal = any(isinstance(a, WasteDisposalZone) for a in contents)
        robots = [a.robot_type for a in contents if hasattr(a, "robot_type")]
        return {
            "zone": radio.zone if radio else self.zone_for_pos(pos),
            "radioactivity": getattr(radio, "level", None),
            "robots": robots,
            "wastes": [{"id": w.unique_id, "waste_type": w.waste_type} for w in wastes],
            "disposal": disposal,
        }

    def get_accessible_neighborhood(self, agent) -> list[tuple[int, int]]:
        candidates = self.grid.get_neighborhood(agent.pos, moore=True, include_center=False)
        return [pos for pos in candidates if self.zone_for_pos(pos) in agent.allowed_zones]

    def get_percepts(self, agent) -> dict:
        current_pos = agent.pos
        visible_tiles = {current_pos: self._serialize_cell(current_pos)}
        for pos in self.get_accessible_neighborhood(agent):
            visible_tiles[pos] = self._serialize_cell(pos)

        visible_waste_positions = {"green": [], "yellow": [], "red": []}
        for waste in self.waste_agents():
            if self.zone_for_pos(waste.pos) in agent.allowed_zones:
                visible_waste_positions[waste.waste_type].append(waste.pos)

        allowed_moves = self.get_accessible_neighborhood(agent)
        random_move = self.random.choice(allowed_moves) if allowed_moves else current_pos
        return {
            "visible_tiles": visible_tiles,
            "current_tile_wastes": visible_tiles[current_pos]["wastes"],
            "visible_waste_positions": visible_waste_positions,
            "allowed_moves": allowed_moves,
            "random_move": random_move,
            "disposal_pos": self.disposal_pos,
            "east_targets": self.east_targets,
            "zone": self.zone_for_pos(current_pos),
        }

    def _waste_by_id(self, waste_id: int | None, pos: tuple[int, int], waste_type: str | None = None):
        for item in self.grid.get_cell_list_contents([pos]):
            if isinstance(item, Waste) and (waste_id is None or item.unique_id == waste_id):
                if waste_type is None or item.waste_type == waste_type:
                    return item
        return None

    def do(self, agent, action: dict) -> dict:
        action_type = action.get("type", "idle")

        if action_type == "move":
            destination = tuple(action["destination"])
            if destination in self.get_accessible_neighborhood(agent):
                old_pos = agent.pos
                self.grid.move_agent(agent, destination)
                self.total_distance += abs(destination[0] - old_pos[0]) + abs(destination[1] - old_pos[1])

        elif action_type == "pick":
            if len(agent.carrying) < agent.carry_capacity:
                waste = self._waste_by_id(action.get("waste_id"), agent.pos, waste_type=agent.collectible_type)
                if waste is not None:
                    self.grid.remove_agent(waste)
                    agent.carrying.append(waste.waste_type)

        elif action_type == "transform":
            if (
                agent.transform_threshold is not None
                and len(agent.carrying) >= agent.transform_threshold
                and all(w == agent.collectible_type for w in agent.carrying[: agent.transform_threshold])
            ):
                for _ in range(agent.transform_threshold):
                    agent.carrying.pop(0)
                agent.carrying.append(agent.output_type)

        elif action_type == "drop":
            if len(agent.carrying) == 1:
                waste_type = agent.carrying.pop()
                self.grid.place_agent(Waste(self, waste_type=waste_type), agent.pos)

        elif action_type == "dispose":
            if agent.pos == self.disposal_pos and len(agent.carrying) == 1 and agent.carrying[0] == "red":
                agent.carrying.pop()
                self.disposed_waste += 1

        return self.get_percepts(agent)

    def step(self):
        self.agents.shuffle_do("step")
        self._record_robot_visits()
        self.datacollector.collect(self)
        if self.steps >= self.max_steps or (self.count_waste("green") == 0 and self.count_waste("yellow") == 0 and self.count_waste("red") == 0 and all(len(r.carrying) == 0 for r in self.robot_agents())):
            self.running = False

    def summary(self) -> dict:
        return {
            "step": self.steps,
            "green_waste": self.count_waste("green"),
            "yellow_waste": self.count_waste("yellow"),
            "red_waste": self.count_waste("red"),
            "disposed_waste": self.disposed_waste,
        }

    def get_zone(self, pos):
        x, y = pos
        if x < self.grid.width // 3:
            return "green"
        elif x < 2 * self.grid.width // 3:
            return "yellow"
        else:
            return "red"
    def get_zone_color(self, pos):
        zone = self.get_zone(pos)
        if zone == "green":
            return "#4CAF50"
        elif zone == "yellow":
            return "#FBC02D"
        else:
            return "#E53935"
