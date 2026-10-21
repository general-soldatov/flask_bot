"""
Приём событий Callback API.

* ``extract_bodies`` — разбор event из serverless-триггеров (формат Yandex Cloud
  Functions / API Gateway и т.п.), логика перенесена из прежнего Dispatcher.handler.
* ``setup_webhook`` / ``run_webhook`` — готовый aiohttp-сервер.
* Для FastAPI/Quart/Sanic достаточно вызвать ``await dp.feed_webhook(body)``
  и вернуть полученную строку как text/plain.
"""
import json
import logging
from typing import Any, List

from .dispatcher import Dispatcher, InvalidSecret

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- serverless: разбор event
def extract_bodies(event: Any) -> List[dict]:
    """Достаёт VK-события из разных форм serverless-event."""
    bodies: List[dict] = []

    if isinstance(event, dict) and "messages" in event:
        for msg in event.get("messages", []):
            body = _from_message(msg)
            if body:
                bodies.append(body)
    elif isinstance(event, dict) and "details" in event:
        body = _from_details(event.get("details", {}))
        if body:
            bodies.append(body)
    elif isinstance(event, dict) and "body" in event:
        body = _parse_body(event.get("body"))
        if body:
            bodies.append(body)
    elif isinstance(event, dict) and "type" in event:
        bodies.append(event)  # уже готовое событие VK
    elif isinstance(event, list):
        for item in event:
            body = _from_message(item)
            if body:
                bodies.append(body)
    elif isinstance(event, str):
        try:
            return extract_bodies(json.loads(event))
        except json.JSONDecodeError:
            pass

    return [b for b in bodies if isinstance(b, dict) and "type" in b]


def _from_message(msg):
    if isinstance(msg, dict):
        if "body" in msg:
            return _parse_body(msg["body"])
        if "details" in msg:
            return _from_details(msg["details"])
        if "message" in msg:
            return _from_message(msg["message"])
    return None


def _from_details(details):
    if isinstance(details, dict):
        msg = details.get("message")
        if isinstance(msg, dict) and "body" in msg:
            return _parse_body(msg["body"])
        if "body" in details:
            return _parse_body(details["body"])
    return None


def _parse_body(body):
    """Парсинг body с защитой от ошибок."""
    if not body:
        return None
    if isinstance(body, dict):
        return body
    if isinstance(body, str):
        body = body.strip()
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            logger.error(f"Body: {body[:200]}...")
            # Пробуем восстановить обрезанный JSON (как в исходной версии)
            if body.count('{') > body.count('}'):
                try:
                    fixed = body + '}' * (body.count('{') - body.count('}'))
                    logger.info(f"Восстановлен JSON: {fixed[:100]}...")
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass
    return None


# ---------------------------------------------------------------- aiohttp
def make_aiohttp_handler(dp: Dispatcher):
    """aiohttp-хендлер: быстро отвечает VK, обработку уводит в фон."""
    from aiohttp import web

    async def handle(request: "web.Request") -> "web.Response":
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="bad request")
        try:
            text = await dp.feed_webhook(body)
        except InvalidSecret:
            return web.Response(status=403, text="forbidden")
        return web.Response(text=text)

    return handle


def setup_webhook(app, dp: Dispatcher, path: str = "/") -> None:
    """Подключает вебхук к существующему aiohttp.web.Application."""
    app.router.add_post(path, make_aiohttp_handler(dp))

    async def _startup(_app):
        await dp.startup()

    async def _cleanup(_app):
        await dp.shutdown()

    app.on_startup.append(_startup)
    app.on_cleanup.append(_cleanup)


def run_webhook(dp: Dispatcher, host: str = "0.0.0.0", port: int = 8080, path: str = "/") -> None:
    """Блокирующий запуск aiohttp-сервера для Callback API."""
    from aiohttp import web

    app = web.Application()
    setup_webhook(app, dp, path)
    web.run_app(app, host=host, port=port)
