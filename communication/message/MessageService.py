#!/usr/bin/env python3
from collections import deque


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

    def set_model(self, model):
        """Bind service to a model instance."""
        self.__model = model
        self.__messages_to_proceed.clear()
        self.__message_history.clear()
        self.__message_counter = 0

    def set_log_messages(self, enabled: bool):
        """Enable/disable debug print of each message."""
        self.__log_messages = bool(enabled)

    def set_instant_delivery(self, instant_delivery):
        """ Set the instant delivery parameter.
        """
        self.__instant_delivery = instant_delivery

    def _record_message(self, message):
        content = message.get_content() if hasattr(message, "get_content") else None
        kind = content.get("kind") if isinstance(content, dict) else None
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
                "performative": str(message.get_performative()),
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

    def send_message(self, message):
        """ Dispatch message if instant delivery active, otherwise add the message to proceed list.
        """
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
