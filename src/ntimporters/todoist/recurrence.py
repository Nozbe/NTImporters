"""Todoist recurring due string (en, pl) -> RRULE"""

import re

FREQS = {
    "DAILY": "day days daily dzień dzien dni dnia codziennie morning afternoon evening night rano wieczorem",
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
MONTHS = (
    "jan january styczeń stycznia",
    "feb february luty lutego",
    "mar march marzec marca",
    "apr april kwiecień kwietnia",
    "may maj maja",
    "jun june czerwiec czerwca",
    "jul july lipiec lipca",
    "aug august sierpień sierpnia",
    "sep sept september wrzesień września",
    "oct october październik października",
    "nov november listopad listopada",
    "dec december grudzień grudnia",
)
FREQ = {word: freq for freq, words in FREQS.items() for word in words.split()}
MONTH = {word: n for n, words in enumerate(MONTHS, 1) for word in words.split()}
DAY_OF_MONTH = {
    f"{n}{suffix}": n for n in range(1, 32) for suffix in ("", "st", "nd", "rd", "th", ".")
}
QUARTER = {"quarter", "quarterly", "kwartał", "kwartal", "kwartalnie"}
DAY = {word: day for day, words in DAYS.items() for word in words.split()}
INTERVAL = {"other": 2, "drugi": 2, "drugą": 2, "drugie": 2, "trzeci": 3, "trzecią": 3}
POS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}
POS |= {"last": -1, "ostatni": -1, "ostatnią": -1, "ostatnia": -1, "ostatniego": -1}
WORKDAYS = {"weekday", "weekdays", "workday", "workdays", "dzień roboczy", "dni robocze"}
FILLER = {"every", "each", "co", "każdy", "każdego", "każdą", "każda", "każde", "w", "we"}
FILLER |= {"and", "i", "oraz", "a", "on", "the"}

END = re.compile(r"\s(?:until|ending|for|do|przez)\s")
TAIL = re.compile(r"\s(?:at|@|o|starting|from|until|ending|for|od|do|przez)\s.*$")
UNTIL = re.compile(r"\s(?:until|ending|do)\s(\d{4})-(\d{2})-(\d{2})\b")
NOISE = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\b|\b\d{1,2}:\d{2}\b|\bof (?:the )?month\b|\bmiesiąca\b"
)


LANGS = {"en", "pl"}


def to_rrule(text: str | None, lang: str | None = "en") -> str | None:
    """Todoist due.string in due.lang -> RRULE without DTSTART; None if unrecognised"""
    if lang not in LANGS or not (rule := _rule(text)):
        return None
    text = f" {text.lower()} "
    if until := UNTIL.search(text):
        return f"{rule};UNTIL={''.join(until.groups())}"
    # end not given as ISO date ("until feb 28", "for 3 weeks"): unbounded rule would be wrong
    return None if END.search(text) else rule


def _rule(text: str | None) -> str | None:
    """RRULE FREQ/INTERVAL/BY* part of due.string"""
    text = TAIL.sub("", f" {(text or '').lower().replace('!', '')} ")
    tokens = [t for t in re.split(r"[\s,]+", NOISE.sub(" ", text)) if t and t not in FILLER]
    interval = 1
    # number is an interval only before a unit word: "27 jan", "1, 15" are dates
    if len(tokens) > 1 and (
        n := int(tokens[0])
        if tokens[0].isdigit() and (tokens[1] in FREQ or tokens[1] in QUARTER)
        else INTERVAL.get(tokens[0])
    ):
        interval, tokens = n, tokens[1:]
    every = f";INTERVAL={interval}" if interval > 1 else ""
    phrase = " ".join(tokens)

    if len(tokens) == 1 and (freq := FREQ.get(phrase)):
        return f"FREQ={freq}{every}"
    if phrase in QUARTER:
        return f"FREQ=MONTHLY;INTERVAL={3 * interval}"
    # "every 2 weeks on monday", "every month on the 5th": unit word before BY* part
    unit = FREQ.get(tokens[0]) if len(tokens) > 1 else None
    if unit in ("WEEKLY", "MONTHLY"):
        tokens = tokens[1:]
    if phrase in WORKDAYS:
        return f"FREQ=WEEKLY{every};BYDAY=MO,TU,WE,TH,FR"
    if phrase == "weekend":
        return f"FREQ=WEEKLY{every};BYDAY=SA,SU"
    if unit in (None, "WEEKLY") and tokens and all(t in DAY for t in tokens):
        return f"FREQ=WEEKLY{every};BYDAY={','.join(dict.fromkeys(DAY.get(t) for t in tokens))}"
    if unit in (None, "MONTHLY") and tokens and all(days := list(map(DAY_OF_MONTH.get, tokens))):
        return f"FREQ=MONTHLY{every};BYMONTHDAY={','.join(map(str, days))}"
    if interval > 1 or unit:
        return None
    match tokens:
        case [month, day] if month in MONTH and day in DAY_OF_MONTH:
            return f"FREQ=YEARLY;BYMONTH={MONTH.get(month)};BYMONTHDAY={DAY_OF_MONTH.get(day)}"
        case [day, month] if month in MONTH and day in DAY_OF_MONTH:
            return f"FREQ=YEARLY;BYMONTH={MONTH.get(month)};BYMONTHDAY={DAY_OF_MONTH.get(day)}"
        case [pos, "day" | "dzień" | "dnia"] if POS.get(pos) == -1:
            return "FREQ=MONTHLY;BYMONTHDAY=-1"
        case [pos, day] if pos in POS and day in DAY:
            return f"FREQ=MONTHLY;BYDAY={DAY.get(day)};BYSETPOS={POS.get(pos)}"
    return None
