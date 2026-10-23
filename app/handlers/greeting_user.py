# from vkBot import Router, Message, MessageEventObject, Bot
# from vkBot.fsm.state import State, StatesGroup
# from vkBot.fsm.context import FSMContext
# from vkBot.filters import StateFilter
from aiovkBot import Router, Message, MessageEventObject, Bot
from aiovkBot.fsm.state import State, StatesGroup
from aiovkBot.fsm.context import FSMContext
from aiovkBot.filters import StateFilter


from app.filters import SourcePayload, Button
from app.config.config import ADMIN
from app.config.dictionary import lexicon, reference
from app.features.user_api import Contingent
# from app.database import ManageVK, Users, Students
from app.ydb_connect import ManageVK, Users, Students

import logging
import json
import os
import app.keyboards as key

logger = logging.getLogger(__name__)

rt = Router()
    
class Register(StatesGroup):
    name = State()

@rt.message(Button('profile'))
async def cmd_profile(message: Message, db: ManageVK):
    url = None
    try:
        info = await db.get_info(message.from_id)
        if isinstance(info, Students):
            data = dict(name = info.full_name,
                        subject=lexicon.subject[info.subject])
            url = reference.schedule.profile.format(subject=info.subject, tg_id=message.from_id)
        else:
            data = dict(name = f"{info.first_name} {info.last_name}",
                        subject=lexicon.subject[info.subject])
        await message.answer(lexicon.users['profile'].format(**data),
                                 keyboard=key.get_profile(url).as_markup())
    except Exception as e:
        info = None 
        data = {}
        logger.error(f'DB: {e}')

@rt.callback_query(SourcePayload('profile'))
async def call_profile(event: MessageEventObject, state: FSMContext, db: ManageVK):
    action = event.payload_model.action
    if action == 'subject':
        await event.edit_message(lexicon.users['choice_subject'], keyboard=key.get_subject(True).as_markup())
    elif action == 'register':
        await state.set_state(Register.name)      
        await state.set_data({'message_id': event.message_id, 'cmid': event.conversation_message_id})
        await event.edit_message(lexicon.users['register'], keyboard=key.stop.as_markup())
    else:
        url = None
        try:
            info = await db.get_info(event.user_id)
            if isinstance(info, Students):
                data = dict(name = info.full_name,
                            subject=lexicon.subject[info.subject])
                url = reference.schedule.profile.format(subject=info.subject, tg_id=event.user_id)
            else:
                data = dict(name = f"{info.first_name} {info.last_name}",
                            subject=lexicon.subject[info.subject])
            await event.edit_message(lexicon.users['profile'].format(**data),
                                    keyboard=key.get_profile(url).as_markup())
        except Exception as e:
            info = None 
            data = {}
            logger.error(f'DB: {e}')


@rt.message(StateFilter(Register.name))
async def register(message: Message, state: FSMContext, bot: Bot, db: ManageVK):
    data = await state.get_data()
    try:
        await bot.edit_message(peer_id=message.peer_id, message_id=data['message_id'], 
                         cmid=data['cmid'], new_message=lexicon.users['help'])
    except Exception as e:
        logger.error(f'Register error: {e}')
    # bot.vk.messages.delete(peer_id=message.peer_id, cmids=[data['cmid']], message_ids=data['message_id'], delete_for_all=True)
    info_db = await db.get_user_by_id(message.from_id)
    data = await Contingent.get(message.text, info_db.subject)
    if data:
        info = data.model_dump()
        await state.update_data(data=json.dumps(info))
        await message.answer(
            lexicon.users['correct'].format(**info),
            keyboard=key.get_agree('register').as_markup())
    else:
        await message.answer(lexicon.users['uncorrect'], keyboard=key.stop.as_markup())

@rt.callback_query(SourcePayload('register'))
async def question_check(event: MessageEventObject, state: FSMContext, db: ManageVK, bot: Bot):
    agree = event.payload_model.action
    data = json.loads(state.get_data()['data'])
    await state.clear_state()
    if agree == 'yes':
        try:
            info = await db.get_user_by_id(event.user_id)
            student = Students(id=event.user_id, subject=info.subject, 
                               group_id=data['group'], full_name=data['name'], profile=data['profile'])
            await db.insert(student)
            await bot.send_message(peer_id=ADMIN, message=lexicon.users['success_to_admin'].format(**data,
                                                                                         user_id=event.user_id,
                                                                                         subject=lexicon.subject[info.subject]))
            await event.edit_message(lexicon.users['success'].format(**data,
                                                                     subject=lexicon.subject[info.subject]),
                                                                     keyboard=key.start_pack(info.subject, is_register=True).as_markup())
        except Exception as e:
            await bot.send_message(peer_id=ADMIN, message=lexicon.admin['error_reg'].format(**data, user_id=event.user_id, e=e))
            await event.edit_message(lexicon.users['error'])
            logger.error(f'Register error: {e}')

    else:
        await event.edit_message(lexicon.users['exit_reg'])


# Question

class Question(StatesGroup):
    text = State()

@rt.callback_query(SourcePayload('question'))
async def edit_schedule(event: MessageEventObject, state: FSMContext):
    await state.set_state(Question.text)
    await state.set_data({'message_id': event.message_id, 'cmid': event.conversation_message_id})
    await event.edit_message(lexicon.users['question'], keyboard=key.stop.as_markup())

@rt.message(StateFilter(Question.text))
async def question(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(user_message_id=message.id)
    # await bot.vk.messages.delete(peer_id=message.peer_id, cmids=[data['cmid']], message_ids=data['message_id'], delete_for_all=True)
    await message.answer(
        lexicon.users['available_reply'], 
        keyboard=key.get_agree('question_check').as_markup())

@rt.callback_query(SourcePayload('question_check'))
async def question_check(event: MessageEventObject, state: FSMContext, db: ManageVK, bot: Bot):
    agree = event.payload_model.action
    dt = await state.get_data()
    user_msg_id = dt.get('user_message_id')   

    if agree == 'yes':
        try:
            user = await db.get_info(event.user_id)
        except:
            user = None
        if isinstance(user, Students):
            text = lexicon.admin['question_student'].format(**user.__dict__)
        else:
            text = lexicon.admin['question_user']
        await bot.send_message(peer_id=ADMIN, message=text, 
                               keyboard=key.set_answer(event.user_id, user_msg_id).as_markup())
        # await bot.send_message_with_forward(ADMIN, 'Message', [user_msg_id])
        import aiovk
        async with aiovk.TokenSession(access_token=os.getenv('ACCESS_KEY')) as session:
            api = aiovk.API(session)
            await api.messages.send(forward_messages=user_msg_id, user_id=ADMIN, peer_id=event.peer_id, random_id=0)
            
        # await bot.vk.messages.send(forward_messages=[id], user_id=ADMIN, peer_id=event.peer_id, random_id=0) #ВКонтакте требует параметр random_id для каждого метода messages.send, чтобы избежать дублирования сообщений.
        await event.edit_message(lexicon.users['send_question'])
    else:
        await event.edit_message(lexicon.users['help'], keyboard=key.contact.as_markup())
    await state.clear()

@rt.callback_query(SourcePayload('stop'))
async def edit_schedule(event: MessageEventObject, state: FSMContext, bot: Bot):
    """Stopped State Group
    """
    info = await state.get_state()
    users_info = await bot.get_vk_user_info(event.user_id)
    if info:
        await state.clear()
    await event.edit_message(lexicon.users['help'].format(name=users_info.first_name), keyboard=key.contact.as_markup())
