# coding: utf-8



from __future__ import annotations
import pprint
import re  # noqa: F401
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Any, ClassVar, Dict, List, Optional
from typing_extensions import Annotated
from typing import Optional, Set
from typing_extensions import Self

class TaskRecurrence(BaseModel):
    id: Optional[Annotated[str, Field(min_length=16, strict=True, max_length=16)]] = None
    project_id: Optional[Annotated[str, Field(min_length=0, strict=True, max_length=16)]] = None
    current_task_id: Optional[Annotated[str, Field(min_length=16, strict=True, max_length=16)]] = None
    pattern: Optional[Annotated[str, Field(min_length=1, strict=True)]] = None
    __properties: ClassVar[List[str]] = ["id", "project_id", "current_task_id", "pattern"]

    @field_validator('id')
    def id_validate_regular_expression(cls, value):
        if value is None:
            return value

        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('project_id')
    def project_id_validate_regular_expression(cls, value):
        if value is None:
            return value

        if not re.match(r"^([a-zA-Z0-9]{16}|task_me)?$", value):
            raise ValueError(r"must validate the regular expression /^([a-zA-Z0-9]{16}|task_me)?$/")
        return value

    @field_validator('current_task_id')
    def current_task_id_validate_regular_expression(cls, value):
        if value is None:
            return value

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
            "project_id": obj.get("project_id"),
            "current_task_id": obj.get("current_task_id"),
            "pattern": obj.get("pattern")
        })
        return _obj


