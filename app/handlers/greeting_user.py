from vkBot import Router, Message, MessageEventObject, Bot
from vkBot.fsm.state import State, StatesGroup
from vkBot.fsm.context import FSMContext
from vkBot.filters import StateFilter

from app.filters import SourcePayload, Button
from app.config.config import ADMIN
from app.config.dictionary import lexicon, reference
from app.features.user_api import Contingent
# from app.database import ManageVK, Users, Students
from app.ydb_connect import ManageVK, Users, Students

import logging
import json
import app.keyboards as key

logger = logging.getLogger(__name__)

rt = Router()
    
class Register(StatesGroup):
    name = State()

@rt.message(Button('profile'))
def cmd_profile(message: Message, db: ManageVK):
    url = None
    try:
        info = db.get_info(message.from_id)
        if isinstance(info, Students):
            data = dict(name = info.full_name,
                        subject=lexicon.subject[info.subject])
            url = reference.schedule.profile.format(subject=info.subject, tg_id=message.from_id)
        else:
            data = dict(name = f"{info.first_name} {info.last_name}",
                        subject=lexicon.subject[info.subject])
        message.answer(lexicon.users['profile'].format(**data),
                                 keyboard=key.get_profile(url).as_markup())
    except Exception as e:
        info = None 
        data = {}
        logger.error(f'DB: {e}')

@rt.callback_query(SourcePayload('profile'))
def call_profile(event: MessageEventObject, state: FSMContext, db: ManageVK):
    action = event.payload_model.action
    if action == 'subject':
        event.edit_message(lexicon.users['choice_subject'], keyboard=key.get_subject(True).as_markup())
    elif action == 'register':
        state.set_state(Register.name)      
        state.set_data({'message_id': event.message_id, 'cmid': event.conversation_message_id})
        event.edit_message(lexicon.users['register'], keyboard=key.stop.as_markup())
    else:
        url = None
        try:
            info = db.get_info(event.user_id)
            if isinstance(info, Students):
                data = dict(name = info.full_name,
                            subject=lexicon.subject[info.subject])
                url = reference.schedule.profile.format(subject=info.subject, tg_id=event.user_id)
            else:
                data = dict(name = f"{info.first_name} {info.last_name}",
                            subject=lexicon.subject[info.subject])
            event.edit_message(lexicon.users['profile'].format(**data),
                                    keyboard=key.get_profile(url).as_markup())
        except Exception as e:
            info = None 
            data = {}
            logger.error(f'DB: {e}')


@rt.message(StateFilter(Register.name))
def register(message: Message, state: FSMContext, bot: Bot, db: ManageVK):
    data = state.get_data()
    try:
        bot.edit_message(peer_id=message.peer_id, message_id=data['message_id'], 
                         cmid=data['cmid'], new_message=lexicon.users['help'])
    except Exception as e:
        logger.error(f'Register error: {e}')
    # bot.vk.messages.delete(peer_id=message.peer_id, cmids=[data['cmid']], message_ids=data['message_id'], delete_for_all=True)
    info_db = db.get_user_by_id(message.from_id)
    data = Contingent.get(message.text, info_db.subject)
    if data:
        info = data.model_dump()
        state.update_data(data=json.dumps(info))
        message.answer(
            lexicon.users['correct'].format(**info),
            keyboard=key.get_agree('register').as_markup())
    else:
        message.answer(lexicon.users['uncorrect'], keyboard=key.stop.as_markup())

@rt.callback_query(SourcePayload('register'))
def question_check(event: MessageEventObject, state: FSMContext, db: ManageVK, bot: Bot):
    agree = event.payload_model.action
    data = json.loads(state.get_data()['data'])
    state.clear_state()
    if agree == 'yes':
        try:
            info = db.get_user_by_id(event.user_id)
            student = Students(id=event.user_id, subject=info.subject, 
                               group_id=data['group'], full_name=data['name'], profile=data['profile'])
            db.insert(student)
            bot.send_message(peer_id=ADMIN, message=lexicon.users['success_to_admin'].format(**data,
                                                                                         user_id=event.user_id,
                                                                                         subject=lexicon.subject[info.subject]))
            event.edit_message(lexicon.users['success'].format(**data,
                                                                     subject=lexicon.subject[info.subject]),
                                                                     keyboard=key.start_pack(info.subject, is_register=True).as_markup())
        except Exception as e:
            bot.send_message(peer_id=ADMIN, message=lexicon.admin['error_reg'].format(**data, user_id=event.user_id, e=e))
            event.edit_message(lexicon.users['error'])
            logger.error(f'Register error: {e}')

    else:
        event.edit_message(lexicon.users['exit_reg'])


# Question

class Question(StatesGroup):
    text = State()

@rt.callback_query(SourcePayload('question'))
def edit_schedule(event: MessageEventObject, state: FSMContext):
    state.set_state(Question.text)
    state.set_data({'message_id': event.message_id, 'cmid': event.conversation_message_id})
    event.edit_message(lexicon.users['question'], keyboard=key.stop.as_markup())

@rt.message(StateFilter(Question.text))
def question(message: Message, state: FSMContext, bot: Bot):
    data = state.get_data()
    state.update_data(message_id=message.id)
    bot.vk.messages.delete(peer_id=message.peer_id, cmids=[data['cmid']], message_ids=data['message_id'], delete_for_all=True)
    message.answer(
        lexicon.users['available_reply'], keyboard=key.get_agree('question_check').as_markup())

@rt.callback_query(SourcePayload('question_check'))
def question_check(event: MessageEventObject, state: FSMContext, db: ManageVK, bot: Bot):
    agree = event.payload_model.action
    id = state.get_data().get('message_id')
    if agree == 'yes':
        try:
            user = db.get_info(event.user_id)
        except:
            user = None
        if isinstance(user, Students):
            text = lexicon.admin['question_student'].format(**user.__dict__)
        elif isinstance(user, Users):
            text = lexicon.admin['question_user']
        bot.send_message(peer_id=ADMIN, message=text, keyboard=key.set_answer(event.user_id, id).as_markup())
        bot.vk.messages.send(forward_messages=[id], user_id=ADMIN, peer_id=event.peer_id, random_id=0) #ВКонтакте требует параметр random_id для каждого метода messages.send, чтобы избежать дублирования сообщений.
        event.edit_message(lexicon.users['send_question'])
    else:
        event.edit_message(lexicon.users['help'], keyboard=key.contact.as_markup())
    state.clear()

@rt.callback_query(SourcePayload('stop'))
def edit_schedule(event: MessageEventObject, state: FSMContext, bot: Bot):
    """Stopped State Group
    """
    info = state.get_state()
    users_info = bot.get_vk_user_info(event.user_id)
    if info:
        state.clear()
    event.edit_message(lexicon.users['help'].format(name=users_info.first_name), keyboard=key.contact.as_markup())
