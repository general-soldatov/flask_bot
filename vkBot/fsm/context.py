from typing import Any, Dict, Optional, Union
from .state import State
from .storage.base import BaseStorage

class FSMContext:
    """
    Контекст конечного автомата для конкретного пользователя.
    Все методы СИНХРОННЫЕ.
    
    Пример:
        state.set_state(OrderFood.choosing_food_name)
        state.update_data(food="pizza")
        data = state.get_data()
        state.clear()
    """
    def __init__(self, storage: BaseStorage, key: str) -> None:
        self.storage = storage
        self.key = key

    def set_state(self, state: Any = None) -> None:
        """
        Установить состояние.
        
        Args:
            state: State, строка или None (сбросить состояние)
        """
        if state is None:
            self.storage.set_state(self.key, None)
            return
        if isinstance(state, State):
            state_str = state.state
        elif isinstance(state, str):
            state_str = state
        else:
            raise TypeError(f'state must be State, str or None, got{type(state)}')
        self.storage.set_state(self.key, state_str)

    def get_state(self) -> Optional[str]: 
        """Получить текущее состояние (строку)"""
        return self.storage.get_state(self.key)

    def is_state(self, state: Union[State, str]) -> bool:
        """Проверить, что текущее состояние равно указанному"""
        current = self.get_state()
        if current is None:
            return False

        expected = state.state if isinstance(state, State) else state
        return current == expected
    
    def set_data(self, data: Dict[str, Any]) -> None: 
        """Полностью перезаписать данные"""
        self.storage.set_data(self.key, data)
        
    def update_data(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Обновить данные (слияние с существующими).
        
        Пример:
            state.update_data(food="pizza", size="L")
        """
        return self.storage.update_data(self.key, kwargs)
    
    def get_data(self) -> Dict[str, Any]: 
        """Получить все данные"""
        return self.storage.get_data(self.key)
    
    def clear(self) -> None:
        """Очистить состояние и данные"""
        self.storage.clear(self.key)

    def clear_state(self) -> None:
        self.storage.clear_state(self.key)

    def __repr__(self) -> str:
        return f"FSMContext(key={self.key!r}, state={self.get_state()!r})"