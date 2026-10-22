import asyncio
import hashlib
import json
import logging
import os
import typing
from typing import Any, ClassVar, Dict, Iterable, List, Optional, Union

import ydb
import ydb.aio
from ydb.aio import iam as aio_iam
from dotenv import load_dotenv
from pydantic import BaseModel, computed_field

from vkBot.fsm.storage.base import BaseStorage

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


def _is_json_field(annotation: Any) -> bool:
    """dict, Dict[str, Any] и т.п. хранятся в колонке JsonDocument."""
    return annotation is dict or typing.get_origin(annotation) is dict


class BaseTable(BaseModel):
    primary_key: ClassVar[str] = 'id'

    @classmethod
    def table_name(cls) -> str:
        """Единственное место, где формируется имя таблицы (YDB различает регистр)."""
        return cls.__name__.lower()

    @classmethod
    def create_table(cls):
        fields = [f'{field_name} {DATA.get(field_info.annotation, JsonDocument).__name__}'
                  for field_name, field_info in cls.model_fields.items()]
        fields.extend([f'{field_name} {DATA.get(field_info.return_type, JsonDocument).__name__}'
                       for field_name, field_info in cls.model_computed_fields.items()])
        fields_sql = ',\n'.join(fields)
        text = f"CREATE TABLE IF NOT EXISTS `{cls.table_name()}` ({fields_sql}"
        if cls.primary_key:
            text += f",\nPRIMARY KEY ({cls.primary_key})"
        text += "\n);"
        return text

    def _write(self, verb: str, fields: Optional[Iterable[str]] = None):
        dump = self.model_dump()
        if fields is not None:
            dump = {name: dump[name] for name in fields}
        declares = '\n'.join(
            f'DECLARE ${name} AS {DATA.get(type(value), JsonDocument).__name__};'
            for name, value in dump.items())
        placeholders = ', '.join(f'${name}' for name in dump)
        cols = ', '.join(dump)
        return (f"{declares}\n{verb} INTO `{self.table_name()}` ({cols}) VALUES ({placeholders});",
                self.values(dump))

    def insert(self):
        return self._write('INSERT')

    def upsert(self, fields: Optional[Iterable[str]] = None):
        """
        fields — записать только эти колонки (в YDB UPSERT не трогает остальные колонки
        существующей строки). Без fields перезаписывается вся строка.
        """
        return self._write('UPSERT', fields)

    @classmethod
    def select(cls):
        return f"SELECT * FROM `{cls.table_name()}`;"

    @classmethod
    def drop(cls):
        return f"DROP TABLE IF EXISTS `{cls.table_name()}`;"

    def values(self, dump: dict):
        return {f'${name}': self.validate_data(value) for name, value in dump.items()}

    @staticmethod
    def validate_data(value):
        tp = DATATYPE.get(type(value))
        # всё, что не умеем сопоставить с примитивом (dict, list, ...), хранится как JSON
        if tp is None or tp == ydb.PrimitiveType.JsonDocument:
            return ydb.TypedValue(json.dumps(value, ensure_ascii=False), ydb.PrimitiveType.JsonDocument)
        return ydb.TypedValue(value, tp)

    @classmethod
    def select_id(cls, key):
        params = {"$key": ydb.TypedValue(key, DATATYPE.get(type(key)))}
        return (f"DECLARE $key AS {DATA.get(type(key), JsonDocument).__name__};\n"
                f"SELECT * FROM `{cls.table_name()}` WHERE {cls.primary_key} = $key;"), params

    @classmethod
    def delete_id(cls, key):
        params = {"$key": ydb.TypedValue(key, DATATYPE.get(type(key)))}
        return (f"DECLARE $key AS {DATA.get(type(key), JsonDocument).__name__};\n"
                f"DELETE FROM `{cls.table_name()}` WHERE {cls.primary_key} = $key;"), params

    @classmethod
    def from_row(cls, row: dict):
        """
        Строка YDB -> модель. Раньше это был model_construct(obj), который перекрывал
        одноимённый метод pydantic. JSON-колонки приходят строкой (str/bytes) — разбираем;
        NULL (например, колонка, не записанная через частичный UPSERT) пропускаем,
        чтобы сработало значение по умолчанию.
        """
        data = {}
        for field, value in row.items():
            if value is None:
                continue
            info = cls.model_fields.get(field)
            if info is not None and _is_json_field(info.annotation) and isinstance(value, (str, bytes)):
                value = json.loads(value)
            data[field] = value
        return cls(**data)


