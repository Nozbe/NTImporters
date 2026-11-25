# coding: utf-8



from __future__ import annotations
import json
from enum import Enum
from typing_extensions import Self


class Color(str, Enum):

    NULL = 'null'
    ELWIS = 'elwis'
    FELUS = 'felus'
    FLUFFY = 'fluffy'
    LUNA = 'luna'
    MAJA = 'maja'
    PEDRO = 'pedro'
    RUFUS = 'rufus'
    TOTO = 'toto'
    AQUAMARINE = 'aquamarine'
    AUBERGINE = 'aubergine'
    BLUE = 'blue'
    BROWN = 'brown'
    BURNTSIENNA = 'burntsienna'
    DARKGREEN = 'darkgreen'
    DEEPPURPLE = 'deeppurple'
    DUSTPINK = 'dustpink'
    GREEN = 'green'
    HEATHER = 'heather'
    INDIGO = 'indigo'
    KARMIN = 'karmin'
    LIGHTBLUE = 'lightblue'
    LIGHTPINK = 'lightpink'
    MAUVE = 'mauve'
    MIDNIGHT = 'midnight'
    NAVY = 'navy'
    OCEAN = 'ocean'
    OCHER = 'ocher'
    OLIVE = 'olive'
    ORANGE = 'orange'
    PINK = 'pink'
    PURPLE = 'purple'
    RED = 'red'
    SAND = 'sand'
    STONE = 'stone'
    TAUPE = 'taupe'
    TEAL = 'teal'
    ULTRAMARINE = 'ultramarine'
    YELLOW = 'yellow'
    AMBER = 'amber'
    CORAL = 'coral'
    PLUM = 'plum'
    ROSEWOOD = 'rosewood'
    SAGE = 'sage'
    STEEL = 'steel'

    @classmethod
    def from_json(cls, json_str: str) -> Self:
        return cls(json.loads(json_str))


