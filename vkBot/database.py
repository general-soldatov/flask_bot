import os
import json
from typing import Any, ClassVar, Union, Optional
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
    def __init__(self):
        # На PythonAnywhere лучше подстраховаться дефолтными значениями, если .env не прочитался
        self.user = os.getenv('DB_USER', 'GeneralSoldatov')
        self.password = os.getenv('DB_PASSWORD', 'ваш_пароль')
        self.host = os.getenv('DB_HOST', '://pythonanywhere-services.com')
        self.name = os.getenv('DB_NAME', 'GeneralSoldatov\$flask_bot')

    def get_db_connection(self):
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.name,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor 
        )

    def create_tables(self, clses=BaseTable):
        connection = self.get_db_connection()
        try:
            for cls in clses.__subclasses__():
                try:
                    with connection.cursor() as cursor:
                        query = cls.create_table()
                        cursor.execute(query)
                except Exception as e:
                    logger.error(f"Ошибка создания таблицы {cls.__name__}: {e}")
            connection.commit()
        finally:
            connection.close()

    def drop_table(self, TableCls: type):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        connection = self.get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(TableCls.drop())
                connection.commit()
            logger.info(f"Таблица {TableCls.__name__.lower()} удалена.")
        finally:
            connection.close()

    def save(self, table: BaseTable):
        """Рекомендуемый метод вместо insert: Безопасно сохраняет состояние (создает или обновляет)."""
        query, params = table.replace()
        connection = self.get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                connection.commit()
        finally:
            connection.close()

    def insert(self, table: BaseTable):
        query, params = table.insert()
        connection = self.get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                connection.commit()
        finally:
            connection.close()

    def update(self, table: BaseTable):
        query, params = table.update()
        connection = self.get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                connection.commit()
        finally:
            connection.close()

    def select(self, TableCls: type):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        connection = self.get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(TableCls.select())
                return [TableCls.from_db(row) for row in cursor.fetchall()]
        finally:
            connection.close()

    def select_id(self, TableCls: type, key: Any):
        """Исправлено: Полная защита от NoneType ошибок."""
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        connection = self.get_db_connection()
        try:
            query, params = TableCls.select_id(key)
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                if row is None:
                    return None  # Возвращаем None, если записи нет (FSM поймет это)
                return TableCls.from_db(row)
        except Exception as e:
            logger.error(e)
            return None
        finally:
            connection.close()

    def delete_id(self, TableCls: type, key: Any):
        if not isinstance(TableCls, type):
            raise TypeError("Требуется передать класс, а не экземпляр")
        query, params = TableCls.delete_id(key)
        connection = self.get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                connection.commit()
        finally:
            connection.close()
