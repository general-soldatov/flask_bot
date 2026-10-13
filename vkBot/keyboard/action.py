from typing import Any, Literal
from pydantic import BaseModel

Payload = str | dict[str, Any]

class ABCAction(BaseModel):
    type: str


class Text(ABCAction):
    type: Literal["text"] = "text"
    label: str
    payload: Payload | None = None


class OpenLink(ABCAction):
    type: Literal["open_link"] = "open_link"
    link: str
    label: str
    payload: Payload | None = None


class Location(ABCAction):
    type: Literal["location"] = "location"
    payload: Payload | None = None


class VKPay(ABCAction):
    type: Literal["vkpay"] = "vkpay"
    payload: Payload | None = None  # Убрана лишняя запятая
    hash: str | None = None         # Убрана лишняя запятая


class VKApps(ABCAction):
    type: Literal["open_app"] = "open_app"
    app_id: int
    owner_id: int
    payload: Payload | None = None
    label: str | None = None
    hash: str | None = None


class Callback(ABCAction):
    type: Literal["callback"] = "callback"
    label: str
    payload: Payload


__all__ = (
    "ABCAction",
    "Callback",
    "Location",
    "OpenLink",
    "Text",
    "VKApps",
    "VKPay",
)
