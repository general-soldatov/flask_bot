import os
from typing import Dict, Any
import logging

# from vkBot import Message, Dispatcher, Bot, Router, MessageEventObject
from aiovkBot import Bot, Dispatcher, Router, Message, MessageEventObject, MemoryStorage
# from vkBot.filters import CommandStart
from aiovkBot.filters import CommandStart

from app.config.dictionary import lexicon
from app.filters import SourcePayload, Helping, GetKey, Button
import app.keyboards as key
from app.features.schedule import Schedule
# from app.database import Users, ManageVK, Students, MySQLStorage
from app.ydb_connect import Users, ManageVK, YQLStorage, Students
from app.handlers import greeting_user, students, admin

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

TOKEN = os.getenv('ACCESS_KEY')
ADMIN = os.getenv('ADMIN')

bot = Bot(TOKEN)
db = ManageVK()

# dp = Dispatcher(bot, storage=YQLStorage(db))
dp = Dispatcher(bot, storage=MemoryStorage())
rt = Router('analys')

@dp.message(CommandStart())
async def start(message: Message, db: ManageVK):
    user = await message.get_user()
    if user:
        if not await db.get_user_by_id(user.id): 
            data = Users(id=message.from_id, first_name=user.first_name, last_name=user.last_name, subject='')
            await db.insert(data)
        await message.answer(lexicon.users['start'].format(name=user.first_name), keyboard=key.get_subject().as_markup())
    else:
        if not await db.get_user_by_id(user.id): 
            data = Users(id=message.from_id, first_name='user.first_name', last_name='user.last_name', subject='')
            await db.insert(data)
        await message.answer(lexicon.users['start'].format(name='студент!'), keyboard=key.get_subject().as_markup())

@dp.message(Helping())
async def cmd_help(message: Message):
    user = await message.get_user()
    await message.answer(lexicon.users['help'].format(name=user.first_name), keyboard=key.contact.as_markup())

@dp.callback_query(SourcePayload('subject'))
async def button(event: MessageEventObject, db: ManageVK):
    subject = event.payload_model.action
    if await db.set_subject_user(event.user_id, subject):
        await event.edit_message(lexicon.users['set_subject'].format(subject=lexicon.subject[subject]), 
                           keyboard=key.start_pack(subject).as_markup())
    else:
        await event.edit_message(lexicon.users['error'])

@dp.message(GetKey())
async def cmd_keyboard(message: Message, db: ManageVK):
    user = await message.get_user()
    info = await db.get_info(user.id)
    is_register = isinstance(info, Students)
    if info:
        await message.answer(lexicon.users['menu'], keyboard=key.start_pack(info.subject, is_register).as_markup())
    else:
        await message.answer()

@dp.message(Button('books'))
async def cmd_keyboard(message: Message, db: ManageVK):
    user = await message.get_user()
    info = await db.get_user_by_id(user.id)
    await message.answer(lexicon.users['books'], keyboard=key.get_book(info.subject).as_markup())

@dp.message(Button('schedule'))
async def cmd_schedule(message: Message):
    weekday, shedules = await Schedule().get_call('today')
    text = f"# {weekday}\n"
    text += '\n'.join([f'{key}: {value}' for key, value in shedules.items()])
    await message.answer(text, keyboard=key.schedule.as_markup())

@dp.callback_query(SourcePayload('schedule'))
async def edit_schedule(event: MessageEventObject):
    weekday, shedules = await Schedule().get_call(event.payload_model.action)
    text = f"# {weekday}\n"
    text += '\n'.join([f'{key}: {value}' for key, value in shedules.items()])
    await event.edit_message(text, keyboard=key.schedule.as_markup())
    


@rt.message()
async def text(message: Message):
    await message.answer("Я рад тебя видеть!")

dp.include_router(greeting_user.rt)
dp.include_router(students.rt)
dp.include_router(admin.rt)
dp.include_router(rt)

# def handler(event: Dict[str, Any], context):
    
    

    
    # dp.run_sinc(event, context, context_data={'db': db}, storage=YQLStorage(db))
