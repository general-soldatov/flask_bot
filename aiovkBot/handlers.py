import inspect
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from .filters import BaseFilter, StateFilter
from .fsm.state import State

logger = logging.getLogger(__name__)

class MagicFilter:
    def __init__(self, path=None):
        self._path = path if path is not None else []

    def __getattr__(self, name: str):
        return MagicFilter(self._path + [('attr', name)])

    def __eq__(self, other: Any):
        return MagicFilter(self._path + [('op', 'eq', other)])

    def __ne__(self, other: Any):
        return MagicFilter(self._path + [('op', 'ne', other)])

    def startswith(self, prefix: str):
        return MagicFilter(self._path + [('op', 'startswith', prefix)])

    def endswith(self, suffix: str):
        return MagicFilter(self._path + [('op', 'endswith', suffix)])

    def contains(self, substring: str):
        return MagicFilter(self._path + [('op', 'contains', substring)])

    def in_(self, items: list):
        return MagicFilter(self._path + [('op', 'in', items)])

    def match(self, pattern: str, flags: int = 0):
        """Проверка соответствия регулярному выражению"""
        return MagicFilter(self._path + [('op', 'match', pattern, flags)])

    def __call__(self, obj: Any) -> bool:
        """Основной метод фильтрации с поддержкой строковых методов"""
        current_value = obj
        
        for action_type, *args in self._path:
            if action_type == 'attr':
                attr_name = args[0]
                
                # Если это строка и запрашивается метод строки
                if isinstance(current_value, str) and hasattr(str, attr_name):
                    # Сохраняем метод для дальнейшего вызова
                    method = getattr(current_value, attr_name)
                    if callable(method):
                        # Если это метод, вызываем его без аргументов
                        try:
                            current_value = method()
                        except TypeError:
                            # Если метод требует аргументов, пытаемся вызвать с пустыми
                            current_value = method()
                    else:
                        current_value = method
                elif hasattr(current_value, attr_name):
                    attr = getattr(current_value, attr_name)
                    if callable(attr):
                        try:
                            current_value = attr()
                        except TypeError:
                            # Если метод требует аргументов
                            current_value = attr
                    else:
                        current_value = attr
                else:
                    return False
                    
            elif action_type == 'method':
                method_name, m_args, m_kwargs = args[0], args[1], args[2]
                if hasattr(current_value, method_name):
                    method = getattr(current_value, method_name)
                    if callable(method):
                        try:
                            current_value = method(*m_args, **m_kwargs)
                        except Exception:
                            return False
                    else:
                        return False
                else:
                    return False
                    
            elif action_type == 'op':
                if len(args) >= 2:
                    op_type, target_value = args[0], args[1]
                    additional_args = args[2:] if len(args) > 2 else []
                    
                    if op_type == 'eq':
                        return current_value == target_value
                    elif op_type == 'ne':
                        return current_value != target_value
                    elif op_type == 'startswith':
                        if isinstance(current_value, str):
                            return current_value.startswith(target_value)
                        return False
                    elif op_type == 'endswith':
                        if isinstance(current_value, str):
                            return current_value.endswith(target_value)
                        return False
                    elif op_type == 'contains':
                        if isinstance(current_value, str):
                            return target_value in current_value
                        return False
                    elif op_type == 'in':
                        return current_value in target_value
                    elif op_type == 'match':
                        if isinstance(current_value, str):
                            flags = additional_args[0] if additional_args else 0
                            return bool(re.match(target_value, current_value, flags))
                        return False
        
        return bool(current_value)

    def lower(self):
        """Перевод строки в нижний регистр"""
        return MagicFilter(self._path + [('method', 'lower', [], {})])

    def upper(self):
        """Перевод строки в верхний регистр"""
        return MagicFilter(self._path + [('method', 'upper', [], {})])

    def strip(self, chars: Optional[str] = None):
        """Удаление пробельных символов в начале и конце строки"""
        return MagicFilter(self._path + [('method', 'strip', [chars] if chars else [], {})])

    def lstrip(self, chars: Optional[str] = None):
        """Удаление пробельных символов в начале строки"""
        return MagicFilter(self._path + [('method', 'lstrip', [chars] if chars else [], {})])

    def rstrip(self, chars: Optional[str] = None):
        """Удаление пробельных символов в конце строки"""
        return MagicFilter(self._path + [('method', 'rstrip', [chars] if chars else [], {})])

    def replace(self, old: str, new: str, count: int = -1):
        """Замена подстроки"""
        return MagicFilter(self._path + [('method', 'replace', [old, new, count], {})])

    def title(self):
        """Преобразование в заглавные буквы"""
        return MagicFilter(self._path + [('method', 'title', [], {})])

    def capitalize(self):
        """Преобразование первой буквы в заглавную"""
        return MagicFilter(self._path + [('method', 'capitalize', [], {})])

    def casefold(self):
        """Агрессивное приведение к нижнему регистру"""
        return MagicFilter(self._path + [('method', 'casefold', [], {})])

    def swapcase(self):
        """Инвертирование регистра"""
        return MagicFilter(self._path + [('method', 'swapcase', [], {})])

    # Комбинированные методы для сложных проверок

    def lower_eq(self, other: str):
        """Проверка равенства после приведения к нижнему регистру"""
        return MagicFilter(self._path + [('method', 'lower', [], {}), ('op', 'eq', other)])

    def upper_eq(self, other: str):
        """Проверка равенства после приведения к верхнему регистру"""
        return MagicFilter(self._path + [('method', 'upper', [], {}), ('op', 'eq', other)])

    def strip_eq(self, other: str, chars: Optional[str] = None):
        """Проверка равенства после удаления пробелов"""
        args = [chars] if chars else []
        return MagicFilter(self._path + [('method', 'strip', args, {}), ('op', 'eq', other)])

    def startswith_ignore_case(self, prefix: str):
        """Проверка начала строки без учета регистра"""
        return MagicFilter(self._path + [
            ('method', 'lower', [], {}),
            ('op', 'startswith', prefix.lower())
        ])

    def endswith_ignore_case(self, suffix: str):
        """Проверка конца строки без учета регистра"""
        return MagicFilter(self._path + [
            ('method', 'lower', [], {}),
            ('op', 'endswith', suffix.lower())
        ])

    def contains_ignore_case(self, substring: str):
        """Проверка содержания подстроки без учета регистра"""
        return MagicFilter(self._path + [
            ('method', 'lower', [], {}),
            ('op', 'contains', substring.lower())
        ])


