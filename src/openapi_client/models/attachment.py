# coding: utf-8



from __future__ import annotations
import pprint
import re  # noqa: F401
import json

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator
from typing import Any, ClassVar, Dict, List, Optional
from typing_extensions import Annotated
from typing import Optional, Set
from typing_extensions import Self

class Attachment(BaseModel):
    id: Optional[Annotated[str, Field(min_length=16, strict=True, max_length=16)]] = None
    author_id: Optional[Annotated[str, Field(min_length=16, strict=True, max_length=16)]] = None
    status: Optional[StrictStr] = None
    name: StrictStr
    mime_type: Optional[StrictStr] = None
    created_at: Optional[Annotated[int, Field(strict=True, ge=0)]] = None
    size: Optional[StrictInt] = None
    __properties: ClassVar[List[str]] = ["id", "author_id", "status", "name", "mime_type", "created_at", "size"]

    @field_validator('id')
    def id_validate_regular_expression(cls, value):
        if value is None:
            return value

        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('author_id')
    def author_id_validate_regular_expression(cls, value):
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
            "created_at",
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
            "author_id": obj.get("author_id"),
            "status": obj.get("status"),
            "name": obj.get("name"),
            "mime_type": obj.get("mime_type"),
            "created_at": obj.get("created_at"),
            "size": obj.get("size")
        })
        return _obj


