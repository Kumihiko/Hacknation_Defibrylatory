from datetime import datetime

import pytest

from aed.normalize.hours import is_open, mentions_24h, parse_osm, parse_text


@pytest.mark.parametrize("text,expected", [
    ("24/7", "24/7"),
    ("Mo-Fr 07:30-15:30", "Mo-Fr 07:30-15:30"),
    ("Mo 08:00-17:00; Tu-Fr 08:00-15:00; Sa-Su, PH off", "Mo 08:00-17:00; Tu-Fr 08:00-15:00"),
    ("Mo-Fr 07:00-17:00; Sa-Su, PH, SH off", "Mo-Fr 07:00-17:00"),
    ("Mo-Fr 06:30-20:00 Sa 07:00-14:00", "Mo-Fr 06:30-20:00; Sa 07:00-14:00"),
    ("Mo 07:00-17:00, Tu-Th 08:00-16:00, Fr 08:00-14:00", "Mo 07:00-17:00; Tu-Th 08:00-16:00; Fr 08:00-14:00"),
])
def test_osm_syntax(text, expected):
    assert parse_text(text).to_osm() == expected


@pytest.mark.parametrize("text,expected", [
    ("24 h", "24/7"),
    ("Całodobowo", "24/7"),
    ("pn. - pt. 6.00-22.00   sob. - niedz. 8.00-22.00", "Mo-Fr 06:00-22:00; Sa-Su 08:00-22:00"),  # Sopot
    ("Poniedziałek: godz. 8:00-18:00; Wtorek-Piątek: godz. 8:00-16:00", "Mo 08:00-18:00; Tu-Fr 08:00-16:00"),  # Warszawa
    ("W dni robocze (poniedziałek - piątek) od godz. 8:00 do godz. 16:00", "Mo-Fr 08:00-16:00"),
    ("poniedziałek - piątek od 7;00 do 20;00", "Mo-Fr 07:00-20:00"),
    ("Dni powszednie 07:00 - 17:00", "Mo-Fr 07:00-17:00"),
    ("sob. i niedz. 9-13", "Sa-Su 09:00-13:00"),
    ("codziennie 6-22", "Mo-Su 06:00-22:00"),
])
def test_polish_text(text, expected):
    assert parse_text(text).to_osm() == expected


@pytest.mark.parametrize("text", [
    "W godzinach otwarcia stacji metra",   # brak godzin – nie zgadujemy
    "Jun-Aug Mo-Su 09:30-18:30",           # sezonowe
    "w sezonie 9-17",
    "",
    None,
])
def test_unknown_is_not_guessed(text):
    assert parse_text(text).known is False


def test_without_days_is_conservative_weekdays_only():
    # brak dni w opisie -> zakładamy tylko dni robocze, żeby nie prowadzić w weekend do zamkniętego AED
    assert parse_text("8.00 - 15.00").to_osm() == "Mo-Fr 08:00-15:00"


def test_over_midnight():
    h = parse_osm("Fr 22:00-06:00")
    assert is_open(h, datetime(2026, 11, 20, 23, 0)) is True   # piątek 23:00
    assert is_open(h, datetime(2026, 11, 21, 5, 0)) is True    # sobota 5:00
    assert is_open(h, datetime(2026, 11, 21, 7, 0)) is False


def test_is_open_boundaries():
    h = parse_text("Mo-Fr 08:00-16:00")
    monday = datetime(2026, 11, 16)
    assert is_open(h, monday.replace(hour=7, minute=59)) is False
    assert is_open(h, monday.replace(hour=8, minute=0)) is True
    assert is_open(h, monday.replace(hour=15, minute=59)) is True
    assert is_open(h, monday.replace(hour=16, minute=0)) is False
    assert is_open(h, datetime(2026, 11, 22, 10, 0)) is False  # niedziela
    assert is_open(parse_text("abc"), monday) is None


def test_mentions_24h():
    assert mentions_24h("Przedsionek schroniska, otwarte całodobowo")
    assert not mentions_24h("nie jest dostępny całodobowo")
    assert not mentions_24h("przy portierni")
