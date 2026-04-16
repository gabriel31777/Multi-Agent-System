#!/usr/bin/env python3
from collections import deque
from collections import defaultdict


class MessageService:
    """MessageService class.
    Class implementing the message service used to dispatch messages between communicating agents.

    Not intended to be created more than once: it's a singleton.

    attr:
    
        messages_to_proceed: the list of message to proceed mailbox of the agent (list)
    """

    __instance = None

    @staticmethod
    def get_instance():
        """ Static access method.
        """
        return MessageService.__instance

    def __init__(self, model,instant_delivery=True):
        """ Create a new MessageService object.
        """
        if MessageService.__instance is not None:
            raise Exception("This class is a singleton!")
        else:
            MessageService.__instance = self
            self.__model = model
            self.__instant_delivery = instant_delivery
            self.__messages_to_proceed = []
            self.__log_messages = False
            self.__message_history = deque(maxlen=500)
            self.__message_counter = 0
            self.__drop_propose_messages = False
            self.__drop_all_messages = False
            self.__message_stats_total = 0
            self.__message_stats_performative = defaultdict(int)
            self.__message_stats_kind = defaultdict(int)

    def set_model(self, model):
        """Bind service to a model instance."""
        self.__model = model
        self.__messages_to_proceed.clear()
        self.__message_history.clear()
        self.__message_counter = 0
        self.__message_stats_total = 0
        self.__message_stats_performative.clear()
        self.__message_stats_kind.clear()

    def set_log_messages(self, enabled: bool):
        """Enable/disable debug print of each message."""
        self.__log_messages = bool(enabled)

    def set_instant_delivery(self, instant_delivery):
        """ Set the instant delivery parameter.
        """
        self.__instant_delivery = instant_delivery

    def set_drop_propose_messages(self, drop_messages: bool):
        """Enable/disable dropping messages with performative PROPOSE."""
        self.__drop_propose_messages = bool(drop_messages)

    def get_drop_propose_messages(self) -> bool:
        return self.__drop_propose_messages

    def set_drop_all_messages(self, drop_messages: bool):
        """Enable/disable dropping all outgoing messages."""
        self.__drop_all_messages = bool(drop_messages)
        if self.__drop_all_messages:
            self.__messages_to_proceed.clear()

    def get_drop_all_messages(self) -> bool:
        return self.__drop_all_messages

    def _record_message(self, message):
        content = message.get_content() if hasattr(message, "get_content") else None
        kind = content.get("kind") if isinstance(content, dict) else None
        perf = str(message.get_performative())
        self.__message_stats_total += 1
        self.__message_stats_performative[perf] += 1
        if kind is not None:
            self.__message_stats_kind[str(kind)] += 1
        if isinstance(content, dict):
            msg_step = content.get("step")
            msg_pos = content.get("pos", content.get("abandoned_pos"))
            msg_eta = content.get("eta")
        else:
            msg_step = None
            msg_pos = None
            msg_eta = None

        model_step = getattr(self.__model, "steps", None)
        self.__message_history.append(
            {
                "index": self.__message_counter,
                "step": model_step if msg_step is None else msg_step,
                "from": message.get_exp(),
                "to": message.get_dest(),
                "performative": perf,
                "kind": kind,
                "pos": msg_pos,
                "eta": msg_eta,
                "content": content,
            }
        )
        self.__message_counter += 1

    def get_message_history(self, limit=None):
        history = list(self.__message_history)
        if limit is None:
            return history
        if limit <= 0:
            return []
        return history[-limit:]

    def get_message_stats(self):
        return {
            "total": int(self.__message_stats_total),
            "by_performative": dict(self.__message_stats_performative),
            "by_kind": dict(self.__message_stats_kind),
        }

    def send_message(self, message):
        """ Dispatch message if instant delivery active, otherwise add the message to proceed list.
        """
        if self.__drop_all_messages:
            return
        if self.__drop_propose_messages and str(message.get_performative()) == "PROPOSE":
            return

        if self.__log_messages:
            print(message)
        self._record_message(message)
        if self.__instant_delivery:
    
            self.dispatch_message(message)
        else:
            self.__messages_to_proceed.append(message)
            
           

    def dispatch_message(self, message):
        """ Dispatch the message to the right agent.
        """
        target = self.find_agent_from_name(message.get_dest())
        if target is not None and hasattr(target, "receive_message"):
            target.receive_message(message)

    def dispatch_messages(self):
        """ Proceed each message received by the message service.
        """
        if len(self.__messages_to_proceed) > 0:
            for message in self.__messages_to_proceed:
                self.dispatch_message(message)

        self.__messages_to_proceed.clear()

    def find_agent_from_name(self, agent_name):
        """ Return the agent according to the agent name given.
        """
        for agent in self.__model.agents:
            if hasattr(agent, "get_name") and agent.get_name() == agent_name:
                return agent
        return None
