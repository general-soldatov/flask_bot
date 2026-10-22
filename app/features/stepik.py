import aiohttp
from typing import Dict, Optional, List, Union
import re
from app.ydb_connect import ManageVK, Students
from app.config.config import service

def get_step_id(data: str):
    pattern = r'(?:\/users\/)?(\d+)(?:\/profile)?'
    match = re.search(pattern, data)
    if match:
        user_id = match.group(1)
        return user_id

class StepikParser:
    def __init__(self, config: Dict[str, str]):
        self.config = config
        # self.token = self._get_token(**config)
        self.base_url = "https://stepik.org/api"
        self.headers = {}
    
    async def get_token(self):
        auth = aiohttp.BasicAuth(**self.config)
        async with aiohttp.ClientSession() as session:
            async with session.post('https://stepik.org/oauth2/token/',
                            data={'grant_type': 'client_credentials'}, auth=auth) as response:
                data = await response.json(content_type=None)
                self.token = data.get('access_token')
                self.headers = {
                        'Authorization': f'Bearer {self.token}'
                }

    
    async def _request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Выполнение GET-запроса к API с обработкой пагинации."""
        url = f"{self.base_url}/{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=params, timeout=30) as response:
                await response.raise_for_status()
                return await response.json(content_type=None)

    async def get_enrollments(self, course_id: int, user_id: Optional[int] = None) -> Union[List[Dict], Dict]:
        page = 1
        students_grades = []

        print(f"Начинаем сбор баллов для курса ID {course_id}...")

        while True:
            # Запрашиваем страницу с оценками
            url = f"{self.base_url}/course-grades?course={course_id}&page={page}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=30) as response:
                    await response.raise_for_status()
                    data = await response.json(content_type=None)

            # Парсим данные о студентах на текущей странице
            for grade in data.get("course-grades", []):
                if user_id is not None and grade["user"] == user_id:
                    return {
                        "user_id": grade["user"],
                        "score": grade["score"],  # Текущий балл студента за курс
                        "passed": grade.get("is_passed"),  # Получил ли уже сертификат/прошел ли курс
                    }
                students_grades.append(
                    {
                        "user_id": grade["user"],
                        "score": grade[
                            "score"
                        ],  # Текущий балл студента за курс
                        "passed": grade.get("is_passed"),  # Получил ли уже сертификат/прошел ли курс
                    }
                )

            # Проверяем, есть ли следующая страница
            if data.get("meta", {}).get("has_next"):
                page += 1
            else:
                break

        return students_grades

async def update_data_stepik(db: ManageVK):
    data = await db.get_all_stepik()
    stepik = StepikParser(service.stepik)
    await stepik.get_token()
    not_search = []
    grades = {}
    text = ''
    try:
        grades[287410] = await stepik.get_enrollments(287410)
        grades[278225] = await stepik.get_enrollments(278225)
        for elem in data:
            flag = False
            student: Students = await db.get_info(elem.id)
            for user in grades[elem.course_id]:
                if user['user_id'] == elem.stepik_id:
                    score = user['score']
                    text += f'{student.full_name} | {score}\n'
                    await db.update_score_stepik(student.id, score)
                    flag = True
                    break
            if not flag:
                text += f'{student.full_name} | {elem.stepik_id} | no data\n'
                not_search.append(student.id)
        return text, not_search
    except Exception as e:
        return e, not_search