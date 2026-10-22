"""Небольшие asyncio-утилиты: rate limiter, пер-ключевые блокировки, TTL-дедупликация."""
import asyncio
import time
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from typing import Dict, List, Optional


class RateLimiter:
    """
    Скользящее окно: не более ``rate`` вызовов за ``per`` секунд.
    У токена сообщества лимит VK — 20 запросов в секунду.

    Lock создаётся отдельно под каждый event loop: в serverless-режиме
    (``asyncio.run`` на каждый вызов) объект переживает loop.
    """

    def __init__(self, rate: int = 20, per: float = 1.0) -> None:
        self.rate = rate
        self.per = per
        self._calls: deque = deque()
        self._lock: Optional[asyncio.Lock] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def acquire(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._loop, self._lock = loop, asyncio.Lock()
            self._calls.clear()
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self.per:
                    self._calls.popleft()
                if len(self._calls) < self.rate:
                    self._calls.append(now)
                    return
                await asyncio.sleep(self.per - (now - self._calls[0]))


class KeyedLocks:
    """
    Блокировка по ключу (user_id): события одного пользователя обрабатываются
    строго по очереди (важно для FSM), разных — параллельно.
    Неиспользуемые блокировки удаляются сразу, память не растёт.
    """

    def __init__(self) -> None:
        self._locks: Dict[str, List] = {}

    @asynccontextmanager
    async def __call__(self, key: str):
        entry = self._locks.get(key)
        if entry is None:
            entry = self._locks[key] = [asyncio.Lock(), 0]
        entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if entry[1] == 0:
                self._locks.pop(key, None)


class TTLSet:
    """Множество с временем жизни записей — дедупликация повторов вебхука по event_id."""

    def __init__(self, ttl: float = 300.0, maxsize: int = 10_000) -> None:
        self.ttl = ttl
        self.maxsize = maxsize
        self._items: "OrderedDict[str, float]" = OrderedDict()

    def add_if_new(self, key: str) -> bool:
        """True — ключ новый (и теперь запомнен); False — уже встречался."""
        now = time.monotonic()
        while self._items:
            oldest, expires = next(iter(self._items.items()))
            if expires <= now or len(self._items) > self.maxsize:
                self._items.popitem(last=False)
            else:
                break
        if key in self._items:
            return False
        self._items[key] = now + self.ttl
        return True
