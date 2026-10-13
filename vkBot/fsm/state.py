from typing import Any, Optional, Dict

class State:
    __slots__ = ("_state_name", "_group_name")

    def __init__(self, state_name: Optional[str] = None) -> None: 
        self._state_name: Optional[str] = state_name
        self._group_name: Optional[str] = None

    def __set_name__(self, owner: Any, name: str) -> None:
        # Вызывается автоматически при объявлении в классе
        self._group_name = owner.__name__
        # Если state_name не задан явно - используем имя атрибута
        if self._state_name is None:
            self._state_name = name

    @property
    def state(self) -> Optional[str]: 
        if self._group_name:
            return f"{self._group_name}:{self._state_name}"
        return self._state_name or ""

    def __str__(self) -> str:
        return self.state

    def __repr__(self) -> str:
        return f"State({self.state!r})"

    def __eq__(self, other) -> bool:
        if isinstance(other, State):
            return self.state == other.state
        if isinstance(other, str):
            return self.state == other
        return False

    def __hash__(self):
        return hash(self.state)

class StatesGroupMeta(type):
    """
    Метакласс для автоматической регистрации State-атрибутов.
    """
    def __new__(mcs, name, bases, namespace, **kwargs):
        cls = super().__new__(mcs, name, bases, namespace)
        cls._states = {}
        cls._state_names = {}

        # Собираем состояния из базовых классов
        for base in bases:
            if hasattr(base, '_states'):
                cls._states.update(base._states)
                cls._state_names.update(base._state_names)

        # Собираем состояния текущего класса
        for key, value in namespace.items():
            if isinstance(value, State):
                cls._states[key] = value
                cls._state_names[value.state] = key

        return cls

    def __iter__(cls):
        """Позволяет итерироваться по состояниям группы"""
        return iter(cls._states.values())

    def __contains__(cls, item):
        """Проверка: state in GroupName"""
        if isinstance(item, State):
            return item.state in cls._state_names
        if isinstance(item, str):
            return item in cls._state_names
        return False

    def __getitem__(cls, name: str) -> State:
        """Получение состояния по имени"""
        return cls._states[name]

    def get_state(cls, state: str) -> Optional[State]:
        """Получение состояния по полному имени"""
        name = cls._state_names.get(state)
        if name:
            return cls._states[name]
        return None

    def all_states(cls) -> Dict[str, State]:
        """Все состояния группы"""
        return dict(cls._states)
    
class StatesGroup(metaclass=StatesGroupMeta): 
    """
    Группа состояний. Аналог aiogram.fsm.state.StatesGroup.
    
    Пример:
        class OrderFood(StatesGroup):
            choosing_food_name = State()
            choosing_food_size = State()
    """
    _states: Dict[str, State] = {}
    _state_names: Dict[str, str] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    @classmethod
    def get_root(cls) -> "StatesGroup":
        """Корневая группа (возвращает себя)"""
        return cls