import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, computed_field

from .fsm.context import FSMContext

logger = logging.getLogger(__name__)


def __getattr__(name: str):
    # Обратная совместимость: раньше Bot жил в vkBot.types
    if name == "Bot":
        from .bot import Bot
        return Bot
    raise AttributeError(name)


class PayloadAction:
    def __init__(self, *args, sep: str = '|'):
        self.data = args
        self._sep = sep

    @classmethod
    def get_payload(cls, data: str, sep: str = '|'):
        return cls(*data.split(sep))

    def dumps(self):
        return self._sep.join(self.data)


class User(BaseModel):
    first_name: str
    last_name: str
    id: int
    sex: int
    screen_name: Optional[str] = None
    can_access_closed: Optional[bool] = None
    is_closed: Optional[bool] = None
    photo_50: Optional[str] = None
    city: Optional[Dict[str, Any]] = None

    @computed_field
    @property
    def full_name(self) -> str:
        return f'{self.first_name} {self.last_name}'

    @classmethod
    def load(cls, **kwargs):
        return cls(**kwargs)


class VkBotBaseModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)


# ========== Enum для типов событий ==========
class VKEventType(str, Enum):
    CONFIRMATION = "confirmation"
    MESSAGE_NEW = "message_new"
    MESSAGE_REPLY = "message_reply"
    MESSAGE_EDIT = "message_edit"
    MESSAGE_ALLOW = "message_allow"
    MESSAGE_DENY = "message_deny"
    MESSAGE_TYPING_STATE = "message_typing_state"
    MESSAGE_EVENT = "message_event"  # Нажатие на inline кнопку


class MessageEntity:
    def __init__(self, type: str, offset: int, length: int):
        self.type = type
        self.offset = offset
        self.length = length

    def extract_from(self, text: str) -> str:
        return text[self.offset : self.offset + self.length]

# class AttachmentType(str, Enum):
#     PHOTO = "photo"
#     VIDEO = "video"
#     AUDIO = "audio"
#     DOC = "doc"
#     STICKER = "sticker"
#     GRAFFITI = "graffiti"
#     LINK = "link"
#     WALL = "wall"
#     POLL = "poll"


# class PhotoSize(BaseModel):
#     """Размер фотографии"""
#     height: int
#     width: int
#     url: str
#     type: str  # s, m, x, y, z, etc.


# class Photo(BaseModel):
#     """Фотография"""
#     id: int
#     album_id: int
#     owner_id: int
#     sizes: List[PhotoSize]
#     text: Optional[str] = ""
#     date: int
#     access_key: Optional[str] = None


# class Video(BaseModel):
#     """Видео"""
#     id: int
#     owner_id: int
#     title: str
#     description: Optional[str] = ""
#     duration: int
#     photo_130: Optional[str] = None
#     photo_320: Optional[str] = None
#     photo_800: Optional[str] = None
#     date: int
#     access_key: Optional[str] = None


# class Audio(BaseModel):
#     """Аудиозапись"""
#     id: int
#     owner_id: int
#     artist: str
#     title: str
#     duration: int
#     url: Optional[str] = None
#     lyrics_id: Optional[int] = None
#     album_id: Optional[int] = None
#     genre_id: Optional[int] = None


# class Document(BaseModel):
#     """Документ"""
#     id: int
#     owner_id: int
#     title: str
#     size: int
#     ext: str
#     url: Optional[str] = None
#     date: int
#     type: int
#     access_key: Optional[str] = None


# class Sticker(BaseModel):
#     """Стикер"""
#     product_id: int
#     sticker_id: int
#     images: Optional[List[PhotoSize]] = None
#     animation_url: Optional[str] = None


# class Link(BaseModel):
#     """Ссылка"""
#     url: str
#     title: str
#     caption: Optional[str] = None
#     description: Optional[str] = None
#     photo: Optional[Photo] = None


# class Attachment(BaseModel):
#     """Вложение"""
#     type: AttachmentType
#     photo: Optional[Photo] = None
#     video: Optional[Video] = None
#     audio: Optional[Audio] = None
#     doc: Optional[Document] = None
#     sticker: Optional[Sticker] = None
#     link: Optional[Link] = None


