import logging
from typing import Any, Optional

from .fsm.state import State
from .types import Message, MessageEventObject

logger = logging.getLogger(__name__)

# Фильтр — любой callable(event), обычный или async. Результат:
#   False/None — не подошло; True — подошло; dict — подошло + данные для хендлера.


class CommandObject:
    def __init__(self, command: str, prefix: str,
                 args: Optional[str] = None,
                 mention: Optional[str] = None):
        self.command = command
        self.prefix = prefix
        self.args = args
        self.mention = mention


class BaseFilter:
    """Наследуйте и переопределите __call__ (можно сделать его async)."""

    def __call__(self, event):
        raise NotImplementedError(f"{type(self).__name__}.__call__ не реализован")


class StateFilter(BaseFilter):
    """
    Фильтр по состоянию FSM (асинхронный: читает состояние из хранилища).

    Пример:
        @dp.message(StateFilter(OrderFood.choosing_food_name))
        async def handler(message, state): ...

        @dp.message(StateFilter("OrderFood:choosing_food_name"))
        @dp.message(StateFilter(None))  # только без состояния
    """

    def __init__(self, *states: Any) -> None:
        self.states = states

    async def __call__(self, event) -> bool:
        fsm_context = getattr(event, '_fsm_context', None)
        if fsm_context is None:
            logger.error('State Filter: event has no fsm_context')
            return False

        current_state = await fsm_context.get_state()
        if self.states == (None,):
            return current_state is None

        for state in self.states:
            if state is None:
                if current_state is None:
                    return True
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
        try:
            return event.payload_model.action == self.action
        except Exception:  # payload без "action"
            return False


class Command(BaseFilter):
    def __init__(self, *commands: str, prefix: str = "/"):
        super().__init__()
        self.commands = [c.lower() for c in commands]
        self.prefix = prefix

    def __call__(self, message: Message):
        text = message.text or ""
        if not text.startswith(self.prefix):
            return False
        parts = text[len(self.prefix):].split(maxsplit=1)
        if not parts or parts[0].lower() not in self.commands:
            return False
        # доступно хендлеру как параметр `command`
        return {"command": CommandObject(
            parts[0].lower(), self.prefix, args=parts[1] if len(parts) > 1 else None
        )}


class CommandStart(Command):
    def __init__(self, prefix: str = ""):
        super().__init__('/start', 'Начать', prefix=prefix)
