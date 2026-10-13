import httpx
from app.config.config import PHYS, TERMEX
from pydantic import BaseModel

class Contingent(BaseModel):
    name: str
    # google_id: int
    profile: str
    group: str

    @classmethod
    def get(cls, name: str, subject: str):
        url = cls.subject(subject)
        if url:
            response = httpx.get(url)
            data: dict = response.json()
            search_name = name.title()
            info = data.get(search_name, False)
            if info:
                return cls(name=search_name, **info)

    @staticmethod
    def subject(key: str):
        data = {
            'code': TERMEX,
            'termex': TERMEX,
            'phys': PHYS
        }
        return data.get(key, TERMEX)
