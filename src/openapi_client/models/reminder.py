# coding: utf-8



from __future__ import annotations
import pprint
import re  # noqa: F401
import json

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator
from typing import Any, ClassVar, Dict, List, Optional
from typing_extensions import Annotated
from typing import Optional, Set
from typing_extensions import Self

class Reminder(BaseModel):
    id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    task_id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    remind_at: StrictInt
    is_relative: StrictBool
    is_all_day: StrictBool
    is_urgent: Optional[StrictBool] = False
    __properties: ClassVar[List[str]] = ["id", "task_id", "remind_at", "is_relative", "is_all_day", "is_urgent"]

    @field_validator('id')
    def id_validate_regular_expression(cls, value):
        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('task_id')
    def task_id_validate_regular_expression(cls, value):
        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
        protected_namespaces=(),
    )


    def to_str(self) -> str:
        return pprint.pformat(self.model_dump(by_alias=True))

    def to_json(self) -> str:
        # TODO: pydantic v2: use .model_dump_json(by_alias=True, exclude_unset=True) instead
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> Optional[Self]:
        return cls.from_dict(json.loads(json_str))

    def to_dict(self) -> Dict[str, Any]:
        excluded_fields: Set[str] = set([
            "id",
        ])

        _dict = self.model_dump(
            by_alias=True,
            exclude=excluded_fields,
            exclude_none=True,
        )
        return _dict

    @classmethod
    def from_dict(cls, obj: Optional[Dict[str, Any]]) -> Optional[Self]:
        if obj is None:
            return None

        if not isinstance(obj, dict):
            return cls.model_validate(obj)

        _obj = cls.model_validate({
            "id": obj.get("id"),
            "task_id": obj.get("task_id"),
            "remind_at": obj.get("remind_at"),
            "is_relative": obj.get("is_relative") if obj.get("is_relative") is not None else False,
            "is_all_day": obj.get("is_all_day") if obj.get("is_all_day") is not None else False,
            "is_urgent": obj.get("is_urgent") if obj.get("is_urgent") is not None else False
        })
        return _obj