async def run_filters(filters, event) -> Optional[Dict[str, Any]]:
    """
    Прогоняет фильтры (sync или async). Возвращает None, если событие не подошло,
    иначе dict с данными, которые фильтры хотят передать хендлеру (может быть пустым).
    Исключение внутри фильтра логируется и считается «не подошло».
    """
    merged: Dict[str, Any] = {}
    for f in filters:
        try:
            result = f(event)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            logger.exception("Ошибка в фильтре %r", f)
            return None
        if isinstance(result, dict):
            merged.update(result)
        elif not result:
            return None
    return merged


class HandlerObject:
    """Хендлер + его фильтры. Сигнатура анализируется один раз при регистрации."""
    __slots__ = ("callback", "filters", "_params", "_var_kw")

    def __init__(self, callback: Callable, filters: List[Any]):
        if not (inspect.iscoroutinefunction(callback)
                or inspect.iscoroutinefunction(getattr(callback, "__call__", None))):
            raise TypeError(
                f"Хендлер {getattr(callback, '__name__', callback)!r} должен быть "
                f"асинхронным (async def)"
            )
        self.callback = callback
        self.filters = filters
        params = list(inspect.signature(callback).parameters.values())
        self._var_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params)
        # первый позиционный параметр — само событие, остальные подставляем по имени
        self._params = {
            p.name for p in params[1:]
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }

    async def check(self, event) -> Optional[Dict[str, Any]]:
        return await run_filters(self.filters, event)

    async def call(self, event, data: Dict[str, Any]):
        kwargs = data if self._var_kw else {k: v for k, v in data.items() if k in self._params}
        return await self.callback(event, **kwargs)


class _Observer:
    """Общая логика регистрации хендлеров (декоратор, фильтры роутера)."""
    _target = "handlers"

    def __init__(self, router):
        self.router = router
        self.router_filters: list = []  # Общие фильтры роутера

    def filter(self, *filters: Any):
        """Привязывает фильтры ко всему роутеру."""
        self.router_filters.extend(filters)
        return self

    def register(self, handler_func, *filters):
        # State автоматически превращаем в StateFilter
        normalized = [StateFilter(f) if isinstance(f, State) else f for f in filters]
        getattr(self.router, self._target).append(HandlerObject(handler_func, normalized))
        return handler_func

    def __call__(self, *filters):
        def decorator(handler_func):
            return self.register(handler_func, *filters)
        return decorator


class MessageHandler(_Observer):
    _target = "handlers"


class CallbackQueryHandler(_Observer):
    _target = "callback_handlers"
