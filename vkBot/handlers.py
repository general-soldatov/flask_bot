import re
from typing import Any, Optional
from .filters import BaseFilter, StateFilter, Command
from .types import Message, MessageEventObject
from .fsm.state import State


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

class MessageHandler:
    def __init__(self, router):
        self.router = router
        self.router_filters = []

    # def filter(self, *filters: Any):
    #     self.router_filters.extend(filters); return self

    # def register(self, handler_func, *filters, text=None):
    #     def event_filter(event: Message) -> bool:
    #         if text and event.text.lower() != text.lower(): return False
    #         for f in filters:
    #             if isinstance(f, (BaseFilter, StateFilter, Command)):
    #                 if not f(event): return False
    #             elif callable(f):
    #                 if not f(event): return False
    #         return True
    #     self.router.handlers.append((event_filter, handler_func))
    #     return handler_func

    def __call__(self, *filters):
        def decorator(handler_func): 
            # Преобразуем State в StateFilter автоматически
            normalized = []
            for f in filters:
                if isinstance(f, State):
                    normalized.append(StateFilter(f))
                else:
                    normalized.append(f)
            combined = self._combine_filters(normalized)
            self.router.handlers.append((combined, handler_func))
            return handler_func
        return decorator

    def _combine_filters(self, filters):
        def combined(event):
            merged_data = {}
            for f in filters:
                if isinstance(f, BaseFilter):
                    result = f(event)
                elif callable(f):
                    result = f(event)
                else:
                    continue

                if result is False:
                    return False
                if isinstance(result, dict):
                    merged_data.update(result)
            return merged_data if merged_data else True
        return combined

class CallbackQueryHandler:
    def __init__(self, router):
        self.router = router
        self.router_filters = []  # Список общих фильтров роутера

    def filter(self, *filters: Any):
        """Метод для привязки фильтров ко всему роутеру"""
        self.router_filters.extend(filters)
        return self

    def register(self, handler_func, *filters):
        def callback_filter(callback_query: MessageEventObject) -> bool:
            for f in filters:
                if callable(f):
                    if not f(callback_query):
                        return False
                    return True
                
        self.router.callback_handlers.append((callback_filter, handler_func))
        return handler_func

    def __call__(self, *filters):
        def decorator(handler_func):
            self.register(handler_func, *filters)
            return handler_func
        return decorator
