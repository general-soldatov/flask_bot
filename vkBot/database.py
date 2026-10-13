import sqlite3
import json
from typing import Any, ClassVar, Union, Optional, Dict
from pydantic import BaseModel
import logging
from pathlib import Path
# import botocore.session
# from botocore.exceptions import ClientError
# from boto_orm.models.config import AWSConfig, AWSSession


logger = logging.getLogger(__name__)

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

class INTEGER(TypeSQL):
    def __init__(self, value: int):
        super().__init__(value)

    def __str__(self):
        return str(self.value)

class TEXT(TypeSQL):
    def __init__(self, value: str):
        super().__init__(value)

    def __str__(self):
        if isinstance(self.value, str):
            return self.value
        raise ValueError('Неправильный тип данных')

class BOOLEAN(TypeSQL):
    def __init__(self, value: bool):
        super().__init__(value) 

    def __str__(self):
        if isinstance(self.value, bool):
            return str(self.value).upper()
        raise ValueError('Неправильный тип данных')

class JSON(TypeSQL):
    def __init__(self, value: Union[dict, BaseModel]):
        super().__init__(value) 
    
    def __str__(self):
        if isinstance(self.value, dict):
            return json.dumps(self.value)
        if isinstance(self.value, BaseModel):
            return self.value.model_dump_json()
        raise ValueError('Неправильный тип данных')

DATA = {
    int: INTEGER,
    bool: BOOLEAN,
    str: TEXT,
    dict: JSON
}     


class BaseTable(BaseModel):
    primary_key: ClassVar[str] = set_key(lambda cls: "id") 

    @classmethod
    def create_table(cls):
        fields = [f'{field_name} {DATA.get(field_info.annotation, JSON).__name__}{" PRIMARY KEY" if field_name == cls.primary_key else ""}' 
                  for field_name, field_info in cls.model_fields.items()]
        return f"""
CREATE TABLE IF NOT EXISTS {cls.__name__.lower()} (
{',\n'.join(fields)}
);
            """

    def insert(self):
        placeholders = ", ".join(["?"] * len(self.model_fields))
        return f"INSERT INTO {self.__class__.__name__.lower()} VALUES ({placeholders})"

    def select(self):
        return f"SELECT * FROM {self.__class__.__name__.lower()}"

    def values(self):
        return tuple(str(DATA[field_info.annotation](self.model_dump().get(field_name, dict))) for field_name, field_info in self.model_fields.items())

    @classmethod
    def model_construct(cls, *values):
        return cls(**{
            field: json.loads(value) if cls.model_fields[field].annotation == dict else value 
                for field, value in zip(cls.model_fields, values)
        })

class DB:
    def __init__(self, path):
        self._conn = sqlite3.connect(path)
        # Подключаемся и работаем с SQLite локально
        self.cursor = self._conn.cursor()

    def create_tables(self, clses=BaseTable):
        for cls in clses.__subclasses__():
            try:
                query = cls.create_table()
                self.cursor.execute(query)
            except Exception as e:
                logger.error(e)
                continue        
        self._conn.commit()

    def drop_table(self, TableCls: type):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        query = f"DROP TABLE IF EXISTS {TableCls.__name__.lower()}"
        self.query_add(query, ())
        logger.info(f"Таблица {TableCls.__name__.lower()} удалена.")

    def add(self, table: BaseTable):
        query = table.insert()
        self.query_add(query, table.values())

    def get(self, TableCls: type):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        try:
            self.cursor.execute(f"SELECT * FROM {TableCls.__name__.lower()}")
            rows = self.cursor.fetchall()
            logger.info(f"Текущее количество записей в базе: {len(rows)}")
            return [TableCls.model_construct(*row) for row in rows]
        except Exception as e:
            logger.error(e)

    def query_add(self, text_query: str, data_query: tuple):
        try:
            self.cursor.execute(text_query, data_query)
            self._conn.commit()
            return True
        except Exception as e:
            logger.error(e)

    def query_get(self, text_query: str, params: Optional[tuple] = ()):
        try:
            self.cursor.execute(text_query, params)
            return self.cursor.fetchall()
        except Exception as e:
            logger.error(e)
        
        
# class SQLBucket:
#     def __init__(self, local_path: Path, bucket_name: str, 
#                  s3_path: str, session: AWSSession, 
#                  config: AWSConfig, Table):
#         self.local_path = local_path
#         self.s3_path = s3_path
#         self.bucket_name = bucket_name
#         _session = botocore.session.get_session()
#         _session.set_credentials(**session.model_dump())
#         self.s3 = _session.create_client(**config.model_dump())
#         # self.s3 = S3Manager(bucket_name, config, session)
#         self.Table = Table

#     def download_db(self):
#         """Скачивает файл БД из бакета, если он там существует."""
#         logger.info("Проверка наличия БД в бакете...")
#         try:
#             self.local_path.parent.mkdir(parents=True, exist_ok=True)
#             # 2. Запрашиваем объект
#             response = self.s3.get_object(Bucket=self.bucket_name, Key=self.s3_path)
            
#             # 3. Безопасно сохраняем в файл чанками (блоки по 1 МБ)
#             with open(self.local_path, 'wb') as file:
#                 for chunk in response['Body'].iter_chunks(chunk_size=1024 * 1024):
#                     file.write(chunk)
#             logger.info(f"БД успешно скачана во временный файл: {self.local_path}")
#         except ClientError as e:
#             if e.response['Error']['Code'] in ['404', 'NoSuchKey']:
#                 logger.warning('Файл БД не найден в бакете. Будет создана новая локальная БД.')
        
#             else:
#                 raise e

#     def upload_db(self):
#         """Выгружает обновленный файл БД обратно в бакет."""
#         if self.local_path.exists():
#             logger.info("Выгрузка измененной БД обратно в бакет...")
#             # 2. Открываем файл в режиме бинарного чтения ('rb') 
#             # и отправляем через метод put_object
#             with open(self.local_path, 'rb') as file_data:
#                 response = self.s3.put_object(
#                     Bucket=self.bucket_name,
#                     Key=self.s3_path,
#                     Body=file_data  # Передаем файловый поток напрямую
#                 )
#             print(f"✅ Файл успешно загружен в S3: {self.bucket_name}/{self.s3_path}")
#             print(f"ETag объекта: {response['ETag']}")

#     def __enter__(self) -> DB:
#         self.download_db()
#         logger.info("Подключение к SQLite...")
#         self.db = self.Table(self.local_path)
#         return self.db

#     def __exit__(self, exc_type, exc, tb):
#         self.db._conn.close()
#         self.upload_db()