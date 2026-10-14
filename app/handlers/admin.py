# from token import PERCENT
import httpx
from vkBot import Router, Message, MessageEventObject, Bot, F
from vkBot.fsm.state import State, StatesGroup
from vkBot.fsm.context import FSMContext
from vkBot.filters import StateFilter

from app.config.config import ADMIN
from app.filters import SourcePayload, Mailer
from app.config.dictionary import lexicon, reference
import app.keyboards as key
# from app.features.copy_message import MessageCopier
from app.filters import SourcePayload
from app.database import ManageVK
# from app.ydb_connect import ManageVK
from app.features.stepik import update_data_stepik

rt = Router()

@rt.callback_query(SourcePayload('check_task'))
def set_task(event: MessageEventObject, db: ManageVK, bot: Bot):
    info = event.payload_model
    if db.add_task(info.user_id, info.task_id, info.score):
        event.edit_message(lexicon.admin['task_score'].format(name=info.fullname, score=info.score, task=info.task_id))
        bot.vk.messages.send(user_id=info.user_id, random_id=0,
                                        peer_id=event.peer_id,
                                        message=lexicon.students['task_score'].format(task=info.task_id, score=info.score))
    else:
        event.send_message(lexicon.admin['error'])


@rt.callback_query(SourcePayload('check_percent'))
def set_percent(event: MessageEventObject, db: ManageVK, bot: Bot):
    info = event.payload_model
    if db.set_percent(info.user_id, int(info.score)):
        event.edit_message(lexicon.admin['percent'].format(name=info.fullname, score=info.score))
        bot.vk.messages.send(user_id=info.user_id, random_id=0,
                                        peer_id=event.peer_id,
                                        message=lexicon.students['percent'].format(score=info.score))
    else:
        event.send_message(lexicon.admin['error'])

@rt.message(F.text.startswith_ignore_case('рейти'))
def set_rate(message: Message, db: ManageVK, bot: Bot):
    message.answer('Please, wait...')
    try:
        response = httpx.get('https://d5dvtf5ioi8q69ckjelk.apigw.yandexcloud.net/vk_bot/rate').json()
        if response:
            time_data = float(response[0]['time']) + float(response[1]['time'])
            message.answer(lexicon.admin['rate'].format(termex=response[0]['message'],
                                                        phys=response[1]['message'],
                                                        time_data=round(time_data, 3)))
        else:
            message.answer('error')
    except Exception as e:
        message.answer(f'error: {e}')

@rt.message(F.text.startswith_ignore_case('степ'))
def set_rate(message: Message, db: ManageVK, bot: Bot):
    message.answer('Please, wait...')        
    text, no_data = update_data_stepik(db)
    message.answer(text)
    for _id in no_data:
        try:
            bot.send_message(_id, 'Ваш Stepik ID не прошёл верификацию. Попробуйте ввести ID снова.')
        except Exception as e:
            message.answer(f"Письмо {_id} не отправлено: {e}")

# @rt.message(Mailer([ADMIN]))
# def cmd_mailer(message: Message):
#     message.answer(lexicon.admin['subject'],
#                          keyboard=key.set_mailer(lexicon.subject, 'subject_mail', 'subject_mail').as_markup())

# @rt.callback_query(SourcePayload('subject_mail'))
# def set_subject(event: MessageEventObject):
#     info = event.payload
#     profile = reference.groups[info['subject_mail']].keys()
#     event.edit_message(lexicon.admin['profile_mail'],
#                          keyboard=key.set_mailer(profile, 'profile_mail', 'subject_mail').as_markup())

# @rt.callback_query(SourcePayload('profile_mail'))
# def set_profile(event: MessageEventObject):
#     info = event.payload
#     profile = reference.groups[info['subject_mail']].keys()
#     event.edit_message(lexicon.admin['profile_mail'],
#                          keyboard=key.set_mailer(profile, 'mail_group', 'profile_mail', 'subject_mail', **info).as_markup())

# @rt.callback_query(SourcePayload('mail_group'))
# def set_group(event: MessageEventObject):
#     info = event.payload
#     profile = reference.groups[info['subject_mail']][info['profile_mail']]
#     event.edit_message(lexicon.admin['subject'],
#                          keyboard=key.set_mailer(profile, 'message_mailer', 'mail_group', 'profile_mail', **info).as_markup())

# class MailState(StatesGroup):
#     message = State()

# @rt.callback_query(SourcePayload('message_mailer'))
# def set_message(event: MessageEventObject, state: FSMContext):
#     state.set_state(MailState.message)
#     state.set_data({'info': event.payload})
#     event.edit_message(lexicon.admin['message_mailer'])

# # message_copier = MessageCopier(bot)

# @rt.message(StateFilter(MailState.message))
# def set_mail_available(message: Message, state: FSMContext):
#     info = state.get_data().get('info')
#     # data = await message.get_full_message()
#     state.update_data(message=message.text)
#     message.answer(
#             lexicon.admin['mail_available'].format(subject_mail=lexicon.subject.get(info.get('subject_mail'), 'ALL'), 
#                                                    profile_mail=info.get('profile_mail', 'ALL'), 
#                                                    mail_group=info.get('mail_group', 'ALL')),
#             keyboard=key.get_agree('mail_available').as_markup())
    
# @rt.callback_query(SourcePayload('mail_available'))
# def set_message(event: MessageEventObject, state: FSMContext, db: ManageVK, bot: Bot):
#     agree = event.payload_model.action
#     if agree == 'yes':
#         data = state.get_data()
#         except_text = []
#         try:        
#             subject_mail = data['info'].get('subject_mail')
#             profile_mail = data['info'].get('profile_mail') 
#             mail_group = data['info'].get('mail_group')
#             if mail_group:
#                 to_mail = db.get_mailing_group(subject_mail, profile_mail, mail_group)
#             elif profile_mail:
#                 to_mail = db.get_mailing_profile(subject_mail, profile_mail)
#             elif subject_mail:
#                 to_mail = db.get_mailing_subject(subject_mail)
#             else:
#                 to_mail = db.get_mailing_all()
#             text = data['message']
#             for id in to_mail:
#                 bot.send_message(peer_id=id, message=text)
#                 # await message_copier.copy_message(
#                 #     source_message=message,
#                 #     target_peer_ids=to_mail[i:i+100],
#                 #     target_message=message.text
#                 # )  
#         except Exception as e:
#             except_text.append(str(e))
#         text = lexicon.admin['mailer_done'].format(subject_mail=lexicon.subject.get(data['info'].get('subject_mail'), 'ALL'), 
#                                                    profile_mail=data['info'].get('profile_mail', 'ALL'), 
#                                                    mail_group=data['info'].get('mail_group', 'ALL'), 
#                                                                     errors='\n'.join(except_text))
#     else:
#         text = lexicon.admin['mailer_cancel']
#     state.clear()
#     event.edit_message(text)