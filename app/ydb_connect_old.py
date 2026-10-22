import ydb
from ydb.iam import ServiceAccountCredentials
import os
import logging
from dotenv import load_dotenv
import hashlib
from typing import Any, Union, ClassVar, Optional, Dict, List
from pydantic import computed_field, BaseModel
from vkBot.fsm.storage.base import BaseStorage
import json

logger = logging.getLogger(__name__)

load_dotenv()

class set_key:
    """Простой дескриптор для создания свойств уровня класса."""
    def __init__(self, func):
        self.func = func
    def __get__(self, instance, owner):
        return self.func(owner)

class TypeSQL:
    def __init__(self, value: Any):
        self.value = value
        self.type = self.__class__.__name__

class Uint64(TypeSQL):
    def __init__(self, value: int):
        super().__init__(value)

    def __str__(self):
        return str(self.value)

class Utf8(TypeSQL):
    def __init__(self, value: str):
        super().__init__(value)

    def __str__(self):
        if isinstance(self.value, str):
            return self.value
        raise ValueError('Неправильный тип данных')

class Bool(TypeSQL):
    def __init__(self, value: bool):
        super().__init__(value) 

    def __str__(self):
        if isinstance(self.value, bool):
            return str(self.value).upper()
        raise ValueError('Неправильный тип данных')

class JsonDocument(TypeSQL):
    def __init__(self, value: Union[dict, BaseModel]):
        super().__init__(value) 
    
    def __str__(self):
        if isinstance(self.value, dict):
            return json.dumps(self.value)
        if isinstance(self.value, BaseModel):
            return self.value.model_dump_json()
        raise ValueError('Неправильный тип данных')

DATA = {
    int: Uint64,
    bool: Bool,
    str: Utf8,
    dict: JsonDocument
}     

DATATYPE = {
    str: ydb.PrimitiveType.Utf8,
    int: ydb.PrimitiveType.Uint64,
    bool: ydb.PrimitiveType.Bool, 
    dict: ydb.PrimitiveType.JsonDocument
}


class BaseTable(BaseModel):
    primary_key: ClassVar[str] = 'id'

    @classmethod
    def create_table(cls):
        fields = [f'{field_name} {DATA.get(field_info.annotation, JsonDocument).__name__}' 
                  for field_name, field_info in cls.model_fields.items()]
        fields.extend([f'{field_name} {DATA.get(field_info.return_type, JsonDocument).__name__}' 
                  for field_name, field_info in cls.model_computed_fields.items()])
        fields_sql = ',\n'.join(fields)
        text = f"""
CREATE TABLE IF NOT EXISTS `{cls.__name__.lower()}` (
{fields_sql}"""
        if cls.primary_key:
            text += f",\nPRIMARY KEY ({cls.primary_key})" 
        text += "\n);"
        return text

    def insert(self):
        dump = self.model_dump()
        text = '\n'.join([f'DECLARE ${name} AS {DATA.get(type(value), JsonDocument).__name__};' for name, value in dump.items()])
        placeholders = ', '.join([f'${name}' for name, _ in dump.items()])
        cols = ', '.join(dump.keys())
        # params =  {f'${name}': ydb.TypedValue(value, DATATYPE.get(type(value))) for name, value in dump.items()}
        params = self.values(dump)
        return f"{text}\nINSERT INTO `{self.__class__.__name__.lower()}` ({cols}) VALUES ({placeholders});", params

    def upsert(self):
        dump = self.model_dump()
        text = '\n'.join([f'DECLARE ${name} AS {DATA.get(type(value), JsonDocument).__name__};' for name, value in dump.items()])
        placeholders = ', '.join([f'${name}' for name, _ in dump.items()])
        cols = ', '.join(dump.keys())
        # params =  {f'${name}': ydb.TypedValue(value, DATATYPE.get(type(value))) for name, value in dump.items()}
        params = self.values(dump)
        return f"{text}\nUPSERT INTO `{self.__class__.__name__.lower()}` ({cols}) VALUES ({placeholders});", params

    @classmethod
    def select(cls):
        return f"SELECT * FROM `{cls.__name__.lower()}`;"

    @classmethod
    def drop(cls):
        return f"DROP TABLE IF EXISTS `{cls.__name__.lower()}`;"

    def values(self, dump: dict):
        return {f'${name}': self.validate_data(value) for name, value in dump.items()}
        # return (str(DATA[field_info.annotation](self.model_dump().get(field_name, dict))) for field_name, field_info in self.model_fields.items())
    
    def validate_data(self, value):
        tp = DATATYPE.get(type(value), JsonDocument)
        if tp == ydb.PrimitiveType.JsonDocument:
            return ydb.TypedValue(json.dumps(value), tp)
        return ydb.TypedValue(value, tp)

    @classmethod
    def select_id(cls, key):
        params = {"$key": ydb.TypedValue(key, DATATYPE.get(type(key)))}
        return f"DECLARE $key AS {DATA.get(type(key), JsonDocument).__name__};\nSELECT * FROM `{cls.__name__.lower()}` WHERE {cls.primary_key} = $key;", params

    @classmethod
    def delete_id(cls, key):
        params = {"$key": ydb.TypedValue(key, DATATYPE.get(type(key)))}
        return f"DECLARE $key AS {DATA.get(type(key), JsonDocument).__name__};\nDELETE FROM `{cls.__name__.lower()}` WHERE {cls.primary_key} = $key;", params


    @classmethod
    def model_construct(cls, obj: dict):
        return cls(**{
            field: json.loads(value) if cls.model_fields[field].annotation == dict else value 
                for field, value in obj.items()
        })