class DB:
    """
    Асинхронный клиент YDB (ydb.aio, QuerySessionPool).

    Один драйвер и один пул сессий на процесс; сессиями управляет пул, а
    ``close()`` останавливает пул и драйвер (раньше драйвер не останавливался
    никогда, а рядом жил второй, устаревший SessionPool).

        db = DB()
        await db.connect()             # необязательно: подключится при первом запросе
        ...
        await db.close()

    или   ``async with DB() as db: ...``

    Драйвер привязан к event loop. Если loop сменился (serverless: asyncio.run
    на каждый вызов), при следующем обращении создаётся новое подключение;
    корректно закрыть старое уже нельзя, поэтому в serverless вызывайте
    ``await db.close()`` в конце каждого вызова (см. Dispatcher.on_shutdown).
    """

    def __init__(self, connect_timeout: int = 20):
        self.connect_timeout = connect_timeout
        self._driver = None
        self._pool = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------ подключение
    async def create_driver(self):
        key_path = os.getenv('YDB_SERVICE_ACCOUNT_KEY_PATH')
        database = os.getenv('YDB_DATABASE')
        endpoint = os.getenv('YDB_ENDPOINT')
        missing = [name for name, value in (('YDB_SERVICE_ACCOUNT_KEY_PATH', key_path),
                                            ('YDB_DATABASE', database),
                                            ('YDB_ENDPOINT', endpoint)) if not value]
        if missing:
            raise RuntimeError(f"Не заданы переменные окружения: {', '.join(missing)}")

        credentials = aio_iam.ServiceAccountCredentials.from_file(key_path)
        driver = ydb.aio.Driver(ydb.DriverConfig(
            database=database, endpoint=endpoint, credentials=credentials))
        try:
            await driver.wait(fail_fast=True, timeout=self.connect_timeout)
        except BaseException:
            await driver.stop()   # не оставляем полуоткрытый драйвер
            raise
        return driver

    async def connect(self):
        """Идемпотентно; параллельные первые запросы создают одно подключение."""
        loop = asyncio.get_running_loop()
        if self._pool is not None and self._loop is loop:
            return self._pool
        if self._lock is None or self._lock_loop is not loop:
            self._lock, self._lock_loop = asyncio.Lock(), loop
        async with self._lock:
            if self._pool is not None and self._loop is loop:
                return self._pool
            if self._pool is not None:
                logger.warning("YDB: event loop сменился, подключение создаётся заново")
                self._driver = self._pool = None
            driver = await self.create_driver()
            try:
                pool = ydb.aio.QuerySessionPool(driver)
            except BaseException:
                await driver.stop()
                raise
            self._driver, self._pool, self._loop = driver, pool, loop
        return self._pool

    async def close(self) -> None:
        """Останавливает пул сессий и драйвер. Безопасно вызывать повторно."""
        pool, driver, loop = self._pool, self._driver, self._loop
        self._pool = self._driver = self._loop = None
        if loop is not None and loop is not asyncio.get_running_loop():
            logger.warning("YDB: подключение принадлежит другому loop — освободить нечем")
            return
        if pool is not None:
            try:
                await pool.stop()
            except Exception as e:
                logger.error(f"YDB: ошибка остановки пула: {e}")
        if driver is not None:
            try:
                await driver.stop()
            except Exception as e:
                logger.error(f"YDB: ошибка остановки драйвера: {e}")

    async def __aenter__(self) -> "DB":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    # ------------------------------------------------------------ запросы
    async def execute(self, query: str, params: Optional[dict] = None) -> List[dict]:
        """Выполняет запрос с ретраями, возвращает строки первого result set.
        Исключения пробрасываются."""
        pool = await self.connect()
        result_sets = await pool.execute_with_retries(query, params)
        return list(result_sets[0].rows) if result_sets else []

    async def create_tables(self, clses=BaseTable):
        for cls in clses.__subclasses__():
            try:
                await self.execute(cls.create_table())
            except Exception as e:
                logger.error(e)
                continue

    async def insert(self, table: BaseTable):
        query, params = table.insert()
        await self.execute(query, params)

    async def upsert(self, table: BaseTable, fields: Optional[Iterable[str]] = None):
        query, params = table.upsert(fields)
        await self.execute(query, params)

    @staticmethod
    def _check_class(TableCls: type) -> None:
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")

    async def select(self, TableCls: type):
        self._check_class(TableCls)
        rows = await self.execute(TableCls.select())
        return [TableCls.from_row(row) for row in rows]

    async def select_get_dict(self, TableCls: type):
        self._check_class(TableCls)
        return await self.execute(TableCls.select())

    async def select_id(self, TableCls: type, key: Any):
        """Модель или None (записи нет либо запрос не удался — ошибка пишется в лог)."""
        self._check_class(TableCls)
        try:
            rows = await self.execute(*TableCls.select_id(key))
            return TableCls.from_row(rows[0]) if rows else None
        except Exception as e:
            logger.error(e)

    async def delete_id(self, TableCls: type, key: Any):
        self._check_class(TableCls)
        await self.execute(*TableCls.delete_id(key))

    async def drop_table(self, TableCls: type):
        self._check_class(TableCls)
        await self.execute(TableCls.drop())
        logger.info(f"Таблица {TableCls.table_name()} удалена.")

    async def query(self, text_query: str, data_query: Optional[dict] = None):
        """Произвольный запрос; при ошибке — лог и None (как раньше)."""
        try:
            return await self.execute(text_query, data_query)
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





