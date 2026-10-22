import asyncio
import json
import logging
import os
from typing import Any, ClassVar, List, Optional, Union

from pydantic import BaseModel

logger = logging.getLogger(__name__)

class set_key:
    """Простой дескриптор для создания свойств уровня класса."""
    def __init__(self, func):
        self.func = func
    def __get__(self, instance, owner):
        return self.func(owner)

class BaseTable(BaseModel):
    primary_key: ClassVar[str] = set_key(lambda cls: "id") 

    @classmethod
    def create_table(cls):
        # Исправлено: Для первичного ключа используем INT, для обычных строк VARCHAR(255)
        fields = []
        for field_name, field_info in cls.model_fields.items():
            if field_name == cls.primary_key:
                sql_type = "INT NOT NULL AUTO_INCREMENT PRIMARY KEY" if field_info.annotation is int else "VARCHAR(255) PRIMARY KEY"
            else:
                annotation = field_info.annotation
                if annotation is int: sql_type = "BIGINT"
                elif annotation is float: sql_type = "DOUBLE"
                elif annotation is bool: sql_type = "BOOLEAN"
                elif annotation is str: sql_type = "VARCHAR(255)"
                else: sql_type = "JSON" # Для dict, list и вложенных BaseModel
            
            fields.append(f"`{field_name}` {sql_type}")
            
        field = ',\n'.join(fields)
        return f"CREATE TABLE IF NOT EXISTS `{cls.__name__.lower()}` ({field}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"

    def _prepare_params(self):
        """Вспомогательный метод для очистки параметров."""
        raw_data = self.model_dump()
        clean_params = {}
        for key, val in raw_data.items():
            if isinstance(val, (dict, list)):
                clean_params[key] = json.dumps(val, ensure_ascii=False)
            elif isinstance(val, bool):
                clean_params[key] = int(val) # Переводим в 1/0 для MySQL BOOLEAN
            else:
                clean_params[key] = val
        return clean_params

    def insert(self):
        """Исправлено: Корректный синтаксис INSERT INTO ... VALUES."""
        table_name = self.__class__.__name__.lower()
        clean_data = self._prepare_params()
        
        fields = [f"`{k}`" for k in clean_data.keys()]
        placeholders = ", ".join(["%s"] * len(clean_data))
        
        query = f"INSERT INTO `{table_name}` ({', '.join(fields)}) VALUES ({placeholders});"
        return query, tuple(clean_data.values())

    def replace(self):
        """Новый метод: Идеально для FSM. Создает запись или перезаписывает её, если ID существует."""
        table_name = self.__class__.__name__.lower()
        clean_data = self._prepare_params()
        
        fields = [f"`{k}`" for k in clean_data.keys()]
        placeholders = ", ".join(["%s"] * len(clean_data))
        
        query = f"REPLACE INTO `{table_name}` ({', '.join(fields)}) VALUES ({placeholders});"
        return query, tuple(clean_data.values())

    def update(self):
        """Исправлено: Корректный синтаксис UPDATE ... SET ... WHERE id = %s."""
        table_name = self.__class__.__name__.lower()
        clean_data = self._prepare_params()
        pk_field = self.primary_key
        
        # ID убираем из SET, так как он будет использоваться только в WHERE
        pk_value = clean_data.pop(pk_field, None)
        
        fields = list(clean_data.keys())
        set_clause = ", ".join([f"`{field}` = %s" for field in fields])
        
        query = f"UPDATE `{table_name}` SET {set_clause} WHERE `{pk_field}` = %s;"
        params = tuple(clean_data.values()) + (pk_value,)
        
        return query, params

    @classmethod
    def select(cls):
        return f"SELECT * FROM `{cls.__name__.lower()}`;"

    @classmethod
    def drop(cls):
        return f"DROP TABLE IF EXISTS `{cls.__name__.lower()}`;"

    @classmethod
    def select_id(cls, key):
        return f"SELECT * FROM `{cls.__name__.lower()}` WHERE `{cls.primary_key}` = %s;", (key, )

    @classmethod
    def delete_id(cls, key):
        return f"DELETE FROM `{cls.__name__.lower()}` WHERE `{cls.primary_key}` = %s;", (key, )

    @classmethod
    def from_db(cls, obj: Optional[dict]):
        """Исправлено: Защита от None и безопасный парсинг JSON полей."""
        if not obj:
            return None
        
        prepared = {}
        for field, value in obj.items():
            if field not in cls.model_fields:
                continue
            
            # Если поле в базе данных представлено строкой JSON, парсим его обратно в dict
            if cls.model_fields[field].annotation == dict and isinstance(value, str):
                try:
                    prepared[field] = json.loads(value) if value else {}
                except Exception:
                    prepared[field] = {}
            else:
                prepared[field] = value
        return cls(**prepared)


