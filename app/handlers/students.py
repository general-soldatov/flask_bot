from app.config.config import ADMIN, service
from app.filters import SourcePayload
from app.config.dictionary import lexicon, reference
import app.keyboards as key

from vkBot import Router, Message, MessageEventObject, Bot
from vkBot.fsm.state import State, StatesGroup
from vkBot.fsm.context import FSMContext
from vkBot.filters import StateFilter
from app.filters import SourcePayload, Button
# from app.database import ManageVK, Students, Stepik
from app.ydb_connect import ManageVK, Students
from app.features.stepik import get_step_id
import logging

logger = logging.getLogger(__name__)
rt = Router()

@rt.message(Button('task'))
def cmd_task(message: Message, db: ManageVK):
    info = db.get_tasks(message.from_id)
    if info:
        message.answer(lexicon.students['task'], 
                             keyboard=key.get_tasks(reference.tasks[info['subject']], solve_task=info['tasks']).as_markup())
    else:
        message.answer(lexicon.users['permission_denied'])

@rt.callback_query(SourcePayload('tasks'))
def set_task(event: MessageEventObject, db: ManageVK, bot: Bot):
    user = db.get_info(event.user_id)
    if isinstance(user, Students):
        task = event.payload_model.action
        event.edit_message(lexicon.students['task_call'].format(task=task))
        bot.send_message(peer_id=ADMIN, message=lexicon.admin['task'].format(name=user.full_name,
                                                                         task=task, subject=lexicon.subject[user.subject]),
                                    keyboard=key.check_task(task, event.user_id, user.full_name).as_markup())
    else:
        event.edit_message(lexicon.users['permission_denied'])

@rt.callback_query(SourcePayload('percent'))
def set_task(event: MessageEventObject, db: ManageVK, bot: Bot):
    user = db.get_info(event.user_id)
    if isinstance(user, Students):
        event.edit_message(lexicon.students['percent_call'])
        bot.send_message(peer_id=ADMIN, message=lexicon.admin['percent_call'].format(name=user.full_name,
                                                                         subject=lexicon.subject[user.subject]),
                                    keyboard=key.check_percent(event.user_id, user.full_name).as_markup())
    else:
        event.edit_message(lexicon.users['permission_denied'])

@rt.callback_query(SourcePayload('stepik_id'))
def stepik_id(event: MessageEventObject, db: ManageVK):
    user = db.get_info(event.user_id)
    if isinstance(user, Students):
        event.edit_message(lexicon.students['step_class'], keyboard=key.stepik(user.subject).as_markup())
    else:
        event.edit_message(lexicon.users['permission_denied'])

class StepikID(StatesGroup):
    text = State()

@rt.callback_query(SourcePayload('step_reg'))
def stepik_id(event: MessageEventObject, state: FSMContext):
    state.set_state(StepikID.text)
    state.set_data({'message_id': event.message_id, 'cmid': event.conversation_message_id})
    event.edit_message(lexicon.students['stepik_id'], keyboard=key.stop.as_markup())


@rt.message(StateFilter(StepikID.text))
def question(message: Message, state: FSMContext, db: ManageVK, bot: Bot):
    step_id = int(get_step_id(message.text))

    user = db.get_info(message.from_id)
    if step_id and isinstance(user, Students):
        try:
            student = db.get_score_stepik(message.from_id)
            if not student:
                db.set_stepik_id(message.from_id, service.course[user.subject], int(step_id), 0)
            else:
                db.update_stepik_id(message.from_id, step_id)
            message.answer(lexicon.students['step_success'])
            state.clear()
        except Exception as e:
            message.answer(lexicon.users["error"])
            logger.error(e)
    else:
        message.answer(lexicon.users['error'])

@rt.callback_query(SourcePayload('colab'))
def set_task(event: MessageEventObject, db: ManageVK):
    user = db.get_info(event.user_id)
    if isinstance(user, Students):
        event.edit_message(lexicon.students['colab'], keyboard=key.get_temp_colab(user.subject).as_markup())
    else:
        event.edit_message(lexicon.users['permission_denied'])

class Colab(StatesGroup):
    link = State()

@rt.callback_query(SourcePayload('colab_task'))
def set_task(event: MessageEventObject, db: ManageVK, state: FSMContext):
    user = db.get_info(event.user_id)
    if isinstance(user, Students):
        event.edit_message(lexicon.students['colab_url'], keyboard=key.stop.as_markup())
        state.set_state(Colab.link)
    else:
        event.edit_message(lexicon.users['permission_denied'])

@rt.message(StateFilter(Colab.link))
def question(message: Message, state: FSMContext, db: ManageVK, bot: Bot):
    try:
        db.set_colab(message.from_id, message.text)
        user = db.get_info(message.from_id)
    except Exception as e:
        logger.error(f'Send colab: {e}')
        message.answer(lexicon.users["error"])
        return
    if isinstance(user, Students):
        task = db.get_colab_by_url(message.text)
        message.answer(lexicon.students['task_call'].format(task='colab'))
        state.clear()
        bot.send_message(ADMIN, lexicon.admin['task'].format(name=user.full_name,
                                                                         task='colab', subject=lexicon.subject[user.subject]),
                                    keyboard=key.check_task(task.id, message.from_id, user.full_name, colab=message.text).as_markup())
    else:
        message.answer(lexicon.users['permission_denied'])
