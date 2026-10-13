from pydantic import BaseModel, Field
from typing import List, Union, Optional
from enum import Enum
from .action import *

class ButtonColor(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    NEGATIVE = "negative"
    POSITIVE = "positive"

class Button(BaseModel):
    action: Union[Callback, Location, OpenLink, Text, VKApps, VKPay]
    color: Optional[ButtonColor] = None

    def model_dump_json(self, *, indent = None, ensure_ascii = False, include = None, exclude = None, context = None, by_alias = None, exclude_unset = False, exclude_defaults = False, exclude_none = True, exclude_computed_fields = False, round_trip = False, warnings = True, fallback = None, serialize_as_any = False, polymorphic_serialization = None):
        return super().model_dump_json(indent=indent, ensure_ascii=ensure_ascii, include=include, exclude=exclude, context=context, by_alias=by_alias, exclude_unset=exclude_unset, exclude_defaults=exclude_defaults, exclude_none=exclude_none, exclude_computed_fields=exclude_computed_fields, round_trip=round_trip, warnings=warnings, fallback=fallback, serialize_as_any=serialize_as_any, polymorphic_serialization=polymorphic_serialization)

class InlineKeyboard(BaseModel):
    current_row_idx: int = Field(default=0, exclude=True)
    buttons: List[List[Button]] = Field(default_factory=lambda: [[]])
    inline: bool = True

    MAX_COLUMNS: int = Field(default=5, exclude=True)

    def as_markup(self) -> str:
        if len(self.buttons[-1]) < 1:
            self.buttons.pop()
        return self.model_dump_json(by_alias=True, exclude_none=True)

    def add(self, action, color: Optional[ButtonColor] = None):
        if len(self.buttons[self.current_row_idx]) >= self.MAX_COLUMNS:
            self.row()
            
        button = Button(action=action, color=color)
        self.buttons[self.current_row_idx].append(button)
        return self

    def row(self):
        if self.buttons[self.current_row_idx]:
            self.buttons.append([])
            self.current_row_idx += 1
        return self

class ReplyKeyboard(InlineKeyboard):
    one_time: bool = False
    inline: bool = False  
