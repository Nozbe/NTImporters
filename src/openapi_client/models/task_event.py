# coding: utf-8



from __future__ import annotations
import pprint
import re  # noqa: F401
import json

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from typing import Any, ClassVar, Dict, List, Optional
from typing_extensions import Annotated
from typing import Optional, Set
from typing_extensions import Self

class TaskEvent(BaseModel):
    id: Optional[Annotated[str, Field(min_length=16, strict=True, max_length=16)]] = None
    integration: Optional[StrictStr] = None
    task_id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    author_id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    created_at: Annotated[int, Field(strict=True, ge=0)]
    last_modified: Optional[Annotated[int, Field(strict=True, ge=0)]] = None
    change: Annotated[str, Field(min_length=1, strict=True)]
    __properties: ClassVar[List[str]] = ["id", "integration", "task_id", "author_id", "created_at", "last_modified", "change"]

    @field_validator('id')
    def id_validate_regular_expression(cls, value):
        if value is None:
            return value

        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('integration')
    def integration_validate_enum(cls, value):
        if value is None:
            return value

        if value not in set(['null', 'api', 'email', 'evernote', 'gcal', 'mcal', 'zapier', 'make', 'slack', 'msteams']):
            raise ValueError("must be one of enum values ('null', 'api', 'email', 'evernote', 'gcal', 'mcal', 'zapier', 'make', 'slack', 'msteams')")
        return value

    @field_validator('task_id')
    def task_id_validate_regular_expression(cls, value):
        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('author_id')
    def author_id_validate_regular_expression(cls, value):
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
            "integration",
            "author_id",
            "created_at",
            "last_modified",
        ])

        _dict = self.model_dump(
            by_alias=True,
            exclude=excluded_fields,
            exclude_none=True,
        )
        # set to None if integration (nullable) is None
        # and model_fields_set contains the field
        if self.integration is None and "integration" in self.model_fields_set:
            _dict['integration'] = None

        return _dict

    @classmethod
    def from_dict(cls, obj: Optional[Dict[str, Any]]) -> Optional[Self]:
        if obj is None:
            return None

        if not isinstance(obj, dict):
            return cls.model_validate(obj)

        _obj = cls.model_validate({
            "id": obj.get("id"),
            "integration": obj.get("integration"),
            "task_id": obj.get("task_id"),
            "author_id": obj.get("author_id"),
            "created_at": obj.get("created_at"),
            "last_modified": obj.get("last_modified"),
            "change": obj.get("change")
        })
        return _obj


