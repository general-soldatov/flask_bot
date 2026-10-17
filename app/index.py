import os
from typing import Dict, Any
import logging

from vkBot import Message, Dispatcher, Bot, Router, MessageEventObject
from vkBot.filters import CommandStart

from app.config.dictionary import lexicon
from app.filters import SourcePayload, Helping, GetKey, Button
import app.keyboards as key
from app.features.schedule import Schedule
from app.database import Users, ManageVK, Students, MySQLStorage
# from app.ydb_connect import Users, ManageVK, YQLStorage, Students
from app.handlers import greeting_user, students, admin

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

TOKEN = os.getenv('ACCESS_KEY')
ADMIN = os.getenv('ADMIN')

bot = Bot(TOKEN)

dp = Dispatcher(bot)

rt = Router('analys')

@dp.message(CommandStart())
def start(message: Message, db: ManageVK):
    user = message.get_user()
    if user:
        if not db.get_user_by_id(user.id): 
            data = Users(id=message.from_id, first_name=user.first_name, last_name=user.last_name, subject='')
            db.insert(data)
        message.answer(lexicon.users['start'].format(name=user.first_name), keyboard=key.get_subject().as_markup())
    else:
        if not db.get_user_by_id(user.id): 
            data = Users(id=message.from_id, first_name='user.first_name', last_name='user.last_name', subject='')
            db.insert(data)
        message.answer(lexicon.users['start'].format(name='студент!'), keyboard=key.get_subject().as_markup())

@dp.message(Helping())
def cmd_help(message: Message):
    user = message.get_user()
    message.answer(lexicon.users['help'].format(name=user.first_name), keyboard=key.contact.as_markup())

@dp.callback_query(SourcePayload('subject'))
def button(event: MessageEventObject, db: ManageVK):
    subject = event.payload_model.action
    if db.set_subject_user(event.user_id, subject):
        event.edit_message(lexicon.users['set_subject'].format(subject=lexicon.subject[subject]), 
                           keyboard=key.start_pack(subject).as_markup())
    else:
        event.edit_message(lexicon.users['error'])

@dp.message(GetKey())
def cmd_keyboard(message: Message, db: ManageVK):
    user = message.get_user()
    info = db.get_info(user.id)
    is_register = isinstance(info, Students)
    if info:
        message.answer(lexicon.users['menu'], keyboard=key.start_pack(info.subject, is_register).as_markup())
    else:
        message.answer()

@dp.message(Button('books'))
def cmd_keyboard(message: Message, db: ManageVK):
    user = message.get_user()
    info = db.get_user_by_id(user.id)
    message.answer(lexicon.users['books'], keyboard=key.get_book(info.subject).as_markup())

@dp.message(Button('schedule'))
def cmd_schedule(message: Message):
    weekday, shedules = Schedule().get_call('today')
    text = f"# {weekday}\n"
    text += '\n'.join([f'{key}: {value}' for key, value in shedules.items()])
    message.answer(text, keyboard=key.schedule.as_markup())

@dp.callback_query(SourcePayload('schedule'))
def edit_schedule(event: MessageEventObject):
    weekday, shedules = Schedule().get_call(event.payload_model.action)
    text = f"# {weekday}\n"
    text += '\n'.join([f'{key}: {value}' for key, value in shedules.items()])
    event.edit_message(text, keyboard=key.schedule.as_markup())
    


@rt.message()
def text(message: Message):
    message.answer("Я рад тебя видеть!")


def handler(event: Dict[str, Any], context):
    # dp.include_router(greeting_user.rt)
    # dp.include_router(students.rt)
    # dp.include_router(admin.rt)
    dp.include_router(rt)

    db = ManageVK()
    return dp.handler(event, context, context_data={'db': db}, storage=MySQLStorage(db))