class DB:
    def __init__(self):
        self.driver = self.create_driver()
        self.pool = ydb.SessionPool(self.driver)
        self.qpool = ydb.QuerySessionPool(self.driver)

    def create_tables(self, clses=BaseTable):
        with self.pool.checkout() as session:
            for cls in clses.__subclasses__():
                try:
                    query = cls.create_table()
                    session.execute_scheme(query)
                except Exception as e:
                    logger.error(e)
                    continue        
        
    @staticmethod
    def create_driver():
        key_path = os.getenv('YDB_SERVICE_ACCOUNT_KEY_PATH')

        credentials = ServiceAccountCredentials.from_file(key_path)
        driver_config = ydb.DriverConfig(
            database=os.getenv('YDB_DATABASE'),
            endpoint=os.getenv('YDB_ENDPOINT'),
            credentials=credentials
        )
        driver = ydb.Driver(driver_config)
        driver.wait(fail_fast=True, timeout=20)
        return driver

    def insert(self, table: BaseTable):
        query, params = table.insert()
        self.qpool.execute_with_retries(query, params)

    def upsert(self, table: BaseTable):
        query, params = table.upsert()
        self.qpool.execute_with_retries(query, params)

    def select(self, TableCls: type):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        with self.pool.checkout() as session:
            result_sets = session.transaction().execute(TableCls.select(), commit_tx=True)
            return [TableCls.model_construct(row) for row in result_sets[0].rows]

    def select_get_dict(self, TableCls: type):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        with self.pool.checkout() as session:
            result_sets = session.transaction().execute(TableCls.select(), commit_tx=True)
            return result_sets[0].rows

    def select_id(self, TableCls: type, key: Any):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        try:
            result_sets = self.qpool.execute_with_retries(*TableCls.select_id(key))
            return TableCls.model_validate(result_sets[0].rows[0])
        except Exception as e:
            logger.error(e)

    def delete_id(self, TableCls: type, key: Any):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        self.qpool.execute_with_retries(*TableCls.delete_id(key))


    def drop_table(self, TableCls: type):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        with self.pool.checkout() as session:
            session.execute_scheme(TableCls.drop())
        logger.info(f"Таблица {TableCls.__name__.lower()} удалена.")

    def query(self, text_query: str, data_query: tuple):
        try:
            results = self.qpool.execute_with_retries(text_query, data_query) 
            if results:
                return results[0].rows
        except Exception as e:
            logger.error(e)


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

