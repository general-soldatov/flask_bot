import aiohttp
from app.ydb_connect import Stepik, Students
from pydantic import BaseModel
from typing import Dict, List

def sum_task(data: dict) -> float:
    return sum(map(int, data.values()))

class Scores(BaseModel):
    students: Dict[str, Dict[str, List[int | float]]]
    distant: List[int | float]
    default: List[int | float]
    stepik_coeff: Dict[str, int | float]

    @classmethod
    async def model_construct(cls, url: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                page: dict = await response.json(content_type=None)
                return cls(**page)

    @staticmethod
    def _get_mark(value: list, score: float | int):
        for i in range(5, 0, -1):
            if score > value[i - 1]:
                return i
        return 0

    @staticmethod
    def study_score(data: Students, step: Stepik, coeff: dict) -> float:
        score = 0
        if step:
            score = step.score
        tasks = sum_task(data.tasks) + sum_task(data.bonus)
        tasks += coeff[data.subject] * score
        tasks = round(tasks * (1 + data.prize / 100), 1) - int(data.fine)
        return tasks

    def get_mark(self, student: Students, step: Stepik):
        value = self.students[student.subject].get(student.profile, self.default)
        if student.form_study: # если заочка
            value = self.distant
        tasks = self.study_score(student, step, self.stepik_coeff)
        return {
            "star": self._get_mark(value, tasks),
            "rate": tasks
            }



async def get_range(score: float | int):
    url = 'https://storage.yandexcloud.net/termex-bot/telegram-bot/static/range.json'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            page: dict = await response.json(content_type=None)
            for key, value in page.items():
                if score < int(key):
                    return value
            return page["110"]

# async def get_fine(score: float | int, student: Students):
    # data = {
    #     'termex': {'НТТС': [10, 30, 50, 65, 80]},
    #     'phys': {
    #         'ААЭ': [10, 20, 35, 45, 60],
    #         'Биотехнологии': [15, 35, 50, 65, 80],
    #         'ППРС': [10, 30, 50, 60, 75],
    #         'ППЖП': [10, 30, 50, 60, 75]
    #         }
    #     }
    # star = [10, 30, 50, 60, 75]
    # scores = await Scores.model_construct(URL)
    # value = scores.students[student.subject].get(student.profile, scores.default)
    # if student.form_study: # если заочка
        # value = [5, 10, 14, 21, 24.5]
        # value = scores.distant
    


# def study_score(data: Students, step: Stepik):
#     score = 0
#     if step:
#         score = step.score
#     coeff = {
#         'termex': 0.05,
#         'phys': 0.07
#     }
#     tasks = sum_task(data.tasks)
#     tasks += sum_task(data.bonus)
#     tasks += coeff[data.subject] * score
#     tasks = round(tasks * (1 + data.prize / 100), 1) - int(data.fine)
#     return tasks

# async def study_score(data: Students, step: Stepik):
#     score = 0
#     if step:
#         score = step.score
#     coeff = {
#         'termex': 0.05,
#         'phys': 0.07
#     }
#     tasks = sum_task(data.tasks)
#     tasks += sum_task(data.bonus)
#     tasks += coeff[data.subject] * score
#     tasks = round(tasks * (1 + data.prize / 100), 1) - int(data.fine)
#     return tasks
