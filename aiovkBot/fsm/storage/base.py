from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseStorage(ABC):
    """
    Абстрактное асинхронное хранилище состояний.
    Все методы — корутины (Redis/MySQL/YDB-хранилища не блокируют event loop).
    """

    @abstractmethod
    async def set_state(self, key: str, state: Optional[str]) -> None:
        """Установить состояние"""

    @abstractmethod
    async def get_state(self, key: str) -> Optional[str]:
        """Получить состояние"""

    @abstractmethod
    async def set_data(self, key: str, data: Dict[str, Any]) -> None:
        """Установить данные (полностью перезаписать)"""

    @abstractmethod
    async def get_data(self, key: str) -> Dict[str, Any]:
        """Получить данные"""

    @abstractmethod
    async def update_data(self, key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновить данные (слияние)"""

    @abstractmethod
    async def clear(self, key: str) -> None:
        """Очистить состояние и данные"""

    @abstractmethod
    async def clear_state(self, key: str) -> None:
        """Очистить только состояние (данные оставить)"""

    async def close(self) -> None:
        """Закрытие хранилища (опционально)"""
