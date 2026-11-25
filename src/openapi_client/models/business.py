# coding: utf-8



from __future__ import annotations
import pprint
import re  # noqa: F401
import json

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, field_validator
from typing import Any, ClassVar, Dict, List, Optional, Union
from typing_extensions import Annotated
from typing import Optional, Set
from typing_extensions import Self

class Business(BaseModel):
    id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    name: Annotated[str, Field(min_length=1, strict=True, max_length=255)]
    color: Optional[StrictStr] = None
    avatar_url: Optional[StrictStr] = None
    plan_info: Optional[StrictStr] = None
    ai_credits_used: Optional[Union[StrictFloat, StrictInt]] = None
    __properties: ClassVar[List[str]] = ["id", "name", "color", "avatar_url", "plan_info", "ai_credits_used"]

    @field_validator('id')
    def id_validate_regular_expression(cls, value):
        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('color')
    def color_validate_enum(cls, value):
        if value is None:
            return value

        if value not in set(['', 'avatarColor1', 'avatarColor2', 'avatarColor3', 'avatarColor4', 'avatarColor5', 'avatarColor6', 'avatarColor7', 'avatarColor8', 'avatarColor9', 'avatarColor10', 'avatarColor11', 'avatarColor12', 'purple', 'dodgerblue', 'red', 'yellow', 'pink']):
            raise ValueError("must be one of enum values ('', 'avatarColor1', 'avatarColor2', 'avatarColor3', 'avatarColor4', 'avatarColor5', 'avatarColor6', 'avatarColor7', 'avatarColor8', 'avatarColor9', 'avatarColor10', 'avatarColor11', 'avatarColor12', 'purple', 'dodgerblue', 'red', 'yellow', 'pink')")
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
            "plan_info",
            "ai_credits_used",
        ])

        _dict = self.model_dump(
            by_alias=True,
            exclude=excluded_fields,
            exclude_none=True,
        )
        # set to None if avatar_url (nullable) is None
        # and model_fields_set contains the field
        if self.avatar_url is None and "avatar_url" in self.model_fields_set:
            _dict['avatar_url'] = None

        # set to None if plan_info (nullable) is None
        # and model_fields_set contains the field
        if self.plan_info is None and "plan_info" in self.model_fields_set:
            _dict['plan_info'] = None

        return _dict

    @classmethod
    def from_dict(cls, obj: Optional[Dict[str, Any]]) -> Optional[Self]:
        if obj is None:
            return None

        if not isinstance(obj, dict):
            return cls.model_validate(obj)

        _obj = cls.model_validate({
            "id": obj.get("id"),
            "name": obj.get("name"),
            "color": obj.get("color"),
            "avatar_url": obj.get("avatar_url"),
            "plan_info": obj.get("plan_info"),
            "ai_credits_used": obj.get("ai_credits_used")
        })
        return _obj


