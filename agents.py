"""Robot agents for the robot mission.

Group number: 22
Creation date: 2026-03-18
Members: 
    - Gabriel	Anjos Moura
    - Vinícius	da Mata e Mota
    - Nicholas	Oliveira Rodrigues Bragança
"""

from __future__ import annotations

from collections import deque

from mesa import Agent

try:
    from . import actions
except ImportError:
    import actions


class BaseRobotAgent(Agent):
    robot_type = "base"
    allowed_zones = {"z1", "z2", "z3"}
    collectible_type = None
    output_type = None
    transform_threshold = None
    carry_capacity = 2

    def __init__(self, model):
        super().__init__(model)
        self.carrying = []
        self.knowledge = {
            "memory": {},
            "history": deque(maxlen=25),
            "last_action": None,
            "last_percepts": None,
        }

    @property
    def cargo_count(self) -> int:
        return len(self.carrying)

    def step(self):
        self.step_agent()

    def step_agent(self):
        percepts = self.model.get_percepts(self)
        self._update_knowledge(percepts)
        action = self.deliberate(self.knowledge)
        self.knowledge["last_action"] = action
        returned_percepts = self.model.do(self, action)
        self.knowledge["last_percepts"] = returned_percepts
        self.knowledge["history"].append(
            {
                "pos": self.pos,
                "action": action,
                "carrying": list(self.carrying),
            }
        )

    def _update_knowledge(self, percepts: dict):
        self.knowledge.update(percepts)
        self.knowledge["current_goal"] = None
        self.knowledge["goal_type"] = None
        memory = self.knowledge.setdefault("memory", {})
        for pos, content in percepts.get("visible_tiles", {}).items():
            memory[pos] = content
            
        for pos, tile in memory.items():
            if tile.get("zone") in self.allowed_zones:
                for w in tile.get("wastes", []):
                    wtype = w.get("waste_type")
                    if wtype:
                        target_dict = self.knowledge["orphan_waste_positions"] if w.get("orphan", False) else self.knowledge["visible_waste_positions"]
                        if wtype in target_dict and pos not in target_dict[wtype]:
                            target_dict[wtype].append(pos)
                            
        if "patrol_path" not in self.knowledge:
            boundaries = self.model.zone_boundaries
            allowed_xs = []
            for z in self.allowed_zones:
                if z in boundaries:
                    allowed_xs.extend([boundaries[z][0], boundaries[z][1]])
            if not allowed_xs:
                allowed_xs = [0, self.model.width - 1]
            min_x = min(allowed_xs)
            max_x = max(allowed_xs)
            ymax = self.model.height - 1

            path = []
            up = True
            xs = list(range(min_x + 1, max_x + 1, 3))
            if not xs:
                xs = [(min_x + max_x) // 2]
            elif xs[-1] + 1 < max_x:
                xs.append(max_x - 1)

            for x in xs:
                if up:
                    path.append((x, 0))
                    path.append((x, ymax))
                else:
                    path.append((x, ymax))
                    path.append((x, 0))
                up = not up

            closest_idx = 0
            best_dist = float('inf')
            pos = self.pos if self.pos else (min_x, 0)
            for i, p in enumerate(path):
                dist = abs(p[0] - pos[0]) + abs(p[1] - pos[1])
                if dist < best_dist:
                    best_dist = dist
                    closest_idx = i
                    
            self.knowledge["patrol_path"] = path[closest_idx:] + path[:closest_idx]

        self.knowledge["pos"] = self.pos
        self.knowledge["carrying_types"] = list(self.carrying)
        self.knowledge["robot_type"] = self.robot_type
        self.knowledge["allowed_zones"] = tuple(sorted(self.allowed_zones))
        self.knowledge["collectible_type"] = self.collectible_type
        self.knowledge["output_type"] = self.output_type
        self.knowledge["transform_threshold"] = self.transform_threshold
        self.knowledge["carry_capacity"] = self.carry_capacity

    @staticmethod
    def deliberate(knowledge: dict) -> dict:
        return actions.idle()

    @staticmethod
    def _free_allowed_moves(knowledge: dict) -> list[tuple[int, int]]:
        visible_tiles = knowledge.get("visible_tiles", {})
        free_moves = []
        for pos in knowledge.get("allowed_moves", []):
            tile = visible_tiles.get(pos)
            if tile is None or not tile.get("robots"):
                free_moves.append(pos)
        return free_moves

    @staticmethod
    def _action_towards(knowledge: dict, target: tuple[int, int] | None, goal_type: str = "objective") -> dict:
        knowledge["current_goal"] = target
        knowledge["goal_type"] = goal_type
        if target is None:
            return actions.idle()
        pos = knowledge["pos"]
        if pos == target:
            return actions.idle()
        candidates = BaseRobotAgent._free_allowed_moves(knowledge)
        if not candidates:
            return actions.idle()
        best = min(
            candidates,
            key=lambda p: (abs(p[0] - target[0]) + abs(p[1] - target[1]), -p[0]),
        )
        return actions.move(best)

    @staticmethod
    def _nearest_target(pos: tuple[int, int], positions: list[tuple[int, int]]) -> tuple[int, int] | None:
        if not positions:
            return None
        return min(positions, key=lambda p: abs(p[0] - pos[0]) + abs(p[1] - pos[1]))

    @staticmethod
    def _get_lawnmower_target(knowledge: dict) -> tuple[int, int]:
        pos = knowledge["pos"]
        path = knowledge.get("patrol_path", [])
        
        if not path:
            return knowledge.get("random_move", pos)
            
        current_target = path[0]
        if abs(pos[0] - current_target[0]) <= 1 and abs(pos[1] - current_target[1]) <= 1:
            path.append(path.pop(0))
            current_target = path[0]

        return current_target


class GreenRobotAgent(BaseRobotAgent):
    robot_type = "green"
    allowed_zones = {"z1"}
    collectible_type = "green"
    output_type = "yellow"
    transform_threshold = 2
    carry_capacity = 2

    @staticmethod
    def deliberate(knowledge: dict) -> dict:
        pos = knowledge["pos"]
        carrying = knowledge["carrying_types"]
        visible = knowledge["visible_waste_positions"]
        orphans = knowledge.get("orphan_waste_positions", {})
        east_targets = knowledge["east_targets"]["z1"]
        same_cell = knowledge["current_tile_wastes"]

        target_greens = list(visible.get("green", []))
        orphan_greens = list(orphans.get("green", []))
        # Pick orphans if: already carrying 1 (want to pair), OR no non-orphan greens exist
        # (meaning the orphan is the last one and will never get a pair).
        no_more_greens = len(target_greens) == 0
        can_pick_orphans = len(carrying) == 1 or no_more_greens
        if can_pick_orphans:
            target_greens.extend(orphan_greens)

        if len(carrying) == 1 and carrying[0] == "yellow":
            if pos in east_targets:
                return actions.drop()
            target_drop = min(east_targets, key=lambda p: abs(p[0]-pos[0]) + abs(p[1]-pos[1]))
            return BaseRobotAgent._action_towards(knowledge, target_drop)

        if len(carrying) == 1 and carrying[0] == "green" and not target_greens:
            # No pair possible: force-promote the single green → yellow so the
            # yellow robot can carry it forward without leaving dead waste.
            return actions.transform_orphan()

        # After dropping yellow at the handoff point, vacate this cell so yellow robots can enter.
        if pos in east_targets and not carrying:
            yellow_here = [w for w in same_cell if w["waste_type"] == "yellow"]
            if yellow_here:
                retreat_target = (max(0, pos[0] - 1), pos[1])
                retreat_action = BaseRobotAgent._action_towards(knowledge, retreat_target)
                if retreat_action["type"] != "idle":
                    return retreat_action
                return BaseRobotAgent._action_towards(knowledge, knowledge["random_move"])

        if len(carrying) >= 2 and all(t == "green" for t in carrying):
            return actions.transform()

        green_here = [w for w in same_cell if w["waste_type"] == "green"]
        if green_here:
            if not can_pick_orphans:
                green_here = [w for w in green_here if not w.get("orphan")]
        if green_here and len(carrying) < 2:
            return actions.pick_waste(green_here[0]["id"])

        target = BaseRobotAgent._nearest_target(pos, target_greens)
        if target is not None:
            return BaseRobotAgent._action_towards(knowledge, target)

        frontier = BaseRobotAgent._get_lawnmower_target(knowledge)
        return BaseRobotAgent._action_towards(knowledge, frontier, goal_type="patrol")


class YellowRobotAgent(BaseRobotAgent):
    robot_type = "yellow"
    allowed_zones = {"z1", "z2"}
    collectible_type = "yellow"
    output_type = "red"
    transform_threshold = 2
    carry_capacity = 2

    @staticmethod
    def deliberate(knowledge: dict) -> dict:
        pos = knowledge["pos"]
        carrying = knowledge["carrying_types"]
        visible = knowledge["visible_waste_positions"]
        orphans = knowledge.get("orphan_waste_positions", {})
        east_targets = knowledge["east_targets"]["z2"]

        target_yellows = list(visible.get("yellow", []))
        orphan_yellows = list(orphans.get("yellow", []))
        # Pick orphans if: already carrying 1 (want to pair), OR no non-orphan yellows exist.
        no_more_yellows = len(target_yellows) == 0
        can_pick_orphans = len(carrying) == 1 or no_more_yellows
        if can_pick_orphans:
            target_yellows.extend(orphan_yellows)

        if len(carrying) == 1 and carrying[0] == "red":
            if pos in east_targets:
                return actions.drop()
            target_drop = min(east_targets, key=lambda p: abs(p[0]-pos[0]) + abs(p[1]-pos[1]))
            return BaseRobotAgent._action_towards(knowledge, target_drop)

        if len(carrying) == 1 and carrying[0] == "yellow" and not target_yellows:
            # No pair possible: force-promote the single yellow to red so the
            # red robot can pick it up and dispose it.
            return actions.transform_orphan()

        if len(carrying) >= 2 and all(t == "yellow" for t in carrying):
            return actions.transform()

        same_cell = knowledge["current_tile_wastes"]
        yellow_here = [w for w in same_cell if w["waste_type"] == "yellow"]
        if yellow_here:
            if not can_pick_orphans:
                yellow_here = [w for w in yellow_here if not w.get("orphan")]
        if yellow_here and len(carrying) < 2:
            return actions.pick_waste(yellow_here[0]["id"])

        target = BaseRobotAgent._nearest_target(pos, target_yellows)
        if target is not None:
            return BaseRobotAgent._action_towards(knowledge, target)

        frontier = BaseRobotAgent._get_lawnmower_target(knowledge)
        return BaseRobotAgent._action_towards(knowledge, frontier, goal_type="patrol")


class RedRobotAgent(BaseRobotAgent):
    robot_type = "red"
    allowed_zones = {"z1", "z2", "z3"}
    collectible_type = "red"
    output_type = None
    transform_threshold = None
    carry_capacity = 1

    @staticmethod
    def deliberate(knowledge: dict) -> dict:
        pos = knowledge["pos"]
        carrying = knowledge["carrying_types"]
        disposal_pos = knowledge["disposal_pos"]
        visible = knowledge["visible_waste_positions"]

        if len(carrying) == 1 and carrying[0] == "red":
            if pos == disposal_pos:
                return actions.dispose()
            return BaseRobotAgent._action_towards(knowledge, disposal_pos)

        same_cell = knowledge["current_tile_wastes"]
        red_here = [w for w in same_cell if w["waste_type"] == "red"]
        if red_here and len(carrying) < 1:
            return actions.pick_waste(red_here[0]["id"])

        target = BaseRobotAgent._nearest_target(pos, visible["red"])
        if target is not None:
            return BaseRobotAgent._action_towards(knowledge, target)

        frontier = BaseRobotAgent._get_lawnmower_target(knowledge)
        return BaseRobotAgent._action_towards(knowledge, frontier, goal_type="patrol")
