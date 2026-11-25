# coding: utf-8



from __future__ import annotations
import pprint
import re  # noqa: F401
import json

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator
from typing import Any, ClassVar, Dict, List, Optional, Union
from typing_extensions import Annotated
from openapi_client.models.color import Color
from openapi_client.models.team_member_vacations_inner import TeamMemberVacationsInner
from typing import Optional, Set
from typing_extensions import Self

class TeamMember(BaseModel):
    id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    team_id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    user_id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    alias: Optional[Annotated[str, Field(strict=True, max_length=255)]] = None
    description: Optional[StrictStr] = None
    role: StrictStr
    status: StrictStr
    is_favorite: Optional[StrictBool] = False
    sidebar_position: Optional[Union[StrictFloat, StrictInt]] = None
    color: Optional[Color] = None
    team_color: Optional[Color] = None
    vacations: Optional[List[TeamMemberVacationsInner]] = Field(default=None, description="List of vacation ranges for the team member.")
    contact_info: Optional[StrictStr] = None
    __properties: ClassVar[List[str]] = ["id", "team_id", "user_id", "alias", "description", "role", "status", "is_favorite", "sidebar_position", "color", "team_color", "vacations", "contact_info"]

    @field_validator('id')
    def id_validate_regular_expression(cls, value):
        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('team_id')
    def team_id_validate_regular_expression(cls, value):
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

    @field_validator('status')
    def status_validate_enum(cls, value):
        if value not in set(['active', 'pending', 'requesting_join', 'archived', 'expired']):
            raise ValueError("must be one of enum values ('active', 'pending', 'requesting_join', 'archived', 'expired')")
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
            "contact_info",
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
        # set to None if alias (nullable) is None
        # and model_fields_set contains the field
        if self.alias is None and "alias" in self.model_fields_set:
            _dict['alias'] = None

        # set to None if description (nullable) is None
        # and model_fields_set contains the field
        if self.description is None and "description" in self.model_fields_set:
            _dict['description'] = None

        # set to None if sidebar_position (nullable) is None
        # and model_fields_set contains the field
        if self.sidebar_position is None and "sidebar_position" in self.model_fields_set:
            _dict['sidebar_position'] = None

        # set to None if color (nullable) is None
        # and model_fields_set contains the field
        if self.color is None and "color" in self.model_fields_set:
            _dict['color'] = None

        # set to None if team_color (nullable) is None
        # and model_fields_set contains the field
        if self.team_color is None and "team_color" in self.model_fields_set:
            _dict['team_color'] = None

        # set to None if vacations (nullable) is None
        # and model_fields_set contains the field
        if self.vacations is None and "vacations" in self.model_fields_set:
            _dict['vacations'] = None

        # set to None if contact_info (nullable) is None
        # and model_fields_set contains the field
        if self.contact_info is None and "contact_info" in self.model_fields_set:
            _dict['contact_info'] = None

        return _dict

    @classmethod
    def from_dict(cls, obj: Optional[Dict[str, Any]]) -> Optional[Self]:
        if obj is None:
            return None

        if not isinstance(obj, dict):
            return cls.model_validate(obj)

        _obj = cls.model_validate({
            "id": obj.get("id"),
            "team_id": obj.get("team_id"),
            "user_id": obj.get("user_id"),
            "alias": obj.get("alias"),
            "description": obj.get("description"),
            "role": obj.get("role"),
            "status": obj.get("status"),
            "is_favorite": obj.get("is_favorite") if obj.get("is_favorite") is not None else False,
            "sidebar_position": obj.get("sidebar_position"),
            "color": obj.get("color"),
            "team_color": obj.get("team_color"),
            "vacations": [TeamMemberVacationsInner.from_dict(_item) for _item in obj["vacations"]] if obj.get("vacations") is not None else None,
            "contact_info": obj.get("contact_info")
        })
        return _obj


