# coding: utf-8

"""
    Nozbe API

    Nozbe API specification

    The version of the OpenAPI document: 0.0.1
    Contact: support@nozbe.com
    Generated by OpenAPI Generator (https://openapi-generator.tech)

    Do not edit the class manually.
"""  # noqa: E501


from __future__ import annotations
import pprint
import re  # noqa: F401
import json

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator
from typing import Any, ClassVar, Dict, List, Optional, Union
from typing_extensions import Annotated
from typing import Optional, Set
from typing_extensions import Self

class TeamMember(BaseModel):
    """
    TeamMember
    """ # noqa: E501
    id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    team_id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    user_id: Annotated[str, Field(min_length=16, strict=True, max_length=16)]
    alias: Optional[Annotated[str, Field(strict=True, max_length=255)]] = None
    description: Optional[StrictStr] = None
    role: StrictStr
    status: StrictStr
    is_favorite: Optional[StrictBool] = False
    sidebar_position: Optional[Union[StrictFloat, StrictInt]] = None
    __properties: ClassVar[List[str]] = ["id", "team_id", "user_id", "alias", "description", "role", "status", "is_favorite", "sidebar_position"]

    @field_validator('id')
    def id_validate_regular_expression(cls, value):
        """Validates the regular expression"""
        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('team_id')
    def team_id_validate_regular_expression(cls, value):
        """Validates the regular expression"""
        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('user_id')
    def user_id_validate_regular_expression(cls, value):
        """Validates the regular expression"""
        if not re.match(r"^[a-zA-Z0-9]{16}$", value):
            raise ValueError(r"must validate the regular expression /^[a-zA-Z0-9]{16}$/")
        return value

    @field_validator('role')
    def role_validate_enum(cls, value):
        """Validates the enum"""
        if value not in set(['owner', 'admin', 'member']):
            raise ValueError("must be one of enum values ('owner', 'admin', 'member')")
        return value

    @field_validator('status')
    def status_validate_enum(cls, value):
        """Validates the enum"""
        if value not in set(['active', 'pending', 'requesting_join', 'archived', 'expired']):
            raise ValueError("must be one of enum values ('active', 'pending', 'requesting_join', 'archived', 'expired')")
        return value

    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
        protected_namespaces=(),
    )


    def to_str(self) -> str:
        """Returns the string representation of the model using alias"""
        return pprint.pformat(self.model_dump(by_alias=True))

    def to_json(self) -> str:
        """Returns the JSON representation of the model using alias"""
        # TODO: pydantic v2: use .model_dump_json(by_alias=True, exclude_unset=True) instead
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> Optional[Self]:
        """Create an instance of TeamMember from a JSON string"""
        return cls.from_dict(json.loads(json_str))

    def to_dict(self) -> Dict[str, Any]:
        """Return the dictionary representation of the model using alias.

        This has the following differences from calling pydantic's
        `self.model_dump(by_alias=True)`:

        * `None` is only added to the output dict for nullable fields that
          were set at model initialization. Other fields with value `None`
          are ignored.
        * OpenAPI `readOnly` fields are excluded.
        """
        excluded_fields: Set[str] = set([
            "id",
        ])

        _dict = self.model_dump(
            by_alias=True,
            exclude=excluded_fields,
            exclude_none=True,
        )
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

        return _dict

    @classmethod
    def from_dict(cls, obj: Optional[Dict[str, Any]]) -> Optional[Self]:
        """Create an instance of TeamMember from a dict"""
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
            "sidebar_position": obj.get("sidebar_position")
        })
        return _obj