class YQLStorage(BaseStorage):
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
        self.db.upsert(FSMMemory(id=row_id, states=state_str))

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
        query = f"DECLARE $key AS Uint64; DECLARE $data AS JsonDocument; UPDATE {FSMMemory.__name__.lower()} SET data = $data WHERE id = $key"
        self.db.qpool.execute_with_retries(query, 
                                           {'$key': ydb.TypedValue(row_id, DATATYPE[int]), 
                                            '$data': ydb.TypedValue(json.dumps(data, ensure_ascii=False), DATATYPE[dict])})
                    

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
        query = f"DECLARE $key AS Uint64; UPDATE {FSMMemory.__name__.lower()} SET states = '' WHERE id = $key"
        self.db.qpool.execute_with_retries(query, {'$key': ydb.TypedValue(row_id, DATATYPE[int])})


class ManageVK(DB):
    def set_subject_user(self, user_id: int, subject: str):
        try:
            query = f"DECLARE $key AS Uint64; DECLARE $subject AS Utf8; UPDATE {Users.__name__.lower()} SET subject = $subject WHERE id = $key"
            self.qpool.execute_with_retries(query, {'$key': ydb.TypedValue(user_id, DATATYPE[int]), '$subject': ydb.TypedValue(subject, DATATYPE[str])})
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
            query = f"DECLARE $key AS Uint64; DECLARE $prize AS Uint64; UPDATE {Students.__name__.lower()} SET prize = $prize WHERE id = $key"
            self.qpool.execute_with_retries(query, {'$key': ydb.TypedValue(user_id, DATATYPE[int]), '$prize': ydb.TypedValue(percent, DATATYPE[int])})
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    def add_task(self, user_id: int,  task_id: str, score: int):
        try:
            tasks = self.get_tasks(user_id)['tasks']
            tasks[task_id] = score
            query = f"DECLARE $key AS Uint64; DECLARE $tasks AS JsonDocument; UPDATE {Students.__name__.lower()} SET tasks = $tasks WHERE id = $key"
            self.qpool.execute_with_retries(query, {'$key': ydb.TypedValue(user_id, DATATYPE[int]), '$tasks': ydb.TypedValue(json.dumps(tasks), DATATYPE[dict])})
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    def get_mailing_all(self):
        query = f"SELECT id FROM {Users.__name__.lower()}"
        try:
            rows = self.qpool.execute_with_retries(query)          
            return (row['id'] for row in rows)
        except Exception as e:
            logger.error(e)

    def get_mailing_subject(self, subject: str):
        query = f"DECLARE $subject AS Utf8; SELECT id FROM {Users.__name__.lower()} WHERE subject = $subject"
        try:
            result = self.qpool.execute_with_retries(query, {'$subject': ydb.TypedValue(subject, DATATYPE[str])})          
            return (row['id'] for row in result)
        except Exception as e:
            logger.error(e)

    def get_mailing_profile(self, subject: str, profile: str):
        query = f"DECLARE $subject AS Utf8; DECLARE $profile AS Utf8; SELECT id FROM {Students.__name__.lower()} WHERE subject = $subject AND profile = $profile"
        try: 
            result = self.qpool.execute_with_retries(query, {'$subject': ydb.TypedValue(subject, DATATYPE[str]), '$profile': ydb.TypedValue(profile, DATATYPE[str])})          
            return (row['id'] for row in result)
        except Exception as e:
            logger.error(e)

    def get_mailing_group(self, subject: str, profile: str, group: str):
        query = f"DECLARE $subject AS Utf8; DECLARE $profile AS Utf8; DECLARE $group AS Utf8; SELECT id FROM {Students.__name__.lower()} WHERE subject = $subject AND profile = $profile AND group_id = $group"
        try:
            params = {'$subject': ydb.TypedValue(subject, DATATYPE[str]), '$profile': ydb.TypedValue(profile, DATATYPE[str]), '$group': ydb.TypedValue(group, DATATYPE[str])}  
            result = self.qpool.execute_with_retries(query, params)           
            return (row['id'] for row in result)
        except Exception as e:
            logger.error(e)

    def set_stepik_id(self, user_id: int, course_id: int, stepik_id: int, score: int):
        # self._conn.execute(
        #     f"""
        #     INSERT INTO {Stepik.__name__.lower()} (id, course_id, stepik_id, score)
        #     VALUES (?, ?, ?, ?)
        #     """,
        #     (user_id, course_id, stepik_id, score)
        # )

        # self._conn.commit()
        step = Stepik(id=user_id, course_id=course_id, stepik_id=stepik_id, score=score)
        self.upsert(step)

    def update_score_stepik(self, user_id: int, score: int):
        try:
            # self._conn.execute(
            #     ,
            #     (score, user_id)
            # )
            # self._conn.commit()
            query = f"DECLARE $score AS Uint64; DECLARE $key AS Uint64; UPDATE {Stepik.__name__} SET score = $score WHERE id = $key"
            params = {'$key': ydb.TypedValue(user_id, DATATYPE[int]), "$score": ydb.TypedValue(score, DATATYPE[int])}
            self.qpool.execute_with_retries(query, params)
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    def get_score_stepik(self, user_id: int):
        # query = f"SELECT * FROM {Stepik.__name__.lower()} WHERE id = ?"
        try:
            # self.cursor.execute(query, (user_id,))
            # rows = self.cursor.fetchone()            
            # return Stepik.model_construct(*rows)
            return self.select_id(Stepik, user_id)
        except Exception as e:
            logger.error(e)

    def update_stepik_id(self, user_id: int, stepik_id: int):
        try:
            # self._conn.execute(
                
            #     (stepik_id, user_id)
            # )
            # self._conn.commit()
            query = f"DECLARE $step AS Uint64; DECLARE $key AS Uint64; UPDATE {Stepik.__name__} SET stepik_id = $step WHERE id = $key"
            params = {'$key': ydb.TypedValue(user_id, DATATYPE[int]), "$step": ydb.TypedValue(stepik_id, DATATYPE[int])}
            self.qpool.execute_with_retries(query, params)
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    def get_all_stepik(self) -> List[Stepik]:
        # query = f"SELECT * FROM {Stepik.__name__.lower()}"
        try:
            # self.cursor.execute(query)
            # rows = self.cursor.fetchall()            
            # return [Stepik.model_construct(*row) for row in rows]
            return self.select(Stepik)
        except Exception as e:
            logger.error(e)

    def get_all_student(self):
        # query = f"SELECT * FROM {Students.__name__.lower()}"
        try:
            # self.cursor.execute(query)
            # rows = self.cursor.fetchall()            
            # return [Students.model_construct(*row) for row in rows]
            return self.select(Students)
        except Exception as e:
            logger.error(e)

    def get_student_name(self, full_name: str):
        try:
            # self.cursor.execute(query, (full_name, ))
            # rows = self.cursor.fetchone()            
            # return Students.model_construct(*rows)
            query = f"DECLARE $name AS Utf8; SELECT * FROM {Students.__name__.lower()} WHERE full_name = $name"
            params = {'$name': ydb.TypedValue(full_name, DATATYPE[str])}
            return self.qpool.execute_with_retries(query, params)[0].rows[0]
        except Exception as e:
            logger.error(e)

    def set_colab(self, user_id: int, url: str):
        data = Colab(url=url, user_id=user_id)
        try:
            self.insert(data)
        except Exception as e:
            logger.error(f'Database colab: {e}')

    def get_colab(self):
        # query = f"SELECT * FROM {Colab.__name__.lower()}"
        try:
            # self.cursor.execute(query)
            # rows = self.cursor.fetchall()            
            # return [Colab.model_construct(*row) for row in rows]
            return self.select(Colab)
        except Exception as e:
            logger.error(e)

    def get_colab_by_url(self, url: str):
        try:
            query = f"DECLARE $url AS Utf8; SELECT * FROM {Colab.__name__.lower()} WHERE url = $url"
            params = {'$url': ydb.TypedValue(url, DATATYPE[str])}
            return self.qpool.execute_with_retries(query, params)[0].rows[0]
            # self.cursor.execute(query, (url, ))
            # rows = self.cursor.fetchone()            
            # return Colab.model_construct(*rows) 

        except Exception as e:
            logger.error(e)
