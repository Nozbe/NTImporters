"""Todoist recurring due string (en, pl) -> RRULE"""

import re

FREQS = {
    "DAILY": "day days daily dzień dzien dni dnia codziennie",
    "WEEKLY": "week weeks weekly tydzień tydzien tygodnie tygodni tygodnia tygodniowo",
    "MONTHLY": "month months monthly miesiąc miesiac miesiące miesiace miesięcy miesiecy miesięcznie",
    "YEARLY": "year years yearly annually rok roku lata lat rocznie corocznie",
}
DAYS = {
    "MO": "monday mon poniedziałek poniedzialek poniedziałki pon pn",
    "TU": "tuesday tue tues wtorek wtorki wt",
    "WE": "wednesday wed środa środę sroda srode środy śr sr",
    "TH": "thursday thu thur thurs czwartek czwartki czw",
    "FR": "friday fri piątek piatek piątki pt",
    "SA": "saturday sat sobota sobotę sobote soboty sob",
    "SU": "sunday sun niedziela niedzielę niedziele niedziel niedz nd",
}
FREQ = {word: freq for freq, words in FREQS.items() for word in words.split()}
DAY = {word: day for day, words in DAYS.items() for word in words.split()}
INTERVAL = {"other": 2, "drugi": 2, "drugą": 2, "drugie": 2, "trzeci": 3, "trzecią": 3}
POS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}
POS |= {"last": -1, "ostatni": -1, "ostatnią": -1, "ostatnia": -1, "ostatniego": -1}
WORKDAYS = {"weekday", "weekdays", "workday", "workdays", "dzień roboczy", "dni robocze"}
FILLER = {"every", "each", "co", "każdy", "każdego", "każdą", "każda", "każde", "w", "we"}
FILLER |= {"and", "i", "oraz", "a", "on", "the"}

TAIL = re.compile(r"\s(?:at|@|o|starting|from|until|ending|for|od|do|przez)\s.*$")
NOISE = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\b|\b\d{1,2}:\d{2}\b|\bof (?:the )?month\b|\bmiesiąca\b"
)


def to_rrule(text: str | None) -> str | None:
    """Todoist due.string -> RRULE without DTSTART; None if unrecognised"""
    text = TAIL.sub("", f" {(text or '').lower().replace('!', '')} ")
    tokens = [t for t in re.split(r"[\s,]+", NOISE.sub(" ", text)) if t and t not in FILLER]
    interval = 1
    if len(tokens) > 1 and (
        n := int(tokens[0]) if tokens[0].isdigit() else INTERVAL.get(tokens[0])
    ):
        interval, tokens = n, tokens[1:]
    every = f";INTERVAL={interval}" if interval > 1 else ""
    phrase = " ".join(tokens)

    if len(tokens) == 1 and (freq := FREQ.get(phrase)):
        return f"FREQ={freq}{every}"
    if phrase in WORKDAYS:
        return f"FREQ=WEEKLY{every};BYDAY=MO,TU,WE,TH,FR"
    if phrase == "weekend":
        return f"FREQ=WEEKLY{every};BYDAY=SA,SU"
    if tokens and all(t in DAY for t in tokens):
        return f"FREQ=WEEKLY{every};BYDAY={','.join(dict.fromkeys(DAY.get(t) for t in tokens))}"
    if interval > 1:
        return None
    match tokens:
        case [pos, "day" | "dzień" | "dnia"] if POS.get(pos) == -1:
            return "FREQ=MONTHLY;BYMONTHDAY=-1"
        case [pos, day] if pos in POS and day in DAY:
            return f"FREQ=MONTHLY;BYDAY={DAY.get(day)};BYSETPOS={POS.get(pos)}"
    days = [int(m[1]) for t in tokens if (m := re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th|\.)?", t))]
    if tokens and len(days) == len(tokens) and all(1 <= d <= 31 for d in days):
        return f"FREQ=MONTHLY;BYMONTHDAY={','.join(map(str, days))}"
    return None
