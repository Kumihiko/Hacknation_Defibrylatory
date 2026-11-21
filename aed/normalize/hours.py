"""Parsowanie godzin dostępności AED.

Obsługiwane wejścia:
* składnia OpenStreetMap opening_hours (podzbiór: dni, przedziały godzin, "off", "24/7"),
* polskie opisy tekstowe: "24 h", "całodobowo", "pn.-pt. 7.00-15.30", "Wtorek-Piątek: godz. 8:00-16:00".

Wynik to `Hours(is_24_7, week)`, gdzie `week` to lista przedziałów (dzień 0=pon..6=nd, od_min, do_min).
Zasada bezpieczeństwa: jeśli opisu nie da się jednoznacznie zinterpretować, zwracamy brak informacji
(None), zamiast zgadywać – aplikacja nie może wysłać ratownika do zamkniętego AED.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

DAY_CODES = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
FULL_DAY = 24 * 60

Interval = tuple[int, int, int]  # (dzień, od_min, do_min)


@dataclass(frozen=True)
class Hours:
    is_24_7: bool | None
    week: tuple[Interval, ...] | None = None

    @property
    def known(self) -> bool:
        return self.is_24_7 is True or bool(self.week)

    def to_osm(self) -> str | None:
        if self.is_24_7:
            return "24/7"
        if not self.week:
            return None
        return week_to_osm(self.week)


UNKNOWN = Hours(None, None)
ALWAYS = Hours(True, None)

# ---------------------------------------------------------------- wspólne

_TIME_RANGE = re.compile(
    r"(?<![\d.])(\d{1,2})(?:[:.](\d{2}))?\s*(?:-|–|—|do)\s*(\d{1,2})(?:[:.](\d{2}))?(?![\d])"
)


def _minutes(h: str, m: str | None) -> int | None:
    hh, mm = int(h), int(m or 0)
    if hh > 24 or mm > 59 or (hh == 24 and mm):
        return None
    return hh * 60 + mm


def _add_interval(week: dict[int, list[tuple[int, int]]], day: int, start: int, end: int) -> None:
    if end <= start:  # przez północ, np. 22:00-06:00
        week.setdefault(day, []).append((start, FULL_DAY))
        week.setdefault((day + 1) % 7, []).append((0, end))
    else:
        week.setdefault(day, []).append((start, end))


def _finalize(week: dict[int, list[tuple[int, int]]]) -> Hours:
    intervals: list[Interval] = []
    for day in range(7):
        spans = sorted(week.get(day, []))
        merged: list[list[int]] = []
        for s, e in spans:
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        intervals.extend((day, s, e) for s, e in merged)
    if not intervals:
        return UNKNOWN
    if all(any(d == day and s == 0 and e == FULL_DAY for d, s, e in intervals) for day in range(7)):
        return ALWAYS
    return Hours(False, tuple(intervals))


def week_to_osm(week: tuple[Interval, ...]) -> str:
    per_day: dict[int, str] = {}
    for day in range(7):
        spans = [f"{s // 60:02d}:{s % 60:02d}-{e // 60:02d}:{e % 60:02d}" for d, s, e in week if d == day]
        if spans:
            per_day[day] = ",".join(spans)
    rules, day = [], 0
    while day < 7:
        if day not in per_day:
            day += 1
            continue
        start = day
        while day + 1 < 7 and per_day.get(day + 1) == per_day[start]:
            day += 1
        span = DAY_CODES[start] if start == day else f"{DAY_CODES[start]}-{DAY_CODES[day]}"
        rules.append(f"{span} {per_day[start]}")
        day += 1
    return "; ".join(rules)


def is_open(hours: Hours, when: datetime) -> bool | None:
    """Czy AED jest dostępny w chwili `when` (czas lokalny Europe/Warsaw)? None = brak informacji."""
    if hours.is_24_7:
        return True
    if not hours.week:
        return None
    minute = when.hour * 60 + when.minute
    day = when.weekday()
    return any(d == day and s <= minute < e for d, s, e in hours.week)


# ---------------------------------------------------------------- składnia OSM

_OSM_DAY = {c: i for i, c in enumerate(DAY_CODES)}
_OSM_RULE = re.compile(
    r"^(?:(?P<days>(?:Mo|Tu|We|Th|Fr|Sa|Su|PH)(?:\s*[-,]\s*(?:Mo|Tu|We|Th|Fr|Sa|Su|PH))*)\s*)?"
    r"(?P<times>off|closed|\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}(?:\s*,\s*\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2})*)?$"
)


def _osm_days(spec: str | None) -> list[int] | None:
    if not spec:
        return list(range(7))
    days: list[int] = []
    for part in re.split(r"\s*,\s*", spec):
        if part == "PH":
            continue
        if "-" in part:
            a, b = [p.strip() for p in part.split("-")]
            if "PH" in (a, b):
                return None
            i, j = _OSM_DAY[a], _OSM_DAY[b]
            days.extend(range(i, j + 1) if i <= j else list(range(i, 7)) + list(range(0, j + 1)))
        else:
            days.append(_OSM_DAY[part])
    return days


def _osm_cleanup(text: str) -> str:
    text = re.sub(r"\s*,\s*(?:PH|SH)\b|\b(?:PH|SH)\s*,\s*", "", text)  # święta / ferie – pomijamy
    # brakujące średniki między regułami: "Mo-Fr 06:30-20:00 Sa 07:00-14:00", "Mo 07:00-17:00, Tu-Th ..."
    text = re.sub(r"(\d{1,2}:\d{2})\s*,?\s+(?=(?:Mo|Tu|We|Th|Fr|Sa|Su)\b)", r"\1; ", text)
    return text


def parse_osm(value: str | None) -> Hours:
    if not value:
        return UNKNOWN
    text = _osm_cleanup(value.strip())
    if text in {"24/7", "Mo-Su 00:00-24:00", "00:00-24:00", "Mo-Su 0:00-24:00"}:
        return ALWAYS
    week: dict[int, list[tuple[int, int]]] = {}
    for raw_rule in re.split(r"\s*(?:;|\|\|)\s*", text):
        rule = raw_rule.strip().rstrip(",")
        if not rule:
            continue
        m = _OSM_RULE.match(rule)
        if not m or (not m.group("days") and not m.group("times")):
            return UNKNOWN  # miesiące, sezony, wschód słońca itp. – nie zgadujemy
        days_spec, times = m.group("days"), m.group("times")
        if days_spec and days_spec.strip() == "PH":
            continue  # reguła tylko dla świąt – pomijamy
        days = _osm_days(days_spec)
        if days is None:
            return UNKNOWN
        if not times:
            return UNKNOWN
        for d in days:  # późniejsza reguła nadpisuje wcześniejszą dla tych dni
            week[d] = []
        if times in ("off", "closed"):
            continue
        for span in times.split(","):
            a, b = [t.strip() for t in span.split("-")]
            s = _minutes(*a.split(":"))
            e = _minutes(*b.split(":"))
            if s is None or e is None:
                return UNKNOWN
            for d in days:
                _add_interval(week, d, s, e)
    return _finalize(week)


# ---------------------------------------------------------------- polskie opisy

_H24 = re.compile(
    r"\b24\s*/\s*7\b|\b24\s*h\b|\b24\s*godz|całodob|calodob|całą dobę|cala dobe|przez całą dobę|non[- ]?stop",
    re.IGNORECASE,
)
_NOT_H24 = re.compile(r"\bnie\s+(?:jest\s+)?(?:dostępny\s+)?(?:całodob|24)", re.IGNORECASE)
_PL_DAYS: list[tuple[str, int]] = [
    (r"pon(?:iedzia[lł](?:ek|ku))?|pn", 0),
    (r"wt(?:or(?:ek|ku))?", 1),
    (r"[sś]r(?:od[ay])?", 2),
    (r"czw(?:art(?:ek|ku))?", 3),
    (r"pi[aą]t(?:ek|ku)?|pt", 4),
    (r"sob(?:ot[ay])?|sb", 5),
    (r"niedz(?:iel[ai])?|ndz|nd", 6),
]
_DAY_ALT = "|".join(f"(?:{p})" for p, _ in _PL_DAYS)
_DAY_TOKEN = re.compile(rf"(?<![a-ząćęłńóśźż])({_DAY_ALT})\.?(?![a-ząćęłńóśźż])", re.IGNORECASE)
_VAGUE = re.compile(r"godzinach (?:pracy|otwarcia)|godz\. (?:pracy|otwarcia)|w czasie (?:pracy|sezonu)|sezon", re.IGNORECASE)


def _day_index(token: str) -> int | None:
    t = token.lower().rstrip(".")
    for pattern, idx in _PL_DAYS:
        if re.fullmatch(pattern, t, re.IGNORECASE):
            return idx
    return None


_GROUP_WORDS = [
    (re.compile(r"dni\s+(?:powszednie|robocze)|dzie[nń]\s+roboczy|w\s+tygodniu\s+roboczym", re.IGNORECASE), list(range(5))),
    (re.compile(r"weekend\w*", re.IGNORECASE), [5, 6]),
    (re.compile(r"codziennie|ca[lł]y\s+tydzie[nń]|7\s+dni\s+w\s+tygodniu|ka[zż]dego\s+dnia", re.IGNORECASE), list(range(7))),
]
_DAY_JOIN = re.compile(r"^\s*(?:,|i|oraz|\.)?\s*$", re.IGNORECASE)
_DAY_RANGE = re.compile(r"^\s*\.?\s*(?:-|–|—|do)\s*$", re.IGNORECASE)


def _day_groups(text: str) -> list[tuple[int, int, list[int]]]:
    """Grupy dni w tekście jako (początek, koniec, dni) – np. "pn.-pt.", "sob. i niedz.", "dni robocze"."""
    tokens = [(m.start(), m.end(), _day_index(m.group(1))) for m in _DAY_TOKEN.finditer(text)]
    tokens = [t for t in tokens if t[2] is not None]
    groups: list[tuple[int, int, list[int]]] = []
    i = 0
    while i < len(tokens):
        start, end, d = tokens[i]
        days = [d]
        while i + 1 < len(tokens):
            between = text[end:tokens[i + 1][0]]
            nxt = tokens[i + 1][2]
            if _DAY_RANGE.match(between):
                last = days[-1]
                days.extend(range(last + 1, nxt + 1) if last <= nxt else list(range(last + 1, 7)) + list(range(0, nxt + 1)))
            elif _DAY_JOIN.match(between):
                days.append(nxt)
            else:
                break
            end = tokens[i + 1][1]
            i += 1
        groups.append((start, end, sorted(set(days))))
        i += 1
    for pattern, days in _GROUP_WORDS:
        for m in pattern.finditer(text):
            groups.append((m.start(), m.end(), days))
    return sorted(groups)


_SEASONAL = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Mo|Tu|We|Th|Fr|Sa|Su|PH|SH|sunrise|sunset)\b"
    r"|sezon|wakacj|ferie|stycz|lut(?:y|ego)|marz|kwie|\bmaj[a]?\b|czerw|lip(?:iec|ca)|sierp|wrze[sś]|pa[zź]dziern|listopad|grud",
    re.IGNORECASE,
)


def _normalize_text(value: str) -> str:
    text = " ".join(value.split())
    text = re.sub(r"(\d{1,2});(\d{2})", r"\1:\2", text)  # literówka "7;00"
    # "od godz. 8:00 do godz. 16:00" -> "8:00-16:00"
    text = re.sub(
        r"od\s+(?:godz(?:iny|\.)?\s*)?(\d{1,2}(?:[:.]\d{2})?)\s+do\s+(?:godz(?:iny|\.)?\s*)?(\d{1,2}(?:[:.]\d{2})?)",
        r"\1-\2", text, flags=re.IGNORECASE)
    return text


def parse_text(value: str | None) -> Hours:
    if not value:
        return UNKNOWN
    text = _normalize_text(value)
    if _H24.search(text) and not _NOT_H24.search(text):
        return ALWAYS
    osm = parse_osm(text)
    if osm.known:
        return osm
    if _SEASONAL.search(text):
        return UNKNOWN  # godziny sezonowe lub składnia OSM, której nie rozumiemy – nie zgadujemy
    ranges = list(_TIME_RANGE.finditer(text))
    if not ranges:
        return UNKNOWN
    groups = _day_groups(text)
    bare_text = bool(re.fullmatch(r"\s*" + _TIME_RANGE.pattern + r"\s*", text))
    week: dict[int, list[tuple[int, int]]] = {}
    found_any = False
    for m in ranges:
        preceding = [g for g in groups if g[1] <= m.start()]
        if preceding:
            days = preceding[-1][2]
        else:
            following = [g for g in groups if g[0] >= m.end()]
            days = following[0][2] if following and len(groups) == 1 else list(range(5))  # bez dni: ostrożnie pn-pt
        no_minutes = m.group(2) is None and m.group(4) is None
        if no_minutes and not (groups or "godz" in text.lower() or bare_text):
            continue  # "8-16" bez kontekstu może nie być godziną
        s, e = _minutes(m.group(1), m.group(2)), _minutes(m.group(3), m.group(4))
        if s is None or e is None or s == e:
            continue
        found_any = True
        for d in days:
            _add_interval(week, d, s, e)
    if not found_any:
        return UNKNOWN
    return _finalize(week)


def mentions_24h(value: str | None) -> bool:
    """Czy tekst (np. opis lokalizacji) jawnie mówi o dostępności całodobowej."""
    return bool(value and _H24.search(value) and not _NOT_H24.search(value))


def is_vague(value: str | None) -> bool:
    """Opis typu 'w godzinach pracy obiektu' – wiemy, że dostępność jest ograniczona, ale nie znamy godzin."""
    return bool(value and _VAGUE.search(value))