class Message(VkBotBaseModel):
    """Модель сообщения VK"""
    id: int = 0
    date: int = 0
    peer_id: int
    from_id: int
    text: str = ""
    conversation_message_id: Optional[int] = None
    random_id: Optional[int] = None
    ref: Optional[str] = None
    ref_source: Optional[str] = None
    attachments: List[dict] = []
    important: bool = False
    geo: Optional[dict] = None
    payload: Optional[str] = None
    reply_message: Optional['Message'] = None
    fwd_messages: List['Message'] = []
    is_cropped: bool = False
    token: Optional[str] = None

    # Дополнительные поля
    members_count: Optional[int] = None
    action: Optional[dict] = None
    action_mid: Optional[int] = None
    action_email: Optional[str] = None
    action_text: Optional[str] = None

    # Service field
    bot: Optional[Any] = Field(default=None, exclude=True)
    entities: Optional[List['MessageEntity']] = None
    _fsm_context: Optional[FSMContext] = PrivateAttr(default=None)

    async def answer(self, text, entities=None, keyboard=None):
        return await self.bot.send_message(self.peer_id, text, keyboard=keyboard)

    async def reply(self, text, parse_mode: Optional[str] = None, entities=None,
                    reply_markup=None, keyboard=None):
        """Ответ с цитированием (reply) этого сообщения."""
        return await self.bot.send_message_reply(
            self.peer_id, self.conversation_message_id, text, keyboard=keyboard or reply_markup
        )

    async def get_user(self):
        return await self.bot.get_vk_user_info(self.from_id)

    async def edit_message(self, text: str, keyboard=None):
        return await self.bot.edit_message(
            self.peer_id, self.id or None, self.conversation_message_id, text, keyboard
        )


# ========== Модели для inline кнопок (callback) ==========
class CallbackPayload(BaseModel):
    """Payload от inline кнопки"""
    model_config = ConfigDict(extra="allow")

    action: str
    data: Optional[Dict[str, Any]] = None
    page: Optional[int] = None
    product_id: Optional[int] = None


class MessageEventObject(VkBotBaseModel):
    """Объект события нажатия на inline кнопку"""
    user_id: int
    peer_id: int
    event_id: str
    payload: Dict[str, Any] = {}
    conversation_message_id: Optional[int] = None
    message_id: Optional[int] = None
    token: Optional[str] = None

    bot: Optional[Any] = Field(default=None, exclude=True)
    _fsm_context: Optional[FSMContext] = PrivateAttr(default=None)

    @property
    def payload_model(self) -> CallbackPayload:
        """Преобразует payload в модель"""
        return CallbackPayload(**self.payload)

    async def answer(self, text: Optional[str] = None, event_data: Optional[dict] = None):
        """Ответ на нажатие (убирает «часики» на кнопке); text — snackbar."""
        return await self.bot.send_callback_answer(
            self.event_id, self.peer_id, self.user_id, text, event_data
        )

    async def edit_message(self, text: str, keyboard=None):
        return await self.bot.edit_message(
            self.peer_id, self.message_id, self.conversation_message_id, text, keyboard
        )

    async def send_message(self, text, entities=None, keyboard=None):
        return await self.bot.send_message(self.peer_id, text, keyboard=keyboard)


# ========== Основные модели событий ==========
class VKCallbackEvent(BaseModel):
    """Базовая модель для всех callback событий"""
    type: VKEventType
    group_id: int
    secret: Optional[str] = None
    event_id: Optional[str] = None


class MessageEventEvent(VKCallbackEvent):
    """Событие нажатия на inline кнопку"""
    type: VKEventType = VKEventType.MESSAGE_EVENT
    object: MessageEventObject


# ========== Модели для ответа VK (всплывающие уведомления и т.п.) ==========
class VKCallbackAnswer(BaseModel):
    """Базовый ответ на callback событие"""
    type: str = "show_snackbar"
    text: str = ""


class ShowSnackbar(VKCallbackAnswer):
    """Показать всплывающее уведомление"""
    type: str = "show_snackbar"


class OpenLink(VKCallbackAnswer):
    """Открыть ссылку"""
    type: str = "open_link"
    link: str


class OpenApp(VKCallbackAnswer):
    """Открыть мини-приложение"""
    type: str = "open_app"
    app_id: int
    owner_id: int
    hash: str = ""


class VKCallbackResponse(BaseModel):
    """Ответ VK на callback событие"""
    ok: bool = True
    error: Optional[str] = None
