# coding: utf-8



from __future__ import annotations
import pprint
import re  # noqa: F401
import json

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator
from typing import Any, ClassVar, Dict, List, Optional
from typing_extensions import Annotated
from typing import Optional, Set
from typing_extensions import Self

class User(BaseModel):
    id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    name: Annotated[str, Field(min_length=1, strict=True, max_length=255)]
    color: StrictStr
    is_placeholder: StrictBool
    invitation_email: Optional[StrictStr] = None
    avatar_url: Optional[StrictStr] = None
    time_zone: Optional[StrictStr] = None
    __properties: ClassVar[List[str]] = ["id", "name", "color", "is_placeholder", "invitation_email", "avatar_url", "time_zone"]

    @field_validator('id')
    def id_validate_regular_expression(cls, value):
        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('color')
    def color_validate_enum(cls, value):
        if value not in set(['avatarColor1', 'avatarColor2', 'avatarColor3', 'avatarColor4', 'avatarColor5', 'avatarColor6', 'avatarColor7', 'avatarColor8', 'avatarColor9', 'avatarColor10', 'avatarColor11', 'avatarColor12']):
            raise ValueError("must be one of enum values ('avatarColor1', 'avatarColor2', 'avatarColor3', 'avatarColor4', 'avatarColor5', 'avatarColor6', 'avatarColor7', 'avatarColor8', 'avatarColor9', 'avatarColor10', 'avatarColor11', 'avatarColor12')")
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
        # set to None if invitation_email (nullable) is None
        # and model_fields_set contains the field
        if self.invitation_email is None and "invitation_email" in self.model_fields_set:
            _dict['invitation_email'] = None

        # set to None if avatar_url (nullable) is None
        # and model_fields_set contains the field
        if self.avatar_url is None and "avatar_url" in self.model_fields_set:
            _dict['avatar_url'] = None

        # set to None if time_zone (nullable) is None
        # and model_fields_set contains the field
        if self.time_zone is None and "time_zone" in self.model_fields_set:
            _dict['time_zone'] = None

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
            "is_placeholder": obj.get("is_placeholder") if obj.get("is_placeholder") is not None else False,
            "invitation_email": obj.get("invitation_email"),
            "avatar_url": obj.get("avatar_url"),
            "time_zone": obj.get("time_zone")
        })
        return _obj


