import httpx
from typing import Dict, Optional, List, Union
import re
from app.database import ManageVK, Students
from app.config.config import service

def get_step_id(data: str):
    pattern = r'(?:\/users\/)?(\d+)(?:\/profile)?'
    match = re.search(pattern, data)
    if match:
        user_id = match.group(1)
        return user_id

class StepikParser:
    def __init__(self, config: Dict[str, str]):
        self.token = self._get_token(**config)
        self.base_url = "https://stepik.org/api"
        self.headers = {
            'Authorization': f'Bearer {self.token}'
        }
    
    @staticmethod
    def _get_token(client_id, client_secret):
        auth = httpx.BasicAuth(client_id, client_secret)
        resp = httpx.post('https://stepik.org/oauth2/token/',
                                data={'grant_type': 'client_credentials'}, auth=auth)
        return resp.json()['access_token']

    
    def _request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Выполнение GET-запроса к API с обработкой пагинации."""
        url = f"{self.base_url}/{endpoint}"
        response = httpx.get(
            url,
            headers=self.headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def get_enrollments(self, course_id: int, user_id: Optional[int] = None) -> Union[List[Dict], Dict]:
        page = 1
        students_grades = []

        print(f"Начинаем сбор баллов для курса ID {course_id}...")

        while True:
            # Запрашиваем страницу с оценками
            url = f"{self.base_url}/course-grades?course={course_id}&page={page}"
            response = httpx.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()

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

def update_data_stepik(db: ManageVK):
    data = db.get_all_stepik()
    stepik = StepikParser(service.stepik)
    not_search = []
    grades = {}
    text = ''
    try:
        grades[287410] = stepik.get_enrollments(287410)
        grades[278225] = stepik.get_enrollments(278225)
        for elem in data:
            flag = False
            student: Students = db.get_info(elem.id)
            for user in grades[elem.course_id]:
                if user['user_id'] == elem.stepik_id:
                    text += f'{student.full_name} | {user['score']}\n'
                    db.update_score_stepik(student.id, user['score'])
                    flag = True
                    break
            if not flag:
                text += f'{student.full_name} | {elem.stepik_id} | no data\n'
                not_search.append(student.id)
        return text, not_search
    except Exception as e:
        return e, not_search