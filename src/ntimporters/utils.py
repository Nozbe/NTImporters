""" Common helper functions """
import json
import random
from typing import Optional

from openapi_client import apis
from openapi_client.model.color import Color
from openapi_client.model.id16_read_only import Id16ReadOnly
from openapi_client.model.id16_read_only_nullable import Id16ReadOnlyNullable
from openapi_client.model.timestamp_read_only import TimestampReadOnly
from openapi_client.model_utils import ModelNormal


def id16():
    """Generate random string"""
    return 16 * "a"


class ImportException(Exception):
    """ Importer exception """


def check_limits(limits: dict, limit_name: str, current_len: int):
    """ Raise an exception if limits exceeded """
    if current_len > (limit := limits.get(limit_name, 0)) > -1:
        raise ImportException(f"LIMIT {limit_name} : {current_len} > {limit}")


def strip_readonly(model: ModelNormal):
    """Strip read only fields before sending to server"""
    for field in [
        elt
        for elt in model.attribute_map.values()
        if hasattr(model, elt)
        and isinstance(getattr(model, elt), (Id16ReadOnly, Id16ReadOnlyNullable, TimestampReadOnly))
    ]:
        del model.__dict__.get("_data_store")[field]
    return model


def nt_limits(nt_client, team_id: str):
    """Check Nozbe Teams limits"""
    if (team := apis.TeamsApi(nt_client).get_team_by_id(team_id)) and hasattr(team, "limits"):
        return json.loads(team.limits)
    return {}


def map_color(color: Optional[str]) -> Color:
    """Maps color onto Nozbe Teams color"""
    colors = list(list(Color.allowed_values.values())[0].values())
    colors.remove("null")
    return Color(color if color in colors else random.choice(colors))  # nosec
