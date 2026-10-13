from typing import Any, Optional
from .types import Message, MessageEventObject
from vkBot.fsm import State
import logging

logger = logging.getLogger(__name__)

class CommandObject:
    def __init__(self, command: str, prefix: str, 
                 args: Optional[str] = None, 
                 mention: Optional[str] = None):
        self.command = command        
        self.prefix = prefix
        self.args = args              
        self.mention = mention  

class BaseFilter:
    def __init__(self): 
        pass

    def __call__(self, message: 'Message') -> bool: 
        cmd = message.text.split()[1:]
        return isinstance(cmd, str)

class StateFilter(BaseFilter):
    """
    Фильтр по состоянию FSM.
    
    Пример:
        @dp.message(StateFilter(OrderFood.choosing_food_name))
        def handler(message, state): ...
        
        @dp.message(StateFilter("OrderFood:choosing_food_name"))
        def handler(message, state): ...
        
        @dp.message(StateFilter(None))  # только без состояния
        def handler(message, state): ...
    """

    def __init__(self, *states: Any) -> None:
        self.states = states

        # self.target_states = [s.state if hasattr(s, 'state') else s for s in states]

    def __call__(self, event) -> bool:
        fsm_context = getattr(event, '_fsm_context', None)
        if fsm_context is None:
            logger.error('State Filter: event has no fsm_context')
            return False
        
        current_state = fsm_context.get_state()
        if self.states == (None, ): 
            return current_state is None

        for state in self.states:
            if state is None:
                if current_state is None:
                    True
            elif isinstance(state, State):
                if current_state == state.state:
                    return True
            elif isinstance(state, str):
                if current_state == state:
                    return True

        return False

class ActionPayload(BaseFilter):
    def __init__(self, action: str):
        self.action = action
    def __call__(self, event: MessageEventObject) -> bool:
        return event.payload_model.action == self.action

class Command(BaseFilter):
    def __init__(self, *commands: str, prefix: str = "/"):
        super().__init__()
        self.commands = [c.lower() for c in commands]
        self.prefix = prefix

    def __call__(self, message: Message) -> bool:
        if message.text.startswith(self.prefix):
            cmd_pure = message.text[len(self.prefix):].split()[0].lower()
            return cmd_pure in self.commands
        return False

class CommandStart(Command):
    def __init__(self, prefix: str = ""):
        super().__init__('/start', 'Начать', prefix=prefix)