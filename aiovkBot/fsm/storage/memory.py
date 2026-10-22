from typing import Any, Dict, Optional
from .base import BaseStorage


class MemoryStorage(BaseStorage):
    """
    In-memory хранилище состояний.

    Методы объявлены как async ради единого интерфейса, но внутри нет await,
    поэтому каждая операция атомарна в рамках одного event loop.

    ⚠️ Данные живут в памяти процесса. В serverless (Cloud Functions) и при
    нескольких воркерах состояние теряется/не разделяется — используйте
    внешнее хранилище (Redis/YDB/MySQL), унаследовав BaseStorage.
    """

    def __init__(self) -> None:
        self._state_storage: Dict[str, str] = {}
        self._data_storage: Dict[str, Dict[str, Any]] = {}

    async def set_state(self, key: str, state: Optional[str]) -> None:
        if state is None:
            self._state_storage.pop(key, None)
        else:
            self._state_storage[key] = state

    async def get_state(self, key: str) -> Optional[str]:
        return self._state_storage.get(key)

    async def set_data(self, key: str, data: Dict[str, Any]) -> None:
        self._data_storage[key] = dict(data)

    async def get_data(self, key: str) -> Dict[str, Any]:
        return dict(self._data_storage.get(key, {}))

    async def update_data(self, key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        current = self._data_storage.get(key, {})
        current.update(data)
        self._data_storage[key] = current
        return dict(current)

    async def clear(self, key: str) -> None:
        self._state_storage.pop(key, None)
        self._data_storage.pop(key, None)

    async def clear_state(self, key: str) -> None:
        self._state_storage.pop(key, None)

    async def close(self) -> None:
        self._state_storage.clear()
        self._data_storage.clear()

    def __repr__(self) -> str:
        return f"MemoryStorage(states={len(self._state_storage)}, data_keys={len(self._data_storage)})"
