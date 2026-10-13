from typing import Any, Dict, Optional
from .base import BaseStorage


class MemoryStorage(BaseStorage):
    """
    In-memory хранилище состояний.
    Аналог aiogram.fsm.storage.memory.MemoryStorage.
    
    ⚠️ Данные хранятся в памяти процесса.
    При перезапуске функции в Serverless - всё сбрасывается.
    Для продакшена используйте Redis/YDB.
    """

    def __init__(self) -> None:
        # state_storage: {key: state_name}
        self._state_storage: Dict[str, str] = {}
        # data_storage: {key: {data}}
        self._data_storage: Dict[str, Dict[str, Any]] = {}

    def set_state(self, key: str, state: Optional[str]) -> None:
        if state is None:
            self._state_storage.pop(key, None)
        else:
            self._state_storage[key] = state

    def get_state(self, key: str) -> Optional[str]:
        return self._state_storage.get(key)

    def set_data(self, key: str, data: Dict[str, Any]) -> None:
        self._data_storage[key] = dict(data)

    def get_data(self, key: str) -> Dict[str, Any]:
        return dict(self._data_storage.get(key, {}))

    def update_data(self, key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        current = self._data_storage.get(key, {})
        current.update(data)
        self._data_storage[key] = current
        return dict(current)

    def clear(self, key: str) -> None:
        self._state_storage.pop(key, None)
        self._data_storage.pop(key, None)

    def clear_state(self, key: str) -> None:
        self._state_storage.pop(key, None)

    def close(self) -> None:
        self._state_storage.clear()
        self._data_storage.clear()

    def __repr__(self) -> str:
        return f"MemoryStorage(states={len(self._state_storage)}, data_keys={len(self._data_storage)})"