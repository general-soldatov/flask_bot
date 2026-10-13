from vkBot import Message, MessageEventObject
from vkBot.filters import BaseFilter
from typing import List
import json
import logging

logger = logging.getLogger(__name__)

from app.config.dictionary import lexicon

class Helping(BaseFilter):
    def __call__(self, message: Message) -> bool:
        return message.text in ['/help', 'Помощь', lexicon.buttons['help']] or 'помо' in message.text.lower()

class GetKey(BaseFilter):
    def __call__(self, message: Message) -> bool:
        return message.text in ['/menu', '/keyboard', 'клавиатура'] or 'клав' in message.text.lower()


class SourcePayload(BaseFilter):
    def __init__(self, source: str):
        self.source = source
    
    def __call__(self, event: MessageEventObject) -> bool:
        """
        Проверяет, что в payload содержится source с указанным значением
        """
        return event.payload_model.source == self.source

class Button(BaseFilter):
    def __init__(self, name: str):
        self.name = lexicon.buttons[name]

    def __call__(self, message: Message):
        return message.text == self.name

class AdminMenu(BaseFilter):
    def __init__(self, admin_lst: List[int]):
        self.admins = admin_lst
        self.commands: List[str] = []

    def __call__(self, message: Message) -> bool:
        if str(message.from_id) in self.admins:
            return message.text.lower() in self.commands

class Mailer(AdminMenu):
    def __init__(self, admin_lst: List[int]):
        super().__init__(admin_lst)
        self.commands = ['рассылка', 'реклама', 'почта', 'mail']
