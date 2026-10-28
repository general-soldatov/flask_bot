from app.ydb_connect import ManageVK, Students, Stepik, Users
from .rate_maker import get_rate
from .functool import get_range, Scores
from app.features.user_api import Contingent
from typing import Dict, Union

PHYS = "https://storage.yandexcloud.net/phys-bot/json/contingent.json"
TERMEX = "https://storage.yandexcloud.net/termex-bot/json/contingent.json"
SCORES = "https://storage.yandexcloud.net/termex-bot/scores.json"


def get_rates_list(directs: Dict[str, dict]):
    RATE_ADMIN = []

    for bucket, profiles in directs.items():
        for profile in profiles.keys():
            try:
                rate = get_rate(profile, f'{bucket}-bot')
                RATE_ADMIN.append(rate)
            except Exception as e:
                print("No such key", e)
    
    return RATE_ADMIN


async def get_profile(data: Students, step: Stepik) -> Dict[str, Union[str, int, Dict[str, str]]]:
    scores = await Scores.model_construct(SCORES)
    mark = scores.get_mark(data, step)
    rater = await get_range(mark["rate"])
    RATE_ADMIN = get_rates_list(scores.students)
    rate_list = []
    if RATE_ADMIN:
        if data.profile == "Преподаватель" or data.profile == "Тестировщик":
            rate_list = RATE_ADMIN
        elif data.profile in scores.students[data.subject]:
            rate_list = [get_rate(data.profile, f'{data.subject}-bot')]
    return {
        "name": data.full_name,
        "range": rater['name'],
        "quote": rater['quote'],
        "img": rater['image'],
        "stepik": step.score,
        **mark,
        "info": {
            'Профиль': data.profile,
            'Группа': data.group_id
        },
        "tasks": data.tasks,
        "rate_list": rate_list
    }

async def get_data(user_id: int):
    db = ManageVK()
    data = await db.get_info(user_id)
    if isinstance(data, Users):
        return None
    step = await db.get_score_stepik(user_id)
    if not data:
        return
    result = await get_profile(data, step)
    if data.subject == 'termex':
        user = await Contingent.get(data.full_name, 'termex')
        result["info"].update({
            'Вариант': user.var,
            'Вариант Д1': user.varD
        })
    return result