class YQLStorage(BaseStorage):
    """
    Асинхронное хранилище FSM в YDB (таблица FSMMemory: id, states, data).

    Каждая операция пишет только свою колонку (частичный UPSERT), поэтому
    ``set_state`` больше не затирает ``data`` (раньше UPSERT всей строки сбрасывал
    data в ``{}``), а ``set_data`` работает и для ещё не существующей строки.

    Ошибки БД пробрасываются наверх (диспетчер залогирует их), а не
    превращаются молча в «состояния нет».
    ``close()`` закрывает переданный DB.
    """

    def __init__(self, db: 'DB', table_name: str = FSMMemory.table_name()) -> None:
        self.db = db
        self.table_name = table_name

    @staticmethod
    def _key_to_id(key: Union[str, int]) -> int:
        """
        Ключ -> Uint64. Неотрицательные числа (user_id) — как есть. Остальное
        (отрицательные id сообществ, строки) — стабильный хэш в диапазоне >= 2**63,
        чтобы не пересекаться с реальными ID. Встроенный hash() не годится:
        он меняется от запуска к запуску.
        """
        try:
            number = int(key)
            if number >= 0:
                return number
        except (ValueError, TypeError):
            pass
        digest = hashlib.blake2b(str(key).encode('utf-8'), digest_size=8).digest()
        return int.from_bytes(digest, 'big') | (1 << 63)

    async def _upsert(self, key, column: str, type_name: str, value: ydb.TypedValue) -> None:
        query = (f"DECLARE $id AS Uint64; DECLARE $v AS {type_name};\n"
                 f"UPSERT INTO `{self.table_name}` (id, {column}) VALUES ($id, $v);")
        params = {'$id': BaseTable.validate_data(self._key_to_id(key)), '$v': value}
        await self.db.execute(query, params)

    async def _read(self, key, column: str):
        query = (f"DECLARE $id AS Uint64;\n"
                 f"SELECT {column} FROM `{self.table_name}` WHERE id = $id;")
        rows = await self.db.execute(query, {'$id': BaseTable.validate_data(self._key_to_id(key))})
        return rows[0][column] if rows else None

    # ---------- State ----------
    async def set_state(self, key: str, state: Optional[str] = None) -> None:
        await self._upsert(key, 'states', 'Utf8', BaseTable.validate_data(state or ''))

    async def get_state(self, key: str) -> Optional[str]:
        state = await self._read(key, 'states')
        return state if state else None

    # ---------- Data ----------
    async def set_data(self, key, data) -> None:
        await self._upsert(key, 'data', 'JsonDocument', BaseTable.validate_data(dict(data)))

    async def get_data(self, key) -> Dict[str, Any]:
        raw = await self._read(key, 'data')
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except Exception as e:
            logger.error(f"Parse error data from key={key}: {e}")
            return {}

    async def update_data(self, key, data) -> Dict[str, Any]:
        """Слияние. Чтение+запись — два запроса; события одного пользователя
        Dispatcher обрабатывает последовательно, поэтому гонок внутри процесса нет."""
        current = await self.get_data(key)
        current.update(data)
        await self.set_data(key, current)
        return current

    # ---------- Clear ----------
    async def clear(self, key: str) -> None:
        await self.db.delete_id(FSMMemory, self._key_to_id(key))

    async def clear_state(self, key: str) -> None:
        query = f"DECLARE $id AS Uint64; UPDATE `{self.table_name}` SET states = '' WHERE id = $id;"
        await self.db.execute(query, {'$id': BaseTable.validate_data(self._key_to_id(key))})

    async def close(self) -> None:
        await self.db.close()


