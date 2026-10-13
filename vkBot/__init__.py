import re
import inspect
import json
import logging
from typing import Optional, List, Dict, Any

from .types import MessageEntity, Message, Bot, VKEventType, MessageEventObject
from .handlers import MessageHandler, MagicFilter, CallbackQueryHandler
from .fsm.storage.memory import MemoryStorage
from .fsm.context import FSMContext
from .filters import BaseFilter

logger = logging.getLogger(__name__)

F = MagicFilter()

class Router:
    def __init__(self, name='router'):
        self.handlers = []
        self.callback_handlers = []
        self.name = name
        self.message = MessageHandler(self)
        self.callback_query = CallbackQueryHandler(self)

class Dispatcher(Router):
    def __init__(self, bot: Bot, name='dispatcher',
                  storage: Optional[MemoryStorage] = None) -> None:
        super().__init__(name)
        self.storage = storage if storage is not None else MemoryStorage()
        self.bot = bot
        self.routers = [self]

    def _resolve_fsm_key(self, vk_body: dict) -> str:
        """
        Определяем ключ FSM.
        Для VK используем from_id (user_id).
        """
        if vk_body['type'] == VKEventType.MESSAGE_NEW:
            return str(vk_body['object']['message']['from_id'])
        elif vk_body['type'] == VKEventType.MESSAGE_EVENT:
            return str(vk_body['object']['user_id'])
        return "unknown"

    def run_sinc(self, vk_body: Dict[str, Any], context,
                  context_data: dict = {}, storage: Optional[MemoryStorage] = None):
        if storage:
            self.storage = storage

        # --- MESSAGE_NEW ---
        if vk_body['type'] == VKEventType.MESSAGE_NEW:
            message = Message(**vk_body['object']['message'])
            message.bot = self.bot

            fsm_key = self._resolve_fsm_key(vk_body)
            fsm_context = FSMContext(self.storage, fsm_key)
            message._fsm_context = fsm_context

            context_data.update({
                'bot': self.bot, 'state': fsm_context,
                'fsm_context': fsm_context,
                'fsm_key': fsm_key
            })
            
            for router in self.routers:     
                if not self._check_router_filters(router, message):
                    continue

                for is_match, handler in router.handlers:
                    filter_result = is_match(message)
                    context_data['router_name'] = router.name

                    if filter_result is not False:
                        if isinstance(filter_result, dict):
                            context_data.update(filter_result)

                        sig = inspect.signature(handler)
                        kwargs = {k: v for k, v in context_data.items() if k in sig.parameters}
                        return handler(message, **kwargs)

        # --- MESSAGE_EVENT ---
        elif vk_body['type'] == VKEventType.MESSAGE_EVENT:
            event = MessageEventObject(**vk_body['object'])
            event.bot = self.bot

            fsm_key = self._resolve_fsm_key(vk_body)
            fsm_context = FSMContext(self.storage, fsm_key)
            event._fsm_context = fsm_context
            # fsm_context
            context_data.update({
                'bot': self.bot, 'state': fsm_context,
                'fsm_context': fsm_context,
                'fsm_key': fsm_key
            })

            for router in self.routers:     
                # router_filters_passed = True
                # for rf in router.callback_query.router_filters:
                #     if isinstance(rf, BaseFilter):
                #         if not rf(event):
                #             router_filters_passed = False; break
                #     elif callable(rf):
                #         if not rf(event):
                #             router_filters_passed = False; break
                # if not router_filters_passed:
                #     logger.info('Unexpected filters')
                #     continue
                if not self._check_router_filters(router, event, callback=True):
                    continue

                for is_match, handler in router.callback_handlers:
                    filter_result = is_match(event)
                    context_data['router_name'] = router.name

                    if filter_result is not False:
                        if isinstance(filter_result, dict):
                            context_data.update(filter_result)
                            
                        sig = inspect.signature(handler)
                        kwargs = {k: v for k, v in context_data.items() if k in sig.parameters}
                        return handler(event, **kwargs)
                   
    def _check_router_filters(self, router: Router, obj, callback=False):
        """Проверка фильтров роутера"""
        filters = router.callback_query.router_filters if callback else router.message.router_filters

        for rf in filters:
            try: 
                if isinstance(rf, BaseFilter):
                    if not rf(obj):
                        return False
                elif callable(rf):
                    if not rf(obj):
                        return False
            except Exception as e:
                logger.error(f"Router filter error: {e}")
                return False
        return True
        

    def _extract_entities(self, text: str) -> List['MessageEntity']:
        entities = []
        patterns = {
            'bot_command': r'[/*!%$#@\\?^&*\-+=]{1,}[a-zA-Z0-9_@]+',
            'email': r'[a-zA-Z0-9\-_\.]+@[a-zA-Z0-9\-_\.]+\.[a-zA-Z]{2,}',
            'url': r'https?://[^\s]+',
            'mention': r'@[a-zA-Z0-9_]+',
            'hashtag': r'#[a-zA-Z0-9_]+',
            'code': r'<code>(.*?)<\/code>'
        }
        
        for entity_type, pattern in patterns.items():
            for match in re.finditer(pattern, text):
                start, end = match.span()
                entities.append(MessageEntity(
                    type=entity_type,
                    offset=start,
                    length=end - start
                ))
        
        return sorted(entities, key=lambda e: e.offset)

    def include_router(self, router): 
        self.routers.append(router)

    def include_routers(self, *args):
        for item in args: 
            self.include_router(item)

    def handler(self, event, context, context_data: Optional[dict] = {}, storage: Optional[MemoryStorage] = None):
        try:
            # Логируем ТИП и структуру event
            logger.info(f"Тип event: {type(event)}")
            logger.info(f"Ключи event: {list(event.keys()) if isinstance(event, dict) else 'не словарь'}")
            
            # Извлекаем все возможные body из разных структур
            vk_bodies = []
            
            # Случай 1: event - словарь с messages
            if isinstance(event, dict) and "messages" in event:
                for msg in event.get("messages", []):
                    body = self._extract_body_from_message(msg)
                    if body:
                        vk_bodies.append(body)
            
            # Случай 2: event - словарь с details (ваш случай из лога)
            elif isinstance(event, dict) and "details" in event:
                body = self._extract_body_from_details(event.get("details", {}))
                if body:
                    vk_bodies.append(body)
            
            # Случай 3: event - словарь с прямым body
            elif isinstance(event, dict) and "body" in event:
                body = self._parse_body(event.get("body"))
                if body:
                    vk_bodies.append(body)
            
            # Случай 4: event - массив
            elif isinstance(event, list):
                for item in event:
                    body = self._extract_body_from_message(item)
                    if body:
                        vk_bodies.append(body)
            
            # Случай 5: event - просто строка JSON
            elif isinstance(event, str):
                try:
                    parsed = json.loads(event)
                    # Рекурсивно обрабатываем
                    return self.handler(parsed, context)
                except:
                    pass
            
            # Обрабатываем найденные body
            if not vk_bodies:
                logger.warning("Не найдено ни одного VK сообщения в event")
                logger.info(f"Содержимое event: {str(event)[:500]}")
                return {"statusCode": 200}
            
            for vk_body in vk_bodies:
                if vk_body and isinstance(vk_body, dict):
                    # Проверяем, что это VK сообщение
                    if "type" in vk_body:
                        self.run_sinc(vk_body, context, context_data, storage)
                    else:
                        logger.warning(f"Получен body без 'type': {vk_body.keys()}")
            
            return {"statusCode": 200}
            
        except Exception as e:
            logger.error(f"Handler error: {str(e)}", exc_info=True)
            return {"statusCode": 200}

    def _extract_body_from_message(self, msg):
        """Извлечение body из сообщения"""
        if isinstance(msg, dict):
            # Прямой body
            if "body" in msg:
                return self._parse_body(msg["body"])
            
            # Вложенный body через details
            if "details" in msg:
                return self._extract_body_from_details(msg["details"])
            
            # Через message
            if "message" in msg:
                return self._extract_body_from_message(msg["message"])
        
        return None

    def _extract_body_from_details(self, details):
        """Извлечение body из details"""
        if isinstance(details, dict):
            # Прямой message
            if "message" in details:
                msg = details["message"]
                if isinstance(msg, dict) and "body" in msg:
                    return self._parse_body(msg["body"])
            
            # Прямой body
            if "body" in details:
                return self._parse_body(details["body"])
        
        return None

    def _parse_body(self, body):
        """Парсинг body с защитой от ошибок"""
        if not body:
            return None
        
        # Если уже словарь
        if isinstance(body, dict):
            return body
        
        # Если строка - парсим JSON
        if isinstance(body, str):
            body = body.strip()
            if not body:
                return None
            
            try:
                parsed = json.loads(body)
                return parsed
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON: {e}")
                logger.error(f"Body: {body[:200]}...")
                
                # Пробуем восстановить обрезанный JSON
                try:
                    # Если обрезан, добавляем закрывающие скобки
                    if body.count('{') > body.count('}'):
                        fixed = body + '}' * (body.count('{') - body.count('}'))
                        logger.info(f"Восстановлен JSON: {fixed[:100]}...")
                        return json.loads(fixed)
                except:
                    pass
                
                return None
        
        return None

