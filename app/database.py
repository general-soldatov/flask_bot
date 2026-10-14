from typing import Optional, List
from vkBot.database import BaseTable, DB
from vkBot.fsm.storage.base import BaseStorage
from pydantic import computed_field
import logging
import json
import hashlib

logger = logging.getLogger(__name__)


class Users(BaseTable):
    id: int
    last_name: str
    first_name: str
    subject: str
    is_mailing: bool = True


class Students(BaseTable):
    id: int
    full_name: str
    teacher_id: int = 0
    form_study: int = 0
    subject: str
    group_id: str
    profile: str
    fine: int = 0
    prize: int = 0
    bonus: dict = {}
    tasks: dict = {'SO': 0}

class FSMMemory(BaseTable):
    id: int
    states: str = ''
    data: dict = {}

class Stepik(BaseTable):
    id: int
    course_id: int
    stepik_id: int
    score: int

class Colab(BaseTable):
    url: str
    user_id: int

    @computed_field
    @property
    def id(self) -> str:
        length: int = 7
        # 1. Алфавит для Base62 (62 символа)
        BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        
        # 2. Получаем MD5 хэш от ссылки в виде числа
        hasher = hashlib.md5(self.url.encode('utf-8'))
        num = int(hasher.hexdigest(), 16)
        
        # 3. Кодируем число в Base62
        short_hash = ""
        while num > 0:
            num, remainder = divmod(num, 62)
            short_hash = BASE62[remainder] + short_hash
            
        # 4. Обрезаем до нужной длины
        return short_hash[:length]


class StateMemory:
    """
    Таблица для хранения FSM-состояний.
    
    Колонки:
        id      INTEGER PRIMARY KEY  - ключ (user_id)
        states  TEXT                 - имя состояния
        data    TEXT                 - JSON-данные
    """
    _table_name = "statememory"

    def __init__(self, id: int, states: str = '', data: dict = None):
        self.id = id
        self.states = states
        self.data = data if data is not None else {}

class MySQLStorage(BaseStorage):
    """
    Синхронное хранилище FSM на YQL.
    
    Структура таблицы:
        CREATE TABLE statememory (
            id      INTEGER PRIMARY KEY,
            states  TEXT NOT NULL DEFAULT '',
            data    TEXT NOT NULL DEFAULT '{}'
        );
    """
    def __init__(self, 
                 db: 'ManageVK', 
                 table_name: str = FSMMemory.__name__.lower(),
                 check_same_thread: bool = False) -> None:
        """
        Args:
            db: объект БД (или ':memory:')
            table_name: имя таблицы
            check_same_thread: для Serverless/многопоточности - False
        """
        self.db = db
        self.table_name = table_name
        self.check_same_thread = check_same_thread

    def _key_to_id(self, key: str) -> int:
        """
        Преобразование ключа в id.
        Ключ - это user_id (int). Если не число - используем hash. 
        """
        try:
            return int(key)
        except (ValueError, TypeError):
            # Отрицательный hash, чтобы не пересекаться с реальными ID
            return -abs(hash(str(key)) % (10 ** 15))

    def _ensure_row(self, key: str) -> None:
        """Создает строку, если её нет"""
        row_id = self._key_to_id(key)
        obj = FSMMemory(id=row_id)
        self.db.upsert(obj)


    def _fetch(self, key: str) -> FSMMemory:
        """Получить строку по ключу"""
        row_id = self._key_to_id(key)
        return self.db.select_id(FSMMemory, row_id)

    # ---------- State ----------

    def set_state(self, key: str, state: Optional[str] = None) -> None:
        """Установить состояние"""
        row_id = self._key_to_id(key)
        state_str = state if state else ""        
        self.db.update(FSMMemory(id=row_id, states=state_str))

    def get_state(self, key: str):
        """Получить состояние"""
        row = self._fetch(key)
        if row is None:
            return None
        state = row.states
        return state if state != '' else None

    # ---------- Data ----------

    def set_data(self, key, data):
        """Полностью перезаписать данные"""
        row_id = self._key_to_id(key)
        user: FSMMemory = self.db.select_id(FSMMemory, row_id)
        if user:
            user.data = data
            self.db.update(user)
        else:
            user = FSMMemory(id=row_id, data=data)
            self.db.insert(user)


    def get_data(self, key):
        """Получить данные"""
        row = self._fetch(key)
        if row is None:
            return {}
        if not row.data:
            return {}
        try:
            return row.data
        except Exception as e:
            logger.error(f"Parse error data from key={key}: {e}")
            return {}

    def update_data(self, key, data):
        """Обновить данные (слияние)"""
        current = self.get_data(key)
        current.update(data)
        self.set_data(key, current)
        return current

    # ---------- Clear ----------

    def clear(self, key: str) -> None:
        """Очистить состояние и данные"""
        row_id = self._key_to_id(key)
        self.db.delete_id(FSMMemory, row_id)

    def clear_state(self, key):
        """Очистить только состояние"""
        row_id = self._key_to_id(key)
        row_id = self._key_to_id(key)
        user: FSMMemory = self.db.select_id(FSMMemory, row_id)
        user.states = ''
        self.db.update(user)

