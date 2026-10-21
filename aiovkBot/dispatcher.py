import asyncio
import inspect
import logging
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from ._utils import KeyedLocks, TTLSet
from .bot import Bot
from .filters import BaseFilter
from .fsm.context import FSMContext
from .fsm.storage.base import BaseStorage
from .fsm.storage.memory import MemoryStorage
from .handlers import CallbackQueryHandler, MessageHandler, run_filters
from .types import Message, MessageEntity, MessageEventObject, VKEventType

logger = logging.getLogger(__name__)


class InvalidSecret(Exception):
    """Секретный ключ в событии не совпал с настроенным."""


class Router:
    def __init__(self, name='router'):
        self.handlers = []
        self.callback_handlers = []
        self.name = name
        self.message = MessageHandler(self)
        self.callback_query = CallbackQueryHandler(self)


class Dispatcher(Router):
    """
    Асинхронный диспетчер. Один и тот же код обрабатывает события из любого источника:

        * вебхук (Callback API):  ``await dp.feed_webhook(body)``  /  ``vkBot.webhook``
        * serverless:             ``dp.handler(event, context)``
        * Long Poll:              ``await dp.start_polling()``  /  ``dp.run_polling()``
        * что угодно своё:        ``await dp.feed_update(update)``

    Args:
        confirmation_code: строка подтверждения сервера Callback API.
        secret: секретный ключ Callback API (проверяется у каждого события).
        max_concurrent_updates: сколько событий обрабатывается одновременно.
        workflow_data: произвольные зависимости (db, config...), которые
            подставляются в хендлеры по имени параметра.
    """

    def __init__(self, bot: Bot, name='dispatcher',
                 storage: Optional[BaseStorage] = None, *,
                 confirmation_code: Optional[str] = None,
                 secret: Optional[str] = None,
                 max_concurrent_updates: int = 100,
                 **workflow_data: Any) -> None:
        super().__init__(name)
        self.storage = storage if storage is not None else MemoryStorage()
        self.bot = bot
        self.routers = [self]
        self.confirmation_code = confirmation_code
        self.secret = secret
        self.max_concurrent_updates = max_concurrent_updates
        self.workflow_data = workflow_data

        self._locks = KeyedLocks()
        self._seen_events = TTLSet(ttl=300)
        self._tasks: Set[asyncio.Task] = set()
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._semaphore_loop: Optional[asyncio.AbstractEventLoop] = None
        self._startup: List[Callable[..., Awaitable]] = []
        self._shutdown: List[Callable[..., Awaitable]] = []
        self._started = False
        self._poller = None

    # ------------------------------------------------------------------ роутеры
    def include_router(self, router):
        self.routers.append(router)

    def include_routers(self, *args):
        for item in args:
            self.include_router(item)

    # ------------------------------------------------------------------ жизненный цикл
    def on_startup(self, func):
        """Декоратор: ``@dp.on_startup async def init(): ...`` (пул БД и т.п.)."""
        self._startup.append(func)
        return func

    def on_shutdown(self, func):
        self._shutdown.append(func)
        return func

    async def startup(self) -> None:
        if self._started:
            return
        self._started = True
        for func in self._startup:
            await func()

    async def shutdown(self, timeout: float = 10.0) -> None:
        """Дожидается текущих обработчиков, вызывает on_shutdown, закрывает bot и storage."""
        if self._tasks:
            _, pending = await asyncio.wait(set(self._tasks), timeout=timeout)
            for task in pending:
                task.cancel()
        for func in self._shutdown:
            try:
                await func()
            except Exception:
                logger.exception("Ошибка в on_shutdown")
        await self.bot.close()
        await self.storage.close()
        self._started = False

    # ------------------------------------------------------------------ обработка события
    def _resolve_fsm_key(self, vk_body: dict) -> str:
        """Ключ FSM: для VK используем from_id / user_id."""
        if vk_body['type'] == VKEventType.MESSAGE_NEW:
            return str(vk_body['object']['message']['from_id'])
        elif vk_body['type'] == VKEventType.MESSAGE_EVENT:
            return str(vk_body['object']['user_id'])
        return "unknown"

    async def feed_update(self, vk_body: Dict[str, Any],
                          context_data: Optional[dict] = None,
                          storage: Optional[BaseStorage] = None):
        """
        Обрабатывает одно событие VK (dict вида {"type": ..., "object": ...}).
        События одного пользователя выполняются последовательно, разных — параллельно.
        Возвращает результат сработавшего хендлера.
        """
        if storage is not None:
            self.storage = storage

        event_type = vk_body.get('type')
        if event_type == VKEventType.MESSAGE_NEW:
            event = Message(**vk_body['object']['message'])
            callback = False
        elif event_type == VKEventType.MESSAGE_EVENT:
            event = MessageEventObject(**vk_body['object'])
            callback = True
        else:
            logger.debug("Необрабатываемый тип события: %s", event_type)
            return None

        event.bot = self.bot
        fsm_key = self._resolve_fsm_key(vk_body)
        fsm_context = FSMContext(self.storage, fsm_key)
        event._fsm_context = fsm_context

        # Свой словарь на каждое событие (в исходнике mutable default делился между запросами)
        data = {
            **self.workflow_data, **(context_data or {}),
            'bot': self.bot, 'state': fsm_context,
            'fsm_context': fsm_context, 'fsm_key': fsm_key,
        }

        async with self._locks(fsm_key):
            return await self._dispatch(event, data, callback)

    async def _dispatch(self, event, data: dict, callback: bool):
        for router in self.routers:
            if not await self._check_router_filters(router, event, callback):
                continue
            handlers = router.callback_handlers if callback else router.handlers
            for handler in handlers:
                result = await handler.check(event)
                if result is None:
                    continue
                local = {**data, 'router_name': router.name, **result}
                return await handler.call(event, local)
        return None

    async def _check_router_filters(self, router: Router, obj, callback=False) -> bool:
        """Проверка фильтров роутера"""
        observer = router.callback_query if callback else router.message
        return await run_filters(observer.router_filters, obj) is not None

    # ------------------------------------------------------------------ фоновая обработка
    def _get_semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if self._semaphore is None or self._semaphore_loop is not loop:
            self._semaphore = asyncio.Semaphore(self.max_concurrent_updates)
            self._semaphore_loop = loop
        return self._semaphore

    async def _process(self, update: dict, context_data: Optional[dict] = None) -> None:
        async with self._get_semaphore():
            try:
                await self.feed_update(update, context_data)
            except Exception:
                logger.exception("Ошибка обработки события %s", update.get('type'))

    def spawn_update(self, update: dict, context_data: Optional[dict] = None) -> asyncio.Task:
        """Запускает обработку в фоне (не блокирует приём следующих событий)."""
        task = asyncio.get_running_loop().create_task(self._process(update, context_data))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # ------------------------------------------------------------------ вебхук
    async def feed_webhook(self, update: Dict[str, Any], *, background: bool = True,
                           context_data: Optional[dict] = None) -> str:
        """
        Ядро Callback API, не привязанное к веб-фреймворку.
        Возвращает текст ответа для VK: ``"ok"`` либо строку подтверждения.

        * confirmation — отдаёт confirmation_code;
        * secret — если задан, проверяется (иначе InvalidSecret);
        * повторы (VK ретраит, если не получил "ok" за 5 с) отбрасываются по event_id;
        * background=True — сразу отвечаем "ok", обработка идёт в фоне (для долгоживущего
          сервера); False — ждём завершения (serverless: после ответа процесс замораживается).
        """
        if not isinstance(update, dict) or 'type' not in update:
            logger.warning("Получен body без 'type': %r", update)
            return "ok"

        if update['type'] == VKEventType.CONFIRMATION:
            if not self.confirmation_code:
                logger.error("Пришёл confirmation, но confirmation_code не задан")
            return self.confirmation_code or ""

        if self.secret and update.get('secret') != self.secret:
            raise InvalidSecret()

        event_id = update.get('event_id')
        if event_id and not self._seen_events.add_if_new(event_id):
            logger.info("Повтор события %s — пропускаем", event_id)
            return "ok"

        if background:
            self.spawn_update(update, context_data)
        else:
            await self._process(update, context_data)
        return "ok"

    # ------------------------------------------------------------------ serverless
    async def ahandler(self, event, context=None, context_data: Optional[dict] = None,
                       storage: Optional[BaseStorage] = None) -> dict:
        """Async-версия точки входа Cloud Function / Lambda."""
        from .webhook import extract_bodies

        if storage is not None:
            self.storage = storage
        try:
            bodies = extract_bodies(event)
            if not bodies:
                logger.warning("Не найдено ни одного VK сообщения в event")
                logger.info("Содержимое event: %s", str(event)[:500])
                return {"statusCode": 200, "body": "ok"}

            await self.startup()
            answers = []
            for body in bodies:
                answers.append(await self.feed_webhook(body, background=False,
                                                       context_data=context_data))
            # если был confirmation — вернём его код, иначе "ok"
            return {"statusCode": 200, "body": next((a for a in answers if a != "ok"), "ok")}
        except InvalidSecret:
            return {"statusCode": 403, "body": "invalid secret"}
        except Exception as e:
            logger.error(f"Handler error: {e}", exc_info=True)
            return {"statusCode": 200, "body": "ok"}  # 200, чтобы VK не ретраил
        finally:
            # каждый вызов — свой event loop, сессию нужно закрыть до его остановки
            await self.bot.close()

    def handler(self, event, context=None, context_data: Optional[dict] = None,
                storage: Optional[BaseStorage] = None) -> dict:
        """Синхронная точка входа для serverless: ``handler = dp.handler``."""
        return asyncio.run(self.ahandler(event, context, context_data, storage))

    # ------------------------------------------------------------------ long poll
    async def start_polling(self, *, group_id: Optional[int] = None, wait: int = 25,
                            setup: bool = True) -> None:
        """
        Запускает Bots Long Poll и работает, пока не будет вызван stop_polling()
        или отменена задача. См. vkBot.longpoll.LongPoll.
        """
        from .longpoll import LongPoll

        self._poller = LongPoll(self, group_id=group_id, wait=wait, setup=setup)
        await self.startup()
        try:
            await self._poller.run()
        finally:
            await self.shutdown()

    async def stop_polling(self) -> None:
        if self._poller is not None:
            self._poller.stop()

    def run_polling(self, **kwargs) -> None:
        """Блокирующий запуск лонгполлинга (Ctrl+C — корректная остановка)."""
        try:
            asyncio.run(self.start_polling(**kwargs))
        except KeyboardInterrupt:
            pass

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
