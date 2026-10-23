import aiohttp
from app.config.config import PHYS, TERMEX
from pydantic import BaseModel

class Contingent(BaseModel):
    name: str
    profile: str
    group: str

    @classmethod
    async def get(cls, name: str, subject: str):
        url = await cls.subject(subject)
        if url:
            data: dict = await cls.get_query(url)
            search_name = name.title()
            info = data.get(search_name, False)
            if info:
                return cls(name=search_name, **info)

    @staticmethod
    async def subject(key: str):
        data = {
            'code': TERMEX,
            'termex': TERMEX,
            'phys': PHYS
        }
        return data.get(key, TERMEX)

    @staticmethod
    async def get_query(url: str):
        async with aiohttp.ClientSession() as session:
        # 2. Выполняем GET-запрос
            async with session.get(url) as response:
                return await response.json(content_type=None)
