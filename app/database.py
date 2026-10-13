from typing import Optional, Dict, Any
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
    subject: str
    group_id: str
    profile: str
    fine: int = 0
    prize: int = 0
    bonus: dict = {}
    tasks: dict = {'SO': 0}

class StateMemory(BaseTable):
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

# class FSMContext:
#     def __init__(self, storage: 'SQLiteStorage', user_id: int) -> None:
#         self.storage = storage
#         self.user_id = user_id

#     def set_state(self, state: Any = None) -> None:
#         # Извлекаем строковое значение стейта
#         state_str = state.state if hasattr(state, 'state') else state        
        
#         query = """
#                 INSERT OR REPLACE INTO statememory (id, states, data)
#                 VALUES (
#                     ?, 
#                     ?, 
#                     COALESCE((SELECT data FROM statememory WHERE id = ?), '{}')
#                 )
#             """
#         self.storage.db.cursor.execute(query, (self.user_id, state_str, self.user_id))
#         self.storage.db._conn.commit()

#     def get_state(self) -> Optional[str]: 
#         query = "SELECT state FROM statememory WHERE id = ?"
#         row = self.storage.db.query_get(query, (self.user_id,))
#         return row[0][0] if row else None
    
#     def set_data(self, data: Dict[str, Any]) -> None: 
#         json_data = json.dumps(data, ensure_ascii=False)
#         query = """
#                 INSERT OR REPLACE INTO statememory (id, states, data)
#                 VALUES (
#                     ?, 
#                     (SELECT states FROM statememory WHERE id = ?), 
#                     ?
#                 )
#         """
#         self.storage.db.cursor.execute(query, (self.user_id, self.user_id, json_data))
#         self.storage.db._conn.commit()
        
#     def update_data(self, **kwargs: Any) -> Dict[str, Any]:
#         # Получаем текущие данные, обновляем их и сохраняем обратно
#         current_data = self.get_data()
#         current_data.update(kwargs)
#         self.set_data(current_data)
#         return current_data
    
#     def get_data(self) -> Dict[str, Any]: 
#         query = "SELECT data FROM statememory WHERE id = ?"
#         row = self.storage.db.query_get(query, (self.user_id,))
#         if row[0] and row[0][0]:
#             return json.loads(row[0][0])
#         return {} 
    
#     def clear(self) -> None:
#         # Удаляем запись о пользователе полностью
#         query = "DELETE FROM statememory WHERE id = ?"
#         self.storage.db.cursor.execute(query, (self.user_id,))
#         self.storage.db._conn.commit()

