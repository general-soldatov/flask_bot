from typing import Optional
import json

from vkBot.types import CallbackPayload
from vkBot.keyboard.action import Text, OpenLink, Callback
from vkBot.keyboard.button import ReplyKeyboard, InlineKeyboard, ButtonColor
from app.config.dictionary import reference, library_button, lexicon
from app.config.config import service

def start_pack(subject: str, is_register: bool = False):
    start = ReplyKeyboard(one_time=False)
    data = ['profile', 'help', 'books', 'schedule']
    for i, buttton in enumerate(data):
        start.add(Text(label=lexicon.buttons[buttton]))
        if i % 2:
            start.row()
    if is_register:
        start.add(Text(label=lexicon.buttons['task']))
    start.add(OpenLink(label=lexicon.buttons['skill'], link=reference.courses[subject]))
    return start

def get_subject(profile: bool = False):
    direct = InlineKeyboard()
    for i, key in enumerate(lexicon.subject):
        direct.add(Callback(label=lexicon.subject[key], payload=CallbackPayload(source='subject', action=key).model_dump_json()))
    if profile:
        direct.row()
        direct.add(Callback(label=lexicon.buttons['back'], payload=CallbackPayload(action='profile').model_dump_json()))
    return direct

def get_book(subject: str):
    books = InlineKeyboard()
    for key in reference.library[subject]:
        for i, book in enumerate(library_button(subject, key)):
            books.add(OpenLink(**book))
            if i % 2:
                books.row()
        books.row()
    if subject == 'phys':
        books.add(Callback(label=lexicon.buttons['colab'], payload=CallbackPayload(source='colab', action='').model_dump_json()))
    return books

def get_temp_colab(subject):
    books = InlineKeyboard()
    for colab in service.colab:
        books.add(OpenLink(**colab))
        books.row()
    return books

schedule = InlineKeyboard()
for i, key in enumerate(reference.schedule.selector):
    schedule.add(Callback(label=lexicon.schedule[key], payload=CallbackPayload(source='schedule', action=key).model_dump_json()))
    if i % 2:
        schedule.row()


contact = InlineKeyboard()
contact.add(Callback(label=lexicon.contacts['question'], payload=CallbackPayload(source='question', action='').model_dump_json()))
for i, key in enumerate(reference.contacts.keys(), 1):
    contact.add(OpenLink(link=reference.contacts[key],
                         label=lexicon.contacts[key]))
    if i % 2:
        contact.row()

stop = InlineKeyboard()
stop.add(Callback(label=lexicon.inline['stop'], payload=CallbackPayload(source='stop', action='').model_dump_json()))

def get_agree(source: str):
    available = InlineKeyboard()
    available.add(Callback(label=lexicon.buttons['agree'], payload=CallbackPayload(source=source, action='yes').model_dump_json()))
    available.add(Callback(label=lexicon.buttons['disagree'], payload=CallbackPayload(source=source, action='no').model_dump_json()))
    return available

def get_profile(url_profile: str | None = None):
    profile = InlineKeyboard()
    if not url_profile:
        profile.add(Callback(label=lexicon.buttons['register'], payload=CallbackPayload(source='profile', action='register').model_dump_json()))
    else:
        profile.add(OpenLink(link=url_profile,
                         label=lexicon.buttons['profile']))
    profile.row()
    profile.add(Callback(label=lexicon.buttons['subject'], payload=CallbackPayload(source='profile', action='subject').model_dump_json()))
    profile.row()
    profile.add(Callback(label=lexicon.buttons['stepik_id'], payload=CallbackPayload(source='stepik_id', action='stepik_id').model_dump_json()))
    return profile

def set_answer(user_id: int, cmid: int):
    answer = InlineKeyboard()
    answer.add(OpenLink(link=reference.admin['dialog'].format(user_id=user_id, cmid=cmid),
                         label=lexicon.buttons['answer']))
    return answer

def get_tasks(tasks_lst: list, solve_task: list):
    for item in solve_task:
        if item in tasks_lst:
            tasks_lst.remove(item)
    tasks = InlineKeyboard()
    for i, item in enumerate(tasks_lst[:7], 1):
        tasks.add(Callback(label=item, payload=CallbackPayload(source='tasks', action=item).model_dump_json()))
        if i % 5 == 0:
            tasks.row()
    tasks.row()
    tasks.add(Callback(label=lexicon.buttons['percent'], payload=json.dumps({'source': 'percent', 'action': ''})))
    tasks.add(Callback(label=lexicon.buttons['colab'], payload=CallbackPayload(source='colab_task', action='').model_dump_json()))
    return tasks

def check_task(task_id: str, user_id: int, fullname: str, score: int = 8, colab: Optional[str] = None):
    check = InlineKeyboard()
    for i in range(1, score + 1):
        check.add(Callback(label=str(i), payload=CallbackPayload(**{'source': 'check_task',
                                                  'task_id': task_id, 'user_id': user_id,
                                                  'fullname': fullname, 'score': str(i), 'action': ''}).model_dump_json()))
        if i % 5 == 0:
            check.row()
    if colab:
        check.row()
        check.add(OpenLink(link=colab, label='LINK TO COLAB'))
    return check

def check_percent(user_id: int, fullname: str):
    check = InlineKeyboard()
    for elem in reference.tasks['percent']:
        check.add(Callback(label=str(elem), payload=CallbackPayload(**{'source': 'check_percent','user_id': user_id,
                                                  'fullname': fullname, 'score': str(elem), 'action': ''}).model_dump_json()))
        if elem % 3 == 0:
            check.row()
    return check

def stepik(subject: str):
    step = InlineKeyboard()
    step.add(OpenLink(link=reference.classes[subject], label=lexicon.buttons['step_class']))
    step.row()
    step.add(Callback(label=lexicon.buttons['stepik_id'], payload=CallbackPayload(source='step_reg', action='step_reg').model_dump_json()))
    return step

def set_mailer(labels, source_obj: str, current: str, back_source: Optional[str] = None, **kwargs):
    direct = InlineKeyboard()
    kwargs['source'] = source_obj
    for i, key in enumerate(labels):
        if isinstance(labels, dict):
            direct.add(Callback(label=labels[key], payload=CallbackPayload(action='',**kwargs, current=key).model_dump_json()))
        else:
            direct.add(Callback(label=key, payload=json.dumps({**kwargs, current: key, 'action': ''})))
        if i % 2:
            direct.row()
    direct.row()
    direct.add(Callback(label=lexicon.buttons['all'], payload=json.dumps({**kwargs, 'source': "message_mailer", 'action': ''})))
    if back_source:
        direct.row()
        direct.add(Callback(label=lexicon.buttons['back'], payload=CallbackPayload(**{**kwargs, 'source': back_source}, action='').model_dump_json()))
    return direct