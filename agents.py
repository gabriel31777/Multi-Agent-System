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
    from .communication.mailbox.Mailbox import Mailbox
    from .communication.message.Message import Message
    from .communication.message.MessagePerformative import MessagePerformative
    from .communication.message.MessageService import MessageService
except ImportError:
    import actions
    from communication.mailbox.Mailbox import Mailbox
    from communication.message.Message import Message
    from communication.message.MessagePerformative import MessagePerformative
    from communication.message.MessageService import MessageService


MSG_HANDOFF_READY = "handoff_ready"
MSG_HANDOFF_CLAIM = "handoff_claim"
MSG_TARGET_FOUND = "target_found"
MSG_TARGET_CLAIM = "target_claim"

TARGET_CLAIM_TTL = 6
HANDOFF_TTL = 12


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
        self._comm_name = f"{self.robot_type}_{self.unique_id}"
        self._mailbox = Mailbox()
        self._message_service = MessageService.get_instance()
        self.knowledge = {
            "memory": {},
            "history": deque(maxlen=25),
            "last_action": None,
            "last_percepts": None,
            "pending_handoffs": {},
            "handoff_targets": [],
            "active_handoff": None,
            "peer_target_claims": {},
            "target_found_event": None,
            "last_target_claim": None,
            "last_target_claim_step": -1,
        }

    @property
    def cargo_count(self) -> int:
        return len(self.carrying)

    def get_name(self) -> str:
        return self._comm_name

    def receive_message(self, message):
        self._mailbox.receive_messages(message)

    def send_message(self, message):
        if self._message_service is None:
            return
        self._message_service.send_message(message)

    def get_new_messages(self):
        return self._mailbox.get_new_messages()

    def step(self):
        self.step_agent()

    def step_agent(self):
        percepts = self.model.get_percepts(self)
        self._update_knowledge(percepts)
        self._process_messages()
        action = self.deliberate(self.knowledge)
        self._maybe_publish_target_claim()

        target_found_event = self.knowledge.get("target_found_event")
        if target_found_event:
            self._broadcast_target_found(target_found_event)
            self.knowledge["target_found_event"] = None

        self.knowledge["last_action"] = action
        carrying_before = list(self.carrying)
        pos_before = self.pos
        returned_percepts = self.model.do(self, action)
        self._maybe_finalize_handoff(action, pos_before)
        self._maybe_broadcast_handoff_ready(action, carrying_before, pos_before)
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
        self.knowledge["step"] = getattr(self.model, "steps", 0)
        self.knowledge["current_goal"] = None
        self.knowledge["goal_type"] = None
        self.knowledge["target_found_event"] = None
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
        self.knowledge.setdefault("pending_handoffs", {})
        self.knowledge.setdefault("handoff_targets", [])
        self.knowledge.setdefault("active_handoff", None)
        self.knowledge.setdefault("peer_target_claims", {})
        self._cleanup_comm_state()
        self._refresh_handoff_targets()

    def _peer_names(self, robot_type: str | None = None) -> list[str]:
        selected_type = robot_type or self.robot_type
        peers = []
        for robot in self.model.robot_agents():
            if robot is self:
                continue
            if getattr(robot, "robot_type", None) == selected_type and hasattr(robot, "get_name"):
                peers.append(robot.get_name())
        return peers

    def _send_to(self, receiver_name: str, performative: MessagePerformative, content: dict):
        self.send_message(
            Message(
                self.get_name(),
                receiver_name,
                performative,
                content,
            )
        )

    def _broadcast(self, receiver_names: list[str], performative: MessagePerformative, content: dict):
        for receiver_name in receiver_names:
            self._send_to(receiver_name, performative, content)

    @staticmethod
    def _normalize_pos(raw_pos) -> tuple[int, int] | None:
        if not isinstance(raw_pos, (tuple, list)) or len(raw_pos) != 2:
            return None
        return (int(raw_pos[0]), int(raw_pos[1]))

    def _eta_to(self, pos: tuple[int, int]) -> int:
        return abs(self.pos[0] - pos[0]) + abs(self.pos[1] - pos[1])

    def _can_pick_type(self, waste_type: str | None) -> bool:
        if waste_type is None or self.collectible_type is None or waste_type != self.collectible_type:
            return False
        if self.cargo_count >= self.carry_capacity:
            return False
        return all(item == self.collectible_type for item in self.carrying)

    def _has_priority_over_claim(self, pos: tuple[int, int], claim: dict) -> bool:
        peer_eta = int(claim.get("eta", 10**9))
        peer_name = str(claim.get("agent", "~"))
        my_rank = (self._eta_to(pos), self.get_name())
        peer_rank = (peer_eta, peer_name)
        return my_rank <= peer_rank

    def _filter_claimed_targets(self, positions: list[tuple[int, int]]) -> list[tuple[int, int]]:
        unique_positions: list[tuple[int, int]] = []
        for pos in positions:
            normalized = self._normalize_pos(pos)
            if normalized is None or normalized in unique_positions:
                continue
            unique_positions.append(normalized)

        peer_claims = self.knowledge.get("peer_target_claims", {})
        filtered = []
        for pos in unique_positions:
            claim = peer_claims.get(pos)
            if claim is None or self._has_priority_over_claim(pos, claim):
                filtered.append(pos)
        return filtered

    def _cleanup_comm_state(self):
        step = self.knowledge.get("step", 0)
        peer_claims = self.knowledge.setdefault("peer_target_claims", {})
        for pos, claim in list(peer_claims.items()):
            if step - int(claim.get("step", step)) > TARGET_CLAIM_TTL:
                peer_claims.pop(pos, None)

        pending_handoffs = self.knowledge.setdefault("pending_handoffs", {})
        for pos, offer in list(pending_handoffs.items()):
            if step - int(offer.get("step", step)) > HANDOFF_TTL:
                pending_handoffs.pop(pos, None)

        active_handoff = self.knowledge.get("active_handoff")
        if isinstance(active_handoff, dict):
            active_step = int(active_handoff.get("step", step))
            if step - active_step > HANDOFF_TTL:
                self.knowledge["active_handoff"] = None

    def _refresh_handoff_targets(self):
        candidates = []
        active_handoff = self.knowledge.get("active_handoff")
        if isinstance(active_handoff, dict):
            active_pos = self._normalize_pos(active_handoff.get("pos"))
            if active_pos is not None:
                candidates.append(active_pos)

        pending = self.knowledge.get("pending_handoffs", {})
        for pos, offer in pending.items():
            normalized_pos = self._normalize_pos(pos)
            if normalized_pos is None:
                continue
            if offer.get("waste_type") == self.collectible_type:
                candidates.append(normalized_pos)

        self.knowledge["handoff_targets"] = self._filter_claimed_targets(candidates)

    def _is_best_handoff_receiver(self, pos: tuple[int, int], waste_type: str) -> bool:
        candidates = []
        for robot in self.model.robot_agents():
            if getattr(robot, "robot_type", None) != self.robot_type:
                continue
            if not hasattr(robot, "_can_pick_type") or not robot._can_pick_type(waste_type):
                continue
            if getattr(robot, "pos", None) is None:
                continue
            dist = abs(robot.pos[0] - pos[0]) + abs(robot.pos[1] - pos[1])
            candidates.append((dist, robot.get_name()))

        if not candidates:
            return False
        _, best_name = min(candidates)
        return best_name == self.get_name()

    def _send_handoff_claim(self, handoff_pos: tuple[int, int], waste_type: str, handoff_sender: str):
        eta = self._eta_to(handoff_pos)
        content = {
            "kind": MSG_HANDOFF_CLAIM,
            "claimer": self.get_name(),
            "robot_type": self.robot_type,
            "pos": handoff_pos,
            "waste_type": waste_type,
            "handoff_sender": handoff_sender,
            "eta": eta,
            "step": self.knowledge.get("step", 0),
        }
        self._send_to(handoff_sender, MessagePerformative.COMMIT, content)
        self._broadcast(self._peer_names(), MessagePerformative.COMMIT, content)
        self._broadcast_target_claim(handoff_pos, eta=eta, target_kind="handoff", force=True)

    def _claim_best_pending_handoff(self):
        if not self._can_pick_type(self.collectible_type):
            return

        active_handoff = self.knowledge.get("active_handoff")
        if isinstance(active_handoff, dict):
            return

        pending = self.knowledge.get("pending_handoffs", {})
        raw_candidates = [
            self._normalize_pos(pos)
            for pos, offer in pending.items()
            if offer.get("waste_type") == self.collectible_type
        ]
        candidates = self._filter_claimed_targets([p for p in raw_candidates if p is not None])
        if not candidates:
            return

        best_pos = self._nearest_target(self.pos, candidates)
        if best_pos is None or not self._is_best_handoff_receiver(best_pos, self.collectible_type):
            return

        offer = pending.get(best_pos) or pending.get(tuple(best_pos))
        if not isinstance(offer, dict):
            return
        handoff_sender = str(offer.get("from", ""))
        if not handoff_sender:
            return

        self.knowledge["active_handoff"] = {
            "pos": best_pos,
            "from": handoff_sender,
            "waste_type": self.collectible_type,
            "step": self.knowledge.get("step", 0),
        }
        self._send_handoff_claim(best_pos, self.collectible_type, handoff_sender)

    def _handle_handoff_ready(self, sender: str, content: dict):
        handoff_pos = self._normalize_pos(content.get("pos"))
        waste_type = content.get("waste_type")
        if handoff_pos is None or waste_type != self.collectible_type:
            return

        self.knowledge["pending_handoffs"][handoff_pos] = {
            "from": sender,
            "waste_type": waste_type,
            "step": self.knowledge.get("step", 0),
        }

    def _handle_handoff_claim(self, sender: str, content: dict):
        claim_pos = self._normalize_pos(content.get("pos"))
        if claim_pos is None:
            return
        if content.get("robot_type") not in (None, self.robot_type):
            return

        claimer = str(content.get("claimer", sender))
        if claimer == self.get_name():
            return

        self.knowledge["peer_target_claims"][claim_pos] = {
            "agent": claimer,
            "eta": int(content.get("eta", 10**9)),
            "step": int(content.get("step", self.knowledge.get("step", 0))),
        }

        active_handoff = self.knowledge.get("active_handoff")
        if not isinstance(active_handoff, dict):
            return

        active_pos = self._normalize_pos(active_handoff.get("pos"))
        if active_pos == claim_pos and not self._has_priority_over_claim(claim_pos, self.knowledge["peer_target_claims"][claim_pos]):
            self.knowledge["active_handoff"] = None

    def _handle_target_claim(self, sender: str, content: dict):
        claim_pos = self._normalize_pos(content.get("pos"))
        if claim_pos is None:
            return
        if content.get("robot_type") not in (None, self.robot_type):
            return

        claimer = str(content.get("claimer", sender))
        if claimer == self.get_name():
            return

        new_claim = {
            "agent": claimer,
            "eta": int(content.get("eta", 10**9)),
            "step": int(content.get("step", self.knowledge.get("step", 0))),
        }
        current_claim = self.knowledge["peer_target_claims"].get(claim_pos)
        if current_claim is None:
            self.knowledge["peer_target_claims"][claim_pos] = new_claim
            return

        current_rank = (int(current_claim.get("eta", 10**9)), str(current_claim.get("agent", "~")))
        new_rank = (new_claim["eta"], new_claim["agent"])
        if new_rank < current_rank:
            self.knowledge["peer_target_claims"][claim_pos] = new_claim

    def _handle_target_found(self, sender: str, content: dict):
        abandoned_pos = self._normalize_pos(content.get("abandoned_pos") or content.get("pos"))
        if abandoned_pos is None:
            return
        if content.get("robot_type") not in (None, self.robot_type):
            return

        finder = str(content.get("finder", sender))
        peer_claim = self.knowledge["peer_target_claims"].get(abandoned_pos)
        if peer_claim and str(peer_claim.get("agent")) == finder:
            self.knowledge["peer_target_claims"].pop(abandoned_pos, None)

        handoff_sender = content.get("handoff_sender")
        waste_type = content.get("waste_type")
        if handoff_sender and waste_type == self.collectible_type:
            self.knowledge["pending_handoffs"][abandoned_pos] = {
                "from": handoff_sender,
                "waste_type": waste_type,
                "step": self.knowledge.get("step", 0),
            }

    def _process_messages(self):
        for msg in self.get_new_messages():
            content = msg.get_content() if hasattr(msg, "get_content") else getattr(msg, "content", None)
            sender = msg.get_exp() if hasattr(msg, "get_exp") else getattr(msg, "exp", "")
            if not isinstance(content, dict):
                continue

            kind = content.get("kind")
            if kind == MSG_HANDOFF_READY:
                self._handle_handoff_ready(sender, content)
            elif kind == MSG_HANDOFF_CLAIM:
                self._handle_handoff_claim(sender, content)
            elif kind == MSG_TARGET_FOUND:
                self._handle_target_found(sender, content)
            elif kind == MSG_TARGET_CLAIM:
                self._handle_target_claim(sender, content)

        self._cleanup_comm_state()
        self._claim_best_pending_handoff()
        self._refresh_handoff_targets()

    def _broadcast_target_claim(
        self,
        target_pos: tuple[int, int],
        eta: int | None = None,
        target_kind: str = "waste",
        force: bool = False,
    ):
        if target_pos is None:
            return

        eta = self._eta_to(target_pos) if eta is None else eta
        step = self.knowledge.get("step", 0)
        claim_signature = (target_pos, eta, target_kind)
        if not force:
            last_signature = self.knowledge.get("last_target_claim")
            last_step = int(self.knowledge.get("last_target_claim_step", -1))
            if last_signature == claim_signature and (step - last_step) < 3:
                return

        content = {
            "kind": MSG_TARGET_CLAIM,
            "claimer": self.get_name(),
            "robot_type": self.robot_type,
            "pos": target_pos,
            "eta": eta,
            "target_kind": target_kind,
            "waste_type": self.collectible_type,
            "step": step,
        }
        self._broadcast(self._peer_names(), MessagePerformative.PROPOSE, content)
        self.knowledge["last_target_claim"] = claim_signature
        self.knowledge["last_target_claim_step"] = step

    def _maybe_publish_target_claim(self):
        current_goal = self._normalize_pos(self.knowledge.get("current_goal"))
        if current_goal is None:
            return
        if self.knowledge.get("goal_type") != "objective":
            return
        if current_goal == self.pos:
            return

        active_handoff = self.knowledge.get("active_handoff")
        if isinstance(active_handoff, dict) and self._normalize_pos(active_handoff.get("pos")) == current_goal:
            target_kind = "handoff"
        else:
            target_kind = "waste"
        self._broadcast_target_claim(current_goal, target_kind=target_kind)

    def _mark_target_found(self, found_pos: tuple[int, int]):
        active_handoff = self.knowledge.get("active_handoff")
        if not isinstance(active_handoff, dict):
            return

        handoff_pos = self._normalize_pos(active_handoff.get("pos"))
        if handoff_pos is None or handoff_pos == found_pos:
            return

        self.knowledge["target_found_event"] = {
            "abandoned_pos": handoff_pos,
            "found_pos": found_pos,
            "handoff_sender": active_handoff.get("from"),
            "waste_type": active_handoff.get("waste_type", self.collectible_type),
        }
        self.knowledge["active_handoff"] = None

    def _broadcast_target_found(self, event: dict):
        content = {
            "kind": MSG_TARGET_FOUND,
            "finder": self.get_name(),
            "robot_type": self.robot_type,
            "abandoned_pos": event.get("abandoned_pos"),
            "found_pos": event.get("found_pos"),
            "handoff_sender": event.get("handoff_sender"),
            "waste_type": event.get("waste_type"),
            "step": self.knowledge.get("step", 0),
        }
        self._broadcast(self._peer_names(), MessagePerformative.INFORM_REF, content)

    def _downstream_robot_type(self) -> str | None:
        if self.robot_type == "green":
            return "yellow"
        if self.robot_type == "yellow":
            return "red"
        return None

    def _maybe_finalize_handoff(self, action: dict, pos_before: tuple[int, int]):
        if action.get("type") != "pick":
            return
        active_handoff = self.knowledge.get("active_handoff")
        if not isinstance(active_handoff, dict):
            return
        active_pos = self._normalize_pos(active_handoff.get("pos"))
        if active_pos != pos_before:
            return
        self.knowledge["active_handoff"] = None
        self.knowledge.get("pending_handoffs", {}).pop(active_pos, None)

    def _drop_handoff_zone(self) -> str | None:
        if self.robot_type == "green":
            return "z1"
        if self.robot_type == "yellow":
            return "z2"
        return None

    def _maybe_broadcast_handoff_ready(self, action: dict, carrying_before: list[str], pos_before: tuple[int, int]):
        if action.get("type") != "drop" or len(carrying_before) != 1:
            return

        dropped_type = carrying_before[0]
        downstream_type = self._downstream_robot_type()
        handoff_zone = self._drop_handoff_zone()
        if downstream_type is None or handoff_zone is None:
            return

        if dropped_type != self.output_type:
            return

        if pos_before not in self.model.east_targets[handoff_zone]:
            return

        content = {
            "kind": MSG_HANDOFF_READY,
            "from_robot": self.get_name(),
            "robot_type": self.robot_type,
            "waste_type": dropped_type,
            "pos": pos_before,
            "step": self.knowledge.get("step", 0),
        }
        self._broadcast(self._peer_names(downstream_type), MessagePerformative.INFORM_REF, content)

    def deliberate(self, knowledge: dict) -> dict:
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

    def deliberate(self, knowledge: dict) -> dict:
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
        target_greens = self._filter_claimed_targets(target_greens)

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

    def deliberate(self, knowledge: dict) -> dict:
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
        target_yellows = self._filter_claimed_targets(target_yellows)

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
            self._mark_target_found(pos)
            return actions.pick_waste(yellow_here[0]["id"])

        handoff_targets = knowledge.get("handoff_targets", [])
        handoff_target = BaseRobotAgent._nearest_target(pos, handoff_targets)
        if handoff_target is not None:
            active_handoff = knowledge.get("active_handoff")
            if isinstance(active_handoff, dict):
                active_pos = self._normalize_pos(active_handoff.get("pos"))
                if active_pos == handoff_target and pos == handoff_target:
                    knowledge["active_handoff"] = None
                else:
                    return BaseRobotAgent._action_towards(knowledge, handoff_target)
            else:
                return BaseRobotAgent._action_towards(knowledge, handoff_target)

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

    def deliberate(self, knowledge: dict) -> dict:
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
            self._mark_target_found(pos)
            return actions.pick_waste(red_here[0]["id"])

        handoff_targets = knowledge.get("handoff_targets", [])
        handoff_target = BaseRobotAgent._nearest_target(pos, handoff_targets)
        if handoff_target is not None:
            active_handoff = knowledge.get("active_handoff")
            if isinstance(active_handoff, dict):
                active_pos = self._normalize_pos(active_handoff.get("pos"))
                if active_pos == handoff_target and pos == handoff_target:
                    knowledge["active_handoff"] = None
                else:
                    return BaseRobotAgent._action_towards(knowledge, handoff_target)
            else:
                return BaseRobotAgent._action_towards(knowledge, handoff_target)

        visible_reds = self._filter_claimed_targets(visible["red"])
        target = BaseRobotAgent._nearest_target(pos, visible_reds)
        if target is not None:
            return BaseRobotAgent._action_towards(knowledge, target)

        frontier = BaseRobotAgent._get_lawnmower_target(knowledge)
        return BaseRobotAgent._action_towards(knowledge, frontier, goal_type="patrol")
