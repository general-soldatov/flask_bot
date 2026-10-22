import asyncio
import json
import logging
import random
from typing import Any, Dict, List, Optional, Union

from ._utils import RateLimiter
from .types import User

logger = logging.getLogger(__name__)

Keyboard = Union[str, Any]  # JSON-строка или InlineKeyboard/ReplyKeyboard (объект с as_markup())


def _kb(keyboard: Optional[Keyboard]) -> Optional[str]:
    """Принимаем и готовый JSON, и объект клавиатуры."""
    if keyboard is None:
        return None
    return keyboard.as_markup() if hasattr(keyboard, "as_markup") else keyboard


class Bot:
    """
    Асинхронный клиент VK API от имени сообщества (на базе aiovk).

    Используйте как async context manager или вызывайте ``await bot.close()``:

        async with Bot(token) as bot:
            await bot.send_message(peer_id, "Привет!")

    Сессия aiovk создаётся лениво и пересоздаётся, если сменился event loop —
    это нужно для serverless, где каждый вызов делает ``asyncio.run``.
    """

    def __init__(
        self,
        token: str,
        api_version: str = "5.131",
        *,
        group_id: Optional[int] = None,
        requests_per_second: int = 20,
        raise_on_error: bool = False,
    ):
        """
        Args:
            group_id: ID сообщества; если не задан — определяется через groups.getById.
            requests_per_second: клиентский лимит (у токена сообщества у VK — 20/с).
            raise_on_error: False (как в исходной библиотеке) — ошибки VK API логируются,
                высокоуровневые методы возвращают None; True — исключения пробрасываются.
        """
        self.token = token
        self.api_version = api_version
        self.group_id = group_id
        self.raise_on_error = raise_on_error
        self._limiter = RateLimiter(rate=requests_per_second)
        self._session = None
        self._api = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------ транспорт
    def _get_api(self):
        loop = asyncio.get_running_loop()
        if self._api is None or self._loop is not loop:
            try:
                from aiovk import API, TokenSession
            except ImportError as exc:  # pragma: no cover
                raise ImportError("Для работы Bot нужен пакет aiovk: pip install aiovk") from exc

            # Сессия старого (закрытого) loop бесполезна — просто заменяем.
            self._session = TokenSession(access_token=self.token)
            # aiovk подставляет версию из атрибута сессии.
            self._session.API_VERSION = self.api_version
            self._api = API(self._session)
            self._loop = loop
        return self._api

    async def close(self) -> None:
        """Закрыть HTTP-сессию aiovk."""
        session, self._session, self._api = self._session, None, None
        if session is not None and self._loop is asyncio.get_running_loop():
            await session.close()

    async def __aenter__(self) -> "Bot":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def call(self, method: str, **params: Any) -> Any:
        """
        Вызов произвольного метода VK API: ``await bot.call("messages.send", ...)``.
        Параметры со значением None отбрасываются. Исключения пробрасываются.
        Повторяет запрос при ошибке 6 (слишком много запросов) и таймауте сети.
        """
        params = {k: v for k, v in params.items() if v is not None}
        attempts = 3
        for attempt in range(1, attempts + 1):
            await self._limiter.acquire()
            target = self._get_api()
            for part in method.split("."):
                target = getattr(target, part)
            try:
                return await target(**params)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                retryable = getattr(exc, "error_code", None) == 6 or isinstance(exc, asyncio.TimeoutError)
                if retryable and attempt < attempts:
                    await asyncio.sleep(0.4 * attempt)
                    continue
                raise

    async def _request(self, method: str, **params: Any) -> Any:
        """call() + политика ошибок высокоуровневых методов."""
        try:
            return await self.call(method, **params)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            logger.error(f"Ошибка при вызове {method}: {err}")
            if self.raise_on_error:
                raise
            return None

    # ------------------------------------------------------------------ сообщения
    async def send_message(
        self,
        peer_id: int,
        message: Optional[str] = None,
        attachment: Optional[str] = None,
        reply_to: Optional[int] = None,
        forward: Optional[str] = None,
        keyboard: Optional[Keyboard] = None,
        sticker_id: Optional[int] = None,
        payload: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Отправляет сообщение от имени сообщества.

        Args:
            peer_id: ID получателя (пользователя или чата)
            message: Текст сообщения
            attachment: Вложения (photo123_456, video456_789 и т.д.)
            reply_to: ID сообщения, на которое отвечаем (для ЛС)
            forward: Пересылаемые сообщения (json строка)
            keyboard: Клавиатура (json строка или объект клавиатуры)
            sticker_id: ID стикера
            payload: Полезная нагрузка (json строка)
        """
        response = await self._request(
            "messages.send",
            peer_id=peer_id,
            random_id=random.randint(-2_147_483_648, 2_147_483_647),
            message=message or None,
            attachment=attachment or None,
            reply_to=reply_to or None,
            forward=forward or None,
            keyboard=_kb(keyboard) or None,
            sticker_id=sticker_id or None,
            payload=payload or None,
        )
        if response is not None:
            logger.info(f"Успешный ответ от vk.messages.send: {response}")
        return response

    async def send_message_with_forward(
        self,
        peer_id: int,
        message: str,
        forward_message_ids: List[int],
        is_reply: bool = True,
    ) -> Optional[Any]:
        """Отправляет сообщение с пересылкой/цитированием."""
        forward = json.dumps({
            "peer_id": peer_id,
            "conversation_message_ids": forward_message_ids,
            "is_reply": is_reply,
        })
        return await self.send_message(peer_id=peer_id, message=message, forward=forward)

    async def send_message_reply(
        self,
        peer_id: int,
        conversation_message_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
    ) -> Optional[Any]:
        """Отправка сообщения с цитированием (Reply) оригинального сообщения."""
        forward = json.dumps({
            "peer_id": peer_id,
            "conversation_message_ids": [conversation_message_id],
            "is_reply": True,
        })
        return await self.send_message(peer_id, text, forward=forward, keyboard=keyboard)

    async def edit_message(
        self,
        peer_id: int,
        message_id: Optional[int],
        cmid: Optional[int],
        new_message: str,
        keyboard: Optional[Keyboard] = None,
    ) -> Optional[Any]:
        """
        Редактирует сообщение. VK требует ровно один идентификатор:
        если передан cmid (conversation_message_id) — используется он
        (событие message_event приносит только его), иначе message_id.
        """
        return await self._request(
            "messages.edit",
            peer_id=peer_id,
            message=new_message,
            keyboard=_kb(keyboard),
            conversation_message_id=cmid,
            message_id=None if cmid else message_id,
        )

    async def send_typing_status(self, peer_id: int, activity_type: str = "typing") -> Optional[Any]:
        """Статус «печатает...»."""
        return await self._request("messages.setActivity", peer_id=peer_id, type=activity_type)

    async def send_callback_answer(
        self,
        event_id: str,
        peer_id: int,
        user_id: int,
        text_snackbar: Optional[str] = None,
        event_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """
        Ответ на нажатие callback-кнопки (обязателен, иначе у кнопки крутится
        индикатор загрузки). text_snackbar — всплывающая подсказка;
        event_data — произвольное действие (open_link, open_app).
        """
        if text_snackbar and event_data is None:
            event_data = {"type": "show_snackbar", "text": text_snackbar}
        return await self._request(
            "messages.sendMessageEventAnswer",
            event_id=event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=json.dumps(event_data, ensure_ascii=False) if event_data else None,
        )

    # ------------------------------------------------------------------ пользователи / группа
    async def get_vk_user_info(self, user_id: int) -> Optional[User]:
        """users.get -> User"""
        response = await self._request(
            "users.get", user_ids=user_id, fields="photo_50,city,screen_name,sex"
        )
        logger.info(f"Ответ от метода users.get: {response}")
        if response and isinstance(response, list):
            return User.load(**response[0])
        return None

    async def get_group_id(self) -> int:
        """ID сообщества: из конструктора либо через groups.getById (результат кэшируется)."""
        if self.group_id is None:
            response = await self.call("groups.getById")
            # В новых версиях API ответ — {"groups": [...]}, в старых — список.
            groups = response.get("groups", []) if isinstance(response, dict) else response
            self.group_id = int(groups[0]["id"])
        return self.group_id

    # ------------------------------------------------------------------ Bots Long Poll
    async def get_long_poll_server(self, group_id: Optional[int] = None) -> Dict[str, Any]:
        """groups.getLongPollServer -> {"key", "server", "ts"}"""
        return await self.call("groups.getLongPollServer", group_id=group_id or await self.get_group_id())

    async def setup_long_poll(
        self,
        group_id: Optional[int] = None,
        events: tuple = ("message_new", "message_event"),
    ) -> None:
        """
        Включает Long Poll API в сообществе и подписывает на нужные события
        (groups.setLongPollSettings). Версия API в настройках должна быть >= 5.103,
        иначе message_new придёт в старом формате без обёртки "message".
        """
        params = {event: 1 for event in events}
        await self.call(
            "groups.setLongPollSettings",
            group_id=group_id or await self.get_group_id(),
            enabled=1,
            api_version=self.api_version,
            **params,
        )
