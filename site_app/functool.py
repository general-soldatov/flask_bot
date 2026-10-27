import aiohttp

def sum_task(data: dict) -> float:
    return sum(map(int, data.values()))

async def get_range(score: float | int):
    url = 'https://storage.yandexcloud.net/termex-bot/telegram-bot/static/ranger.json'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            page: dict = await response.json(content_type=None)
            for key, value in page.items():
                if score < int(key):
                    return value
            return page["110"]

def get_fine(score: float | int, subject, profile):
    data = {
        'termex': {'НТТС': [10, 30, 50, 65, 80]},
        'phys': {
            'ААЭ': [10, 20, 35, 45, 60],
            'Биотехнологии': [15, 35, 50, 65, 80],
            'ППРС': [10, 30, 50, 60, 75],
            'ППЖП': [10, 30, 50, 60, 75]
            }
        }
    star = [10, 30, 50, 60, 75]
    value = data[subject].get(profile, star)
    for i in range(5, 0, -1):
        if score > value[i - 1]:
            return i
    return 0

def study_score(data: dict):
    tasks = sum_task(data['tasks'])
    tasks += sum_task(data['bonus'])
    tasks = round(tasks * (1 + data['prize'] / 100), 1) - int(data['fine'])
    return tasks