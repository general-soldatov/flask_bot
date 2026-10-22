from datetime import datetime, timedelta
import requests
import aiohttp

from app.config.dictionary import reference

class Schedule:
    def __init__(self) -> None:
        self.weekdays = reference.schedule.weekday

    async def get_call(self, day: str) -> str:
        date_to = reference.schedule.selector.index(day)
        calendar = self.go_day(date_to)
        shedule: dict = await self.get_schedule(week=((calendar.week+1) % 2),
                              day=self.weekdays[calendar.weekday])
        return self.weekdays[calendar.weekday], shedule

    @staticmethod
    def go_day(day: int):
        need_day = datetime.now() + timedelta(days=day)
        return need_day.isocalendar()
    
    @staticmethod
    async def get_schedule(week: int, day: str):
        async with aiohttp.ClientSession() as session:
        # 2. Выполняем GET-запрос
            async with session.get(reference.schedule.source) as response:
                data = await response.json(content_type=None)
                return data[str(week)][day.upper()]
        # response = requests.get(reference.schedule.source)
        # data: dict = response.json()
