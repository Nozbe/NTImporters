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

class BusinessMember(BaseModel):
    id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    business_id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    user_id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    role: StrictStr
    vacations: Optional[List[Items]] = Field(default=None, description="List of vacation ranges for the business member.")
    __properties: ClassVar[List[str]] = ["id", "business_id", "user_id", "role", "vacations"]

    @field_validator('id')
    def id_validate_regular_expression(cls, value):
        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('business_id')
    def business_id_validate_regular_expression(cls, value):
        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('user_id')
    def user_id_validate_regular_expression(cls, value):
        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('role')
    def role_validate_enum(cls, value):
        if value not in set(['owner', 'admin', 'member']):
            raise ValueError("must be one of enum values ('owner', 'admin', 'member')")
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
        # override the default output from pydantic by calling `to_dict()` of each item in vacations (list)
        _items = []
        if self.vacations:
            for _item in self.vacations:
                if _item:
                    _items.append(_item.to_dict())
            _dict['vacations'] = _items
        # set to None if vacations (nullable) is None
        # and model_fields_set contains the field
        if self.vacations is None and "vacations" in self.model_fields_set:
            _dict['vacations'] = None

        return _dict

    @classmethod
    def from_dict(cls, obj: Optional[Dict[str, Any]]) -> Optional[Self]:
        if obj is None:
            return None

        if not isinstance(obj, dict):
            return cls.model_validate(obj)

        _obj = cls.model_validate({
            "id": obj.get("id"),
            "business_id": obj.get("business_id"),
            "user_id": obj.get("user_id"),
            "role": obj.get("role"),
            "vacations": [Items.from_dict(_item) for _item in obj["vacations"]] if obj.get("vacations") is not None else None
        })
        return _obj


