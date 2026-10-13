from datetime import datetime, timedelta
import requests

from app.config.dictionary import reference

class Schedule:
    def __init__(self) -> None:
        self.weekdays = reference.schedule.weekday

    def get_call(self, day: str) -> str:
        date_to = reference.schedule.selector.index(day)
        calendar = self.go_day(date_to)
        shedule: dict = self.get_schedule(week=((calendar.week+1) % 2),
                              day=self.weekdays[calendar.weekday])
        return self.weekdays[calendar.weekday], shedule

    @staticmethod
    def go_day(day: int):
        need_day = datetime.now() + timedelta(days=day)
        return need_day.isocalendar()
    
    @staticmethod
    def get_schedule(week: int, day: str):
        response = requests.get(reference.schedule.source)
        data: dict = response.json()
        return data[str(week)][day.upper()]