class ManageVK(DB):
    def set_subject_user(self, user_id: int, subject: str):
        try:
            query = f"UPDATE {Users.__name__.lower()} SET subject = %s WHERE id = %s"
            connection = self.get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute(query, (subject, user_id))
            connection.commit()
            return True
        except Exception as e:
            logger.error(f'DB: {e}')

    def get_user_by_id(self, user_id: int):
        try:
            return self.select_id(Users, user_id)
        except Exception as e:
            logger.error(e)

    def get_info(self, user_id: int):
        try:
            result = self.select_id(Students, user_id)
            if result:
                return result
            return self.get_user_by_id(user_id)
        except Exception as e:
            logger.error(e)

    def get_tasks(self, user_id: int):        
        try:
            student: Students = self.select_id(Students, user_id)       
            return {
                'subject': student.subject,
                'tasks': student.tasks
                }
        except Exception as e:
            logger.error(e)

    def set_percent(self, user_id: int, percent: int):
        try:
            query = f"UPDATE {Students.__name__.lower()} SET prize = %s WHERE id = %s"
            connection = self.get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute(query, (percent, user_id))
            connection.commit()
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    def add_task(self, user_id: int,  task_id: str, score: int):
        try:
            # tasks = self.get_tasks(user_id)['tasks']
            # tasks[task_id] = score
            # logger.info(tasks)
            # query = f"DECLARE $key AS Uint64; DECLARE $tasks AS JsonDocument; UPDATE {Students.__name__.lower()} SET tasks = $tasks WHERE id = $key"
            # self.qpool.execute_with_retries(query, {'$key': ydb.TypedValue(user_id, DATATYPE[int]), '$tasks': ydb.TypedValue(json.dumps(tasks), DATATYPE[dict])})
            # self._conn.execute(
            #     f"UPDATE {Students.__name__} SET tasks = ? WHERE id = ?",
            #     (json.dumps(tasks), user_id)
            # )
            # self._conn.commit()
            student: Students = self.select_id(Students, user_id)
            student.tasks[task_id] = score
            self.update(student)
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    # def get_mailing_all(self):
    #     query = f"SELECT id FROM {Users.__name__.lower()}"
    #     try:
    #         # self.cursor.execute(query)
    #         rows = self.qpool.execute_with_retries(query)          
    #         return (row['id'] for row in rows)
    #     except Exception as e:
    #         logger.error(e)

    # def get_mailing_subject(self, subject: str):
    #     query = f"DECLARE $subject AS Utf8; SELECT id FROM {Users.__name__.lower()} WHERE subject = $subject"
    #     try:
    #         # self.cursor.execute(query, (subject,))
    #         # rows = self.cursor.fetchall()            
    #         # return (row[0] for row in rows)
    #         result = self.qpool.execute_with_retries(query, {'$subject': ydb.TypedValue(subject, DATATYPE[str])})          
    #         return (row['id'] for row in result)
    #     except Exception as e:
    #         logger.error(e)

    # def get_mailing_profile(self, subject: str, profile: str):
    #     query = f"DECLARE $subject AS Utf8; DECLARE $profile AS Utf8; SELECT id FROM {Students.__name__.lower()} WHERE subject = $subject AND profile = $profile"
    #     try:
    #         # self.cursor.execute(query, (subject, profile))
    #         # rows = self.cursor.fetchall()  
    #         result = self.qpool.execute_with_retries(query, {'$subject': ydb.TypedValue(subject, DATATYPE[str]), '$profile': ydb.TypedValue(profile, DATATYPE[str])})          
    #         return (row['id'] for row in result)
    #     except Exception as e:
    #         logger.error(e)

    # def get_mailing_group(self, subject: str, profile: str, group: str):
    #     query = f"DECLARE $subject AS Utf8; DECLARE $profile AS Utf8; DECLARE $group AS Utf8; SELECT id FROM {Students.__name__.lower()} WHERE subject = $subject AND profile = $profile AND group_id = $group"
    #     try:
    #         # self.cursor.execute(query, (subject, profile, group))
    #         # rows = self.cursor.fetchall() 
    #         params = {'$subject': ydb.TypedValue(subject, DATATYPE[str]), '$profile': ydb.TypedValue(profile, DATATYPE[str]), '$group': ydb.TypedValue(group, DATATYPE[str])}  
    #         result = self.qpool.execute_with_retries(query, params)           
    #         return (row['id'] for row in result)
    #     except Exception as e:
    #         logger.error(e)

    def set_stepik_id(self, user_id: int, course_id: int, stepik_id: int, score: int):
        try:
            step = Stepik(id=user_id, course_id=course_id, stepik_id=stepik_id, score=score)
            self.insert(step)
        except Exception as e:
            logger.error(f'DB {e}')

    def update_score_stepik(self, user_id: int, score: int):
        try:
            query = f"UPDATE {Stepik.__name__} SET score = %s WHERE id = %s"
            connection = self.get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute(query, (score, user_id))
            connection.commit()
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    def get_score_stepik(self, user_id: int):
        try:
            return self.select_id(Stepik, user_id)
        except Exception as e:
            logger.error(e)

    def update_stepik_id(self, user_id: int, stepik_id: int):
        try:
            query = f"UPDATE {Stepik.__name__} SET stepik_id = %s WHERE id = %s"
            connection = self.get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute(query, (stepik_id, user_id))
            connection.commit()
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    def get_all_stepik(self) -> List[Stepik]:
        try:
            return self.select(Stepik)
        except Exception as e:
            logger.error(e)

    def get_all_student(self):
        try:
            return self.select(Students)
        except Exception as e:
            logger.error(e)

    def get_student_name(self, full_name: str):
        try:
            query = f"SELECT * FROM {Students.__name__.lower()} WHERE full_name = %s"
            connection = self.get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute(query, (full_name, ))
            return cursor.fetchone()
        except Exception as e:
            logger.error(e)

    def set_colab(self, user_id: int, url: str):
        data = Colab(url=url, user_id=user_id)
        try:
            self.insert(data)
        except Exception as e:
            logger.error(f'Database colab: {e}')

    def get_colab(self):
        try:
            return self.select(Colab)
        except Exception as e:
            logger.error(e)

    def get_colab_by_url(self, url: str):
        try:
            query = f"SELECT * FROM {Colab.__name__.lower()} WHERE url = %s"
            connection = self.get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute(query, (url, ))
            return cursor.fetchone()
        
        except Exception as e:
            logger.error(e)