class ManageVK(DB):
    # ------------------------------------------------------------ вспомогательные
    async def _set_column(self, table: type, column: str, key: int, value: Any) -> bool:
        """UPDATE `table` SET column = value WHERE id = key. True при успехе, None при ошибке."""
        query = (f"DECLARE $key AS Uint64; DECLARE $value AS {DATA.get(type(value), JsonDocument).__name__};\n"
                 f"UPDATE `{table.table_name()}` SET {column} = $value WHERE id = $key;")
        try:
            await self.execute(query, {'$key': BaseTable.validate_data(key),
                                       '$value': BaseTable.validate_data(value)})
            return True
        except Exception as e:
            logger.error(f'Manage VK error: {e}')

    async def _ids(self, query: str, params: Optional[dict] = None) -> List[int]:
        """Список id; при ошибке — пустой список (раньше возвращался None, и цикл падал)."""
        try:
            return [row['id'] for row in await self.execute(query, params)]
        except Exception as e:
            logger.error(e)
            return []

    # ------------------------------------------------------------ пользователи / студенты
    async def set_subject_user(self, user_id: int, subject: str):
        return await self._set_column(Users, 'subject', user_id, subject)

    async def get_user_by_id(self, user_id: int):
        try:
            return await self.select_id(Users, user_id)
        except Exception as e:
            logger.error(e)

    async def get_info(self, user_id: int):
        try:
            result = await self.select_id(Students, user_id)
            if result:
                return result
            return await self.get_user_by_id(user_id)
        except Exception as e:
            logger.error(e)

    async def get_tasks(self, user_id: int):
        try:
            student: Students = await self.select_id(Students, user_id)
            return {
                'subject': student.subject,
                'tasks': student.tasks
            }
        except Exception as e:
            logger.error(e)

    async def set_percent(self, user_id: int, percent: int):
        return await self._set_column(Students, 'prize', user_id, percent)

    async def add_task(self, user_id: int, task_id: str, score: int):
        try:
            tasks = (await self.get_tasks(user_id))['tasks']
            tasks[task_id] = score
        except Exception as e:
            logger.error(f'Manage VK error: {e}')
            return None
        return await self._set_column(Students, 'tasks', user_id, tasks)

    # ------------------------------------------------------------ рассылки
    async def get_mailing_all(self):
        return await self._ids(f"SELECT id FROM `{Users.table_name()}`")

    async def get_mailing_subject(self, subject: str):
        query = (f"DECLARE $subject AS Utf8;\n"
                 f"SELECT id FROM `{Users.table_name()}` WHERE subject = $subject")
        return await self._ids(query, {'$subject': BaseTable.validate_data(subject)})

    async def get_mailing_profile(self, subject: str, profile: str):
        query = (f"DECLARE $subject AS Utf8; DECLARE $profile AS Utf8;\n"
                 f"SELECT id FROM `{Students.table_name()}` WHERE subject = $subject AND profile = $profile")
        return await self._ids(query, {'$subject': BaseTable.validate_data(subject),
                                       '$profile': BaseTable.validate_data(profile)})

    async def get_mailing_group(self, subject: str, profile: str, group: str):
        query = (f"DECLARE $subject AS Utf8; DECLARE $profile AS Utf8; DECLARE $group AS Utf8;\n"
                 f"SELECT id FROM `{Students.table_name()}` "
                 f"WHERE subject = $subject AND profile = $profile AND group_id = $group")
        return await self._ids(query, {'$subject': BaseTable.validate_data(subject),
                                       '$profile': BaseTable.validate_data(profile),
                                       '$group': BaseTable.validate_data(group)})

    # ------------------------------------------------------------ Stepik
    async def set_stepik_id(self, user_id: int, course_id: int, stepik_id: int, score: int):
        step = Stepik(id=user_id, course_id=course_id, stepik_id=stepik_id, score=score)
        await self.upsert(step)

    async def update_score_stepik(self, user_id: int, score: int):
        # раньше здесь было Stepik.__name__ (с заглавной) — такой таблицы нет, запрос падал
        return await self._set_column(Stepik, 'score', user_id, score)

    async def get_score_stepik(self, user_id: int):
        try:
            return await self.select_id(Stepik, user_id)
        except Exception as e:
            logger.error(e)

    async def update_stepik_id(self, user_id: int, stepik_id: int):
        return await self._set_column(Stepik, 'stepik_id', user_id, stepik_id)

    async def get_all_stepik(self) -> List[Stepik]:
        try:
            return await self.select(Stepik)
        except Exception as e:
            logger.error(e)

    async def get_all_student(self):
        try:
            return await self.select(Students)
        except Exception as e:
            logger.error(e)

    async def get_student_name(self, full_name: str):
        try:
            query = (f"DECLARE $name AS Utf8;\n"
                     f"SELECT * FROM `{Students.table_name()}` WHERE full_name = $name")
            return (await self.execute(query, {'$name': BaseTable.validate_data(full_name)}))[0]
        except Exception as e:
            logger.error(e)

    # ------------------------------------------------------------ Colab
    async def set_colab(self, user_id: int, url: str):
        data = Colab(url=url, user_id=user_id)
        try:
            await self.insert(data)
        except Exception as e:
            logger.error(f'Database colab: {e}')

    async def get_colab(self):
        try:
            return await self.select(Colab)
        except Exception as e:
            logger.error(e)

    async def get_colab_by_url(self, url: str):
        try:
            query = (f"DECLARE $url AS Utf8;\n"
                     f"SELECT * FROM `{Colab.table_name()}` WHERE url = $url")
            return (await self.execute(query, {'$url': BaseTable.validate_data(url)}))[0]
        except Exception as e:
            logger.error(e)