class DB:
    """
    Асинхронная работа с MySQL (aiomysql, пул соединений).

    Параметры берутся из переменных окружения DB_USER, DB_PASSWORD, DB_HOST,
    DB_NAME (и опционально DB_PORT). Значений по умолчанию нет намеренно:
    логины/пароли/имена БД не должны жить в коде.

        db = DB()
        await db.connect()           # или лениво — при первом запросе
        await db.save(row)
        row = await db.select_id(MyTable, 1)
        await db.close()
    """

    def __init__(self, *, minsize: int = 1, maxsize: int = 10):
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.host = os.getenv('DB_HOST')
        self.name = os.getenv('DB_NAME')
        self.port = int(os.getenv('DB_PORT', '3306'))
        self.minsize = minsize
        self.maxsize = maxsize
        self._pool = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self):
        """Создаёт пул. Пул привязан к event loop — при смене loop (serverless) пересоздаётся."""
        import aiomysql

        loop = asyncio.get_running_loop()
        if self._pool is not None and self._loop is loop:
            return self._pool
        missing = [n for n, v in (("DB_USER", self.user), ("DB_PASSWORD", self.password),
                                  ("DB_HOST", self.host), ("DB_NAME", self.name)) if not v]
        if missing:
            raise RuntimeError(f"Не заданы переменные окружения: {', '.join(missing)}")
        self._pool = await aiomysql.create_pool(
            host=self.host, port=self.port, user=self.user, password=self.password,
            db=self.name, charset='utf8mb4', autocommit=True,
            minsize=self.minsize, maxsize=self.maxsize,
            cursorclass=aiomysql.DictCursor,
        )
        self._loop = loop
        return self._pool

    async def close(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None and self._loop is asyncio.get_running_loop():
            pool.close()
            await pool.wait_closed()

    async def __aenter__(self) -> "DB":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def _execute(self, query: str, params: Any = None, fetch: Optional[str] = None):
        """fetch: None | 'one' | 'all'"""
        pool = await self.connect()
        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(query, params)
                if fetch == 'one':
                    return await cursor.fetchone()
                if fetch == 'all':
                    return await cursor.fetchall()
        return None

    async def create_tables(self, clses=BaseTable):
        pool = await self.connect()
        async with pool.acquire() as connection:
            for cls in clses.__subclasses__():
                try:
                    async with connection.cursor() as cursor:
                        await cursor.execute(cls.create_table())
                except Exception as e:
                    logger.error(f"Ошибка создания таблицы {cls.__name__}: {e}")

    async def drop_table(self, TableCls: type):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        await self._execute(TableCls.drop())
        logger.info(f"Таблица {TableCls.__name__.lower()} удалена.")

    async def save(self, table: BaseTable):
        """Рекомендуемый метод вместо insert: создаёт или обновляет запись (REPLACE)."""
        query, params = table.replace()
        await self._execute(query, params)

    async def insert(self, table: BaseTable):
        query, params = table.insert()
        await self._execute(query, params)

    async def update(self, table: BaseTable):
        query, params = table.update()
        await self._execute(query, params)

    async def select(self, TableCls: type) -> List[Any]:
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        rows = await self._execute(TableCls.select(), fetch='all')
        return [TableCls.from_db(row) for row in rows or []]

    async def select_id(self, TableCls: type, key: Any):
        """None, если записи нет или запрос не удался (FSM это учтёт)."""
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        try:
            query, params = TableCls.select_id(key)
            row = await self._execute(query, params, fetch='one')
            return TableCls.from_db(row) if row else None
        except Exception as e:
            logger.error(e)
            return None

    async def delete_id(self, TableCls: type, key: Any):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        query, params = TableCls.delete_id(key)
        await self._execute(query, params)
