from typing import List, Optional, Dict, Any
import random
import logging
import json


from vkBot.fsm.context import FSMContext
# from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict, computed_field
from .keyboard.button import ReplyKeyboard
from enum import Enum
import vk_api

logger = logging.getLogger(__name__)

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


class Bot:
    """Класс для отправки сообщений от имени сообщества VK"""
        
    def __init__(self, token: str, api_version: str = "5.131"):
        self.token = token
        self.api_version = api_version
        self.base_url = "https://api.vk.com/method"
        # self.session = vk.API(token, v=self.api_version)
        vk_session = vk_api.VkApi(token=self.token, api_version=self.api_version)
        self.vk = vk_session.get_api()

    def send_message(
        self,
        peer_id: int,
        message: Optional[str] = None,
        attachment: Optional[str] = None,
        reply_to: Optional[int] = None,
        forward: Optional[str] = None,
        keyboard: Optional[str] = None,
        sticker_id: Optional[int] = None,
        payload: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Отправляет сообщение от имени сообщества.
        
        Args:
            peer_id: ID получателя (пользователя или чата)
            message: Текст сообщения
            attachment: Вложения (photo123_456, video456_789 и т.д.)
            reply_to: ID сообщения, на которое отвечаем (для ЛС)
            forward: Пересылаемые сообщения (json строка)
            keyboard: Клавиатура (json строка)
            sticker_id: ID стикера
            payload: Полезная нагрузка (json строка)
        
        Returns:
            Ответ от VK API
        """
        # Генерируем случайный ID для сообщения
        random_id = random.randint(-2_147_483_648, 2_147_483_647)
        
        params = {
            "peer_id": peer_id,
            "random_id": random_id
        }
        
        # # Добавляем необязательные параметры
        if message:
            params["message"] = message
        if attachment:
            params["attachment"] = attachment
        if reply_to:
            params["reply_to"] = reply_to
        if forward:
            params["forward"] = forward
        if keyboard:
            params["keyboard"] = keyboard
        if sticker_id:
            params["sticker_id"] = sticker_id
        if payload:
            params["payload"] = payload

        try:
            response = self.vk.messages.send(**params)
            logger.info(f"Успешный ответ от vk.messages.send: {response}")
            return response
        except Exception as err:
            logger.error(f"Ошибка при вызове vk.messages.send: {err}")
            return None
        

    
    def send_message_with_forward(
        self,
        peer_id: int,
        message: str,
        forward_message_ids: List[int],
        is_reply: bool = True
    ) -> Dict[str, Any]:
        """
        Отправляет сообщение с пересылкой/цитированием.
        
        Args:
            peer_id: ID получателя
            message: Текст сообщения
            forward_message_ids: Список ID сообщений для пересылки
            is_reply: Является ли ответом (цитированием)
        """
        forward = json.dumps({
            "peer_id": peer_id,
            "conversation_message_ids": forward_message_ids,
            "is_reply": is_reply
        })
        
        return self.send_message(
            peer_id=peer_id,
            message=message,
            forward=forward
        )

    def send_message_reply(self, peer_id, conversation_message_id, text):
        """
        Отправка сообщения с цитированием (Reply) оригинального сообщения.
        """
        try:
            forward_structure = {
                "peer_id": peer_id,
                "conversation_message_ids": [conversation_message_id],
                "is_reply": True 
            }
            
            self.vk.messages.send(
                peer_id=peer_id,
                message=text,
                random_id=random.randint(1, 2**31),
                forward=json.dumps(forward_structure)
            )
            logger.info("Ответ (reply) успешно отправлен.")
        except Exception as err:
            logger.error(f"Ошибка при вызове messages.send с reply: {err}")

    def edit_message(
        self,
        peer_id: int,
        message_id: int,
        cmid: int,
        new_message: str,
        keyboard: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Редактирует существующее сообщение.
        
        Args:
            peer_id: ID чата
            message_id: ID сообщения для редактирования
            new_message: Новый текст сообщения
            keyboard: Новая клавиатура (опционально)
        """
        try:
            # params = {
            #     "peer_id": peer_id,
            #     "message_id": message_id,
            #     "message": new_message,
            #     "cmid": cmid
            # }
            # # Если при редактировании нужно обновить или удалить кнопки
            # if keyboard:
            #     params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)
                
            self.vk.messages.edit(
                peer_id=peer_id,  # ID чата или пользователя
                message_id=message_id,  # ID изменяемого сообщения
                message=new_message,
                keyboard = keyboard,
                cmid=cmid
            )
            logger.info(f"Сообщение {message_id} успешно отредактировано.")
        except Exception as err:
            logger.error(f"Ошибка при вызове messages.edit: {err}")
        

    def send_typing_status(self, peer_id: int, activity_type="typing") -> Dict[str, Any]:
        """
        Отправляет статус "печатает..."
        
        Args:
            peer_id: ID чата
        """

        try:
            self.vk.messages.setActivity(
                peer_id=peer_id,
                type=activity_type
            )
            print(f"Статус активности '{activity_type}' успешно отправлен.")
        except Exception as err:
            logger.error(f"Ошибка при вызове messages.setActivity: {err}")

    def send_callback_answer(self, event_id, peer_id, user_id, text_snackbar: Optional[str] = None):
        """
        Отправляет callback со snackbar"
        
        Args:
            peer_id: ID чата
        """
        params = {
            "event_id": event_id,
            "user_id": user_id,
            "peer_id": peer_id,
            "type": "typing"
        }
        if text_snackbar:
            params['event_data'] = json.dumps({
                "type": "show_snackbar",
                "text": text_snackbar
            })
        try:
            response = self.vk.messages.sendMessageEventAnswer(**params)
            return response
        except Exception as err:
            logger.error(f"Ошибка при вызове vk.messages.sendMessageEventAnswer: {err}")
            return None

    def get_vk_user_info(self, user_id) -> Optional[User]:
        """Запрос информации о пользователе с помощью метода users.get библиотеки vk_api"""
        try:
            # Вызываем метод users.get. Передаем параметры как именованные аргументы (kwargs)
            response = self.vk.users.get(
                user_ids=user_id,
                fields="photo_50,city,screen_name,sex"
            )
            logger.info(f"Ответ от метода users.get: {response}")
            
            
            if response and isinstance(response, list):
                return User.load(**response[0])
            return None
        except Exception as err:
            print(f"Ошибка при вызове vk.users.get: {err}")
            return None
        
        

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
    id: int
    date: int
    peer_id: int
    from_id: int
    text: str
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
    action: Optional[str] = None
    action_mid: Optional[int] = None
    action_email: Optional[str] = None
    action_text: Optional[str] = None

    # Service field
    bot: Optional[Bot] = None
    _fsm_context: Optional['FSMContext'] = None
    entities: Optional[List['MessageEntity']] = None

    class Config:
        arbitrary_types_allowed = True

    def answer(self, text, entities = None, keyboard: Optional[str] = None):
        return self.bot.send_message(self.peer_id, text, keyboard=keyboard)


    def reply(self, text, parse_mode: Optional[str] = None, entities = None, reply_markup: Optional[str] = None):
        return self.bot

    def get_user(self):
        return self.bot.get_vk_user_info(self.from_id)
    
    def edit_message(self, text: str, keyboard: Optional[str] = None):
        self.bot.edit_message(self.peer_id, self.message_id, self.conversation_message_id, text, keyboard)

# ========== Модели для inline кнопок (callback) ==========
class CallbackPayload(BaseModel):
    """Payload от inline кнопки"""
    action: str
    data: Optional[Dict[str, Any]] = None
    page: Optional[int] = None
    product_id: Optional[int] = None
    
    # Любые дополнительные поля
    class Config:
        extra = "allow"


class MessageEventObject(VkBotBaseModel):
    """Объект события нажатия на inline кнопку"""
    user_id: int
    peer_id: int
    event_id: str
    payload: Dict[str, Any]
    conversation_message_id: int
    message_id: Optional[int] = None
    token: Optional[str] = None

    bot: Optional[Bot] = None
    _fsm_context: Optional['FSMContext'] = None
    # entities: Optional[List['MessageEntity']] = None

    class Config:
        arbitrary_types_allowed = True

    @property
    def payload_model(self) -> CallbackPayload:
        """Преобразует payload в модель"""
        return CallbackPayload(**self.payload)

    def edit_message(self, text: str, keyboard: Optional[str] = None):
        self.bot.edit_message(self.peer_id, self.message_id, self.conversation_message_id, text, keyboard)

    def send_message(self, text, entities = None, keyboard: Optional[str] = None):
        return self.bot.send_message(self.peer_id, text, keyboard=keyboard)


# ========== Основные модели событий ==========
class VKCallbackEvent(BaseModel):
    """Базовая модель для всех callback событий"""
    type: VKEventType
    group_id: int
    secret: Optional[str] = None


# class MessageNewEvent(VKCallbackEvent):
#     """Событие нового сообщения"""
#     type: VKEventType = VKEventType.MESSAGE_NEW
#     object: MessageModel
#     client_info: Optional[ClientInfo] = None


class MessageEventEvent(VKCallbackEvent):
    """Событие нажатия на inline кнопку"""
    type: VKEventType = VKEventType.MESSAGE_EVENT
    object: MessageEventObject


# ========== Модели для ответа VK (вые модальные окна и уведомления) ==========
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