class SQLiteStorage(BaseStorage):
    """
    Синхронное хранилище FSM на SQLite.
    
    Структура таблицы:
        CREATE TABLE statememory (
            id      INTEGER PRIMARY KEY,
            states  TEXT NOT NULL DEFAULT '',
            data    TEXT NOT NULL DEFAULT '{}'
        );
    """
    def __init__(self, 
                 db: 'ManageVK', 
                 table_name: str = 'statememory',
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
        self.db._conn.execute(
            f"INSERT OR IGNORE INTO {self.table_name} (id, states, data) "
            "VALUES (?, '', '{})",
            (row_id, )
        )

    def _fetch(self, key: str):
        """Получить строку по ключу"""
        row_id = self._key_to_id(key)
        cur = self.db._conn.execute(
            f"SELECT id, states, data FROM {self.table_name} WHERE id = ?",
            (row_id, )
        )
        return cur.fetchone()

    # ---------- State ----------

    def set_state(self, key: str, state: Optional[str] = None) -> None:
        """Установить состояние"""
        row_id = self._key_to_id(key)
        state_str = state if state else ""        
    
        self.db.cursor.execute(f"INSERT INTO {self.table_name} (id, states, data)"
            "VALUES (?, ?, '{}')"
            "ON CONFLICT(id) DO UPDATE SET states = excluded.states", 
            (row_id, state_str))
        self.db._conn.commit()

    def get_state(self, key: str):
        """Получить состояние"""
        row = self._fetch(key)
        if row is None:
            return None
        state = row[1]
        return state if state else None

    # ---------- Data ----------

    def set_data(self, key, data):
        """Полностью перезаписать данные"""
        row_id = self._key_to_id(key)
        data_json = json.dumps(data, ensure_ascii=False)

        self.db._conn.execute(
            f"""
            INSERT INTO {self.table_name} (id, states, data)
            VALUES (?, '', ?)
            ON CONFLICT(id) DO UPDATE SET data = excluded.data
            """,
            (row_id, data_json)
        )
        self.db._conn.commit()

    def get_data(self, key):
        """Получить данные"""
        row = self._fetch(key)
        if row is None:
            return {}
        raw = row[2]
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
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
        self.db._conn.execute(
            f"DELETE FROM {self.table_name} WHERE id = ?",
            (row_id, )
        )
        self.db._conn.commit()

    def clear_state(self, key):
        """Очистить только состояние"""
        row_id = self._key_to_id(key)
        self.db._conn.execute(
            f"UPDATE {self.table_name} SET states = '' WHERE id = ?",
            (row_id,)
        )
        self.db._conn.commit()

class ManageVK(DB):
    def set_subject_user(self, user_id: int, subject: str):
        query = f"UPDATE users SET subject = ? WHERE id = ?"
        return self.query_add(query, (subject, user_id))

    def get_user_by_id(self, user_id: int):
        try:
            self.cursor.execute(f"SELECT * FROM {Users.__name__.lower()} WHERE id = ?", (user_id, ))
            rows = self.cursor.fetchall()
            return Users.model_construct(*rows[0])
        except Exception as e:
            logger.error(e)

    def get_info(self, user_id: int):
        query = f"SELECT * FROM {Students.__name__.lower()} WHERE id = ?"
        try:
            self.cursor.execute(query, (user_id, ))
            rows = self.cursor.fetchall()
            if len(rows) == 1:
                return Students.model_construct(*rows[0])
            return self.get_user_by_id(user_id)
        except Exception as e:
            logger.error(e)

    def get_tasks(self, user_id: int):
        query = f"SELECT subject, tasks FROM {Students.__name__.lower()} WHERE id = ?"
        try:
            self.cursor.execute(query, (user_id, ))
            rows = self.cursor.fetchone()            
            return {
                'subject': rows[0],
                'tasks': json.loads(rows[1])}
        except Exception as e:
            logger.error(e)

    def set_percent(self, user_id: int, percent: int):
        try:
            self._conn.execute(
                f"UPDATE {Students.__name__} SET prize = ? WHERE id = ?",
                (percent, user_id)
            )
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    def add_task(self, user_id: int,  task_id: str, score: int):
        try:
            tasks = self.get_tasks(user_id)['tasks']
            tasks[task_id] = score
            logger.info(tasks)
            self._conn.execute(
                f"UPDATE {Students.__name__} SET tasks = ? WHERE id = ?",
                (json.dumps(tasks), user_id)
            )
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    def get_mailing_all(self):
        query = f"SELECT id FROM {Users.__name__.lower()}"
        try:
            self.cursor.execute(query)
            rows = self.cursor.fetchall()            
            return (row[0] for row in rows)
        except Exception as e:
            logger.error(e)

    def get_mailing_subject(self, subject: str):
        query = f"SELECT id FROM {Users.__name__.lower()} WHERE subject = ?"
        try:
            self.cursor.execute(query, (subject,))
            rows = self.cursor.fetchall()            
            return (row[0] for row in rows)
        except Exception as e:
            logger.error(e)

    def get_mailing_profile(self, subject: str, profile: str):
        query = f"SELECT id FROM {Students.__name__.lower()} WHERE subject = ? AND profile = ?"
        try:
            self.cursor.execute(query, (subject, profile))
            rows = self.cursor.fetchall()            
            return (row[0] for row in rows)
        except Exception as e:
            logger.error(e)

    def get_mailing_group(self, subject: str, profile: str, group: str):
        query = f"SELECT id FROM {Students.__name__.lower()} WHERE subject = ? AND profile = ? AND group_id = ?"
        try:
            self.cursor.execute(query, (subject, profile, group))
            rows = self.cursor.fetchall()            
            return (row[0] for row in rows)
        except Exception as e:
            logger.error(e)

    def set_stepik_id(self, user_id: int, course_id: int, stepik_id: int, score: int):
        self._conn.execute(
            f"""
            INSERT INTO {Stepik.__name__.lower()} (id, course_id, stepik_id, score)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, course_id, stepik_id, score)
        )

        self._conn.commit()

    def update_score_stepik(self, user_id: int, score: int):
        try:
            self._conn.execute(
                f"UPDATE {Stepik.__name__} SET score = ? WHERE id = ?",
                (score, user_id)
            )
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    def get_score_stepik(self, user_id: int):
        query = f"SELECT * FROM {Stepik.__name__.lower()} WHERE id = ?"
        try:
            self.cursor.execute(query, (user_id,))
            rows = self.cursor.fetchone()            
            return Stepik.model_construct(*rows)
        except Exception as e:
            logger.error(e)

    def update_stepik_id(self, user_id: int, stepik_id: int):
        try:
            self._conn.execute(
                f"UPDATE {Stepik.__name__} SET stepik_id = ? WHERE id = ?",
                (stepik_id, user_id)
            )
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    def get_all_stepik(self):
        query = f"SELECT * FROM {Stepik.__name__.lower()}"
        try:
            self.cursor.execute(query)
            rows = self.cursor.fetchall()            
            return [Stepik.model_construct(*row) for row in rows]
        except Exception as e:
            logger.error(e)

    def get_all_student(self):
        query = f"SELECT * FROM {Students.__name__.lower()}"
        try:
            self.cursor.execute(query)
            rows = self.cursor.fetchall()            
            return [Students.model_construct(*row) for row in rows]
        except Exception as e:
            logger.error(e)

    def get_student_name(self, full_name: str):
        query = f"SELECT * FROM {Students.__name__.lower()} WHERE full_name = ?"
        try:
            self.cursor.execute(query, (full_name, ))
            rows = self.cursor.fetchone()            
            return Students.model_construct(*rows)
        except Exception as e:
            logger.error(e)

    def set_colab(self, user_id: int, url: str):
        data = Colab(url=url, user_id=user_id)
        self.add(data)

    def get_colab(self):
        query = f"SELECT * FROM {Colab.__name__.lower()}"
        try:
            self.cursor.execute(query)
            rows = self.cursor.fetchall()            
            return [Colab.model_construct(*row) for row in rows]
        except Exception as e:
            logger.error(e)

    def get_colab_by_url(self, url: str):
        query = f"SELECT * FROM {Colab.__name__.lower()} WHERE url = ?"
        try:
            self.cursor.execute(query, (url, ))
            rows = self.cursor.fetchone()            
            return Colab.model_construct(*rows) 
        except Exception as e:
            logger.error(e)