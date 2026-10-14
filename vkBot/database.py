import os
import json
from typing import Any, ClassVar, Union
from pydantic import BaseModel
import logging
import pymysql

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

class INT(TypeSQL):
    def __init__(self, value: int):
        super().__init__(value)

    def __str__(self):
        return str(self.value)

class FLOAT(TypeSQL):
    def __init__(self, value: float):
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

class BOOL(TypeSQL):
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
    int: INT,
    float: FLOAT,
    bool: BOOL,
    str: TEXT,
    dict: JSON
}     


class BaseTable(BaseModel):
    primary_key: ClassVar[str] = set_key(lambda cls: "id") 

    @classmethod
    def create_table(cls):
        fields = [f'{field_name} {DATA.get(field_info.annotation, JSON).__name__}{" PRIMARY KEY" if field_name == cls.primary_key else ""}' 
                  for field_name, field_info in cls.model_fields.items()]
        field = ',\n'.join(fields)
        return f"CREATE TABLE IF NOT EXISTS {cls.__name__.lower()} ({field}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"

    def insert(self):
        table_name = self.__class__.__name__.lower()
            
        # 2. Получаем все поля и конвертируем словари/списки в JSON-строки
        raw_data = self.model_dump()
        clean_params = []
        for val in raw_data.values():
            if isinstance(val, (dict, list)):
                # Превращаем словари Python в строки JSON, чтобы MySQL их принял
                clean_params.append(json.dumps(val, ensure_ascii=False))
            else:
                clean_params.append(val)
                
        fields = list(raw_data.keys())
        set_clause = ", ".join([f"{field} = %s" for field in fields])
        
        query = f"INSERT INTO {table_name} SET {set_clause} WHERE id = %s"
        params = tuple(clean_params) + (raw_data.get('id'),)
        
        return query, params
        # placeholders = ", ".join(["%s"] * len(self.__class__.model_fields))
        # params = tuple(self.model_dump().values())
        # return f"INSERT INTO {self.__class__.__name__.lower()} VALUES ({placeholders})", params

    def update(self):
        table_name = self.__class__.__name__.lower()
    
        # 2. Получаем все поля и конвертируем словари/списки в JSON-строки
        raw_data = self.model_dump()
        clean_params = []
        for val in raw_data.values():
            if isinstance(val, (dict, list)):
                # Превращаем словари Python в строки JSON, чтобы MySQL их принял
                clean_params.append(json.dumps(val, ensure_ascii=False))
            else:
                clean_params.append(val)
                
        fields = list(raw_data.keys())
        set_clause = ", ".join([f"{field} = %s" for field in fields])
        
        query = f"UPDATE {table_name} SET {set_clause} WHERE id = %s"
        params = tuple(clean_params) + (raw_data.get('id'),)
        
        return query, params

    @classmethod
    def select(cls):
        return f"SELECT * FROM {cls.__name__.lower()};"

    @classmethod
    def drop(cls):
        return f"DROP TABLE IF EXISTS {cls.__name__.lower()};"

    @classmethod
    def select_id(cls, key):
        return f"SELECT * FROM `{cls.__name__.lower()}` WHERE {cls.primary_key} = %s;", (key, )

    @classmethod
    def delete_id(cls, key):
        return f"DELETE FROM `{cls.__name__.lower()}` WHERE {cls.primary_key} = %s;", (key, )


    @classmethod
    def model_construct(cls, obj: dict):
        return cls(**{
            field: json.loads(value) if cls.model_fields[field].annotation == dict else value 
                for field, value in obj.items()
        })

class DB:
    def __init__(self):
        self.user = os.getenv('DB_USER')
        self.password = os.getenv('DB_PASSWORD')
        self.host = os.getenv('DB_HOST')
        self.name = os.getenv('DB_NAME')

    def get_db_connection(self):
        """Функция создает и возвращает чистое подключение к MySQL"""
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.name,
            charset='utf8mb4',
            # Возвращает строки в виде удобных словарей {'id': 1, 'name': 'test'} вместо кортежей
            cursorclass=pymysql.cursors.DictCursor 
        )

    def create_tables(self, clses=BaseTable):
        connection = self.get_db_connection()
        for cls in clses.__subclasses__():
            try:
                with connection.cursor() as cursor:
                    # Тестовый запрос проверки связи
                    query = cls.create_table()
                    cursor.execute(query)
                
            except Exception as e:
                logger.error(e)
                continue        
        connection.commit()
        connection.close()

    def drop_table(self, TableCls: type):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        connection = self.get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(TableCls.drop())
            connection.commit()
        logger.info(f"Таблица {TableCls.__name__.lower()} удалена.")

    def insert(self, table: BaseTable):
        query, params = table.insert()
        connection = self.get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            connection.commit()

    def update(self, table: BaseTable):
        query, params = table.update()
        connection = self.get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            connection.commit()

    def select(self, TableCls: type):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        connection = self.get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(TableCls.select())
            return [TableCls.model_construct(row) for row in cursor.fetchall()]

    def select_id(self, TableCls: type, key: Any):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        try:
            query, params = TableCls.select_id(key)
            connection = self.get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return TableCls.model_validate(cursor.fetchone())
        except Exception as e:
            logger.error(e)

    def delete_id(self, TableCls: type, key: Any):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        query, params = TableCls.delete_id(key)
        connection = self.get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            connection.commit()

    def drop_table(self, TableCls: type):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        connection = self.get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(TableCls.drop())
            connection.commit()
        logger.info(f"Таблица {TableCls.__name__.lower()} удалена.")

    def query(self, text_query: str, data_query: tuple):
        try:
            connection = self.get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute(text_query, data_query)
                return cursor.fetchall()
        except Exception as e:
            logger.error(e)

  