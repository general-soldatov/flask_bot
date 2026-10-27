from app.ydb_connect import ManageVK, Students, Stepik
from .rate_maker import get_rate
from .functool import get_range, get_fine, sum_task
from app.features.user_api import Contingent

PHYS = "https://storage.yandexcloud.net/phys-bot/json/contingent.json"
TERMEX = "https://storage.yandexcloud.net/termex-bot/json/contingent.json"

def study_score(data: Students, step: Stepik):
    score = 0
    if step:
        score = step.score
    coeff = {
        'termex': 0.05,
        'phys': 0.07
    }
    tasks = sum_task(data.tasks)
    tasks += sum_task(data.bonus)
    tasks += coeff[data.subject] * score
    tasks = round(tasks * (1 + data.prize / 100), 1) - int(data.fine)
    return tasks


directs = {'phys-bot': ['Биотехнологии', 'ППЖП', 'ППРС', 'ААЭ'], 'termex-bot': ['НТТС']}
RATE_ADMIN = []

for bucket, profiles in directs.items():
    for profile in profiles:
        try:
            rate = get_rate(profile, bucket)
            RATE_ADMIN.append(rate)
        except Exception as e:
            print("No such key", e)

async def termex_profile(data, step):  
    tasks = study_score(data, step)
    rater = await get_range(tasks)
    user = await Contingent.get(data.full_name, 'termex')
    rate_list = []
    if RATE_ADMIN:
        if data.profile == "Преподаватель" or data.profile == "Тестировщик":
            rate_list = RATE_ADMIN
        else:
            rate_list = [get_rate(data.profile, 'termex-bot')]
    return {
        "name": data.full_name,
        "range": rater['name'],
        "quote": rater['quote'],
        "rate": tasks,
        "img": rater['image'],
        "star": get_fine(tasks, data.subject, data.profile),
        "info": {
            'Профиль': data.profile,
            'Группа': data.group_id,
            'Вариант': user.data['var'],
            'Вариант Д1': user.data['varD']
        },
        "tasks": data.tasks,
        "rate_list": rate_list
    }

async def phys_profile(data, step):
    tasks = study_score(data, step)
    rater = await get_range(tasks)
    rate_list = []
    if RATE_ADMIN:
        if data.profile == "Преподаватель" or data.profile == "Тестировщик":
            rate_list = RATE_ADMIN
        else:
            rate_list = [get_rate(data.profile, 'phys-bot')]
    return {
        "name": data.full_name,
        "range": rater['name'],
        "quote": rater['quote'],
        "rate": tasks,
        "img": rater['image'],
        "star": get_fine(tasks, data.subject, data.profile),
        "info": {
            'Профиль': data.profile,
            'Группа': data.group_id
        },
        "tasks": data.tasks,
        "rate_list": rate_list
    }

async def get_data(user_id: int):
    data = None
    db = ManageVK()
    data = await db.get_info(user_id)
    step = await db.get_score_stepik(user_id)
    if not data:
        return
    if data.subject == 'phys':
        return await phys_profile(data, step)
    elif data.subject == 'termex':
        return await termex_profile(data, step)
