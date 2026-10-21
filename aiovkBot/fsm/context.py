from typing import Any, Dict, Optional, Union
from .state import State
from .storage.base import BaseStorage


class FSMContext:
    """
    Контекст конечного автомата для конкретного пользователя.
    Все методы — корутины.

    Пример:
        await state.set_state(OrderFood.choosing_food_name)
        await state.update_data(food="pizza")
        data = await state.get_data()
        await state.clear()
    """

    def __init__(self, storage: BaseStorage, key: str) -> None:
        self.storage = storage
        self.key = key

    async def set_state(self, state: Any = None) -> None:
        """State, строка или None (сбросить состояние)."""
        if state is None:
            await self.storage.set_state(self.key, None)
            return
        if isinstance(state, State):
            state_str = state.state
        elif isinstance(state, str):
            state_str = state
        else:
            raise TypeError(f"state must be State, str or None, got {type(state)}")
        await self.storage.set_state(self.key, state_str)

    async def get_state(self) -> Optional[str]:
        """Текущее состояние (строка)"""
        return await self.storage.get_state(self.key)

    async def is_state(self, state: Union[State, str]) -> bool:
        """Текущее состояние равно указанному?"""
        current = await self.get_state()
        if current is None:
            return False
        expected = state.state if isinstance(state, State) else state
        return current == expected

    async def set_data(self, data: Dict[str, Any]) -> None:
        """Полностью перезаписать данные"""
        await self.storage.set_data(self.key, data)

    async def update_data(self, **kwargs: Any) -> Dict[str, Any]:
        """Слияние с существующими данными: await state.update_data(food="pizza")"""
        return await self.storage.update_data(self.key, kwargs)

    async def get_data(self) -> Dict[str, Any]:
        return await self.storage.get_data(self.key)

    async def clear(self) -> None:
        """Очистить состояние и данные"""
        await self.storage.clear(self.key)

    async def clear_state(self) -> None:
        await self.storage.clear_state(self.key)

    def __repr__(self) -> str:
        return f"FSMContext(key={self.key!r})"
