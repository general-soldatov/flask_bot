"""Bots Long Poll: получение событий без публичного адреса и HTTPS."""
import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LongPoll:
    """
    Цикл Bots Long Poll поверх Bot (aiovk) и Dispatcher.

    * получает сервер через groups.getLongPollServer;
    * обрабатывает ошибки ``failed`` (1 — обновить ts, 2 — ключ, 3 — ключ и ts);
    * при сетевых сбоях — экспоненциальная пауза (до 30 с);
    * события уходят в фоновые задачи диспетчера, поэтому долгий хендлер
      не задерживает опрос; порядок событий одного пользователя сохраняется.
    """

    def __init__(self, dp, group_id: Optional[int] = None, wait: int = 25, setup: bool = True):
        self.dp = dp
        self.bot = dp.bot
        self.group_id = group_id
        self.wait = wait
        self.setup = setup
        self.server: Optional[str] = None
        self.key: Optional[str] = None
        self.ts: Optional[str] = None
        self._stopping = False
        self._request: Optional[asyncio.Future] = None

    def stop(self) -> None:
        self._stopping = True
        if self._request is not None and not self._request.done():
            self._request.cancel()

    async def _refresh(self, *, update_ts: bool = True) -> None:
        data = await self.bot.get_long_poll_server(self.group_id)
        self.server, self.key = data["server"], data["key"]
        if update_ts:
            self.ts = data["ts"]

    async def _fetch(self, session, params: Dict[str, Any]) -> Dict[str, Any]:
        async with session.get(self.server, params=params) as resp:
            return await resp.json(content_type=None)

    async def run(self) -> None:
        import aiohttp

        self.group_id = self.group_id or await self.bot.get_group_id()
        if self.setup:
            await self.bot.setup_long_poll(self.group_id)
        await self._refresh()

        timeout = aiohttp.ClientTimeout(total=self.wait + 10)
        backoff = 1.0
        async with aiohttp.ClientSession(timeout=timeout) as session:
            logger.info("Long Poll запущен (group_id=%s)", self.group_id)
            while not self._stopping:
                params = {"act": "a_check", "key": self.key, "ts": self.ts, "wait": self.wait}
                try:
                    self._request = asyncio.ensure_future(self._fetch(session, params))
                    resp = await self._request
                    backoff = 1.0
                except asyncio.CancelledError:
                    if self._stopping:
                        break
                    raise
                except Exception as exc:
                    logger.warning("Long Poll: ошибка запроса (%s), повтор через %.0f с", exc, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                    continue

                if not await self._handle_response(resp):
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
        logger.info("Long Poll остановлен")

    async def _handle_response(self, resp: Dict[str, Any]) -> bool:
        """Возвращает False, если нужно сделать паузу (не удалось обновить сервер)."""
        failed = resp.get("failed")
        try:
            if failed == 1:       # история устарела — берём ts из ответа
                self.ts = resp["ts"]
            elif failed == 2:     # ключ истёк
                await self._refresh(update_ts=False)
            elif failed:          # 3 и неизвестные — всё заново
                await self._refresh()
            else:
                self.ts = resp["ts"]
                for update in resp.get("updates", []):
                    self.dp.spawn_update(update)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Long Poll: не удалось обработать ответ/обновить сервер: %s", exc)
            return False
        return True
