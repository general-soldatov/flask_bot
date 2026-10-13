from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseStorage(ABC):
    """
    Абстрактное хранилище состояний.
    Все методы СИНХРОННЫЕ.
    """

    @abstractmethod
    def set_state(self, key: str, state: Optional[str]) -> None:
        """Установить состояние"""
        pass

    @abstractmethod
    def get_state(self, key: str) -> Optional[str]:
        """Получить состояние"""
        pass

    @abstractmethod
    def set_data(self, key: str, data: Dict[str, Any]) -> None:
        """Установить данные (полностью перезаписать)"""
        pass

    @abstractmethod
    def get_data(self, key: str) -> Dict[str, Any]:
        """Получить данные"""
        pass

    @abstractmethod
    def update_data(self, key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновить данные (слияние)"""
        pass

    @abstractmethod
    def clear(self, key: str) -> None:
        """Очистить состояние и данные"""
        pass

    @abstractmethod
    def clear_state(self, key: str) -> None:
        """Очистить только состояние (данные оставить)"""
        pass

    def close(self) -> None:
        """Закрытие хранилища (опционально)"""
        pass