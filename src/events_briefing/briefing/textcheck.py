"""Checks on briefing prose: counts, dates, plurals, boroughs, and relative time.

A failure here retries the provider, then falls back.

External verification VERIFY_REPORT_10 on 2026-10-17 (n=19 incorrect texts,
small sample, not conclusive) detected 13/19. False positives on that check
were 1/10. One false positive was a borough-scoped category count ("Two
structural fires in Brooklyn and three in the Bronx") compared with the
segment total. This lab did not re-run that set. Recall after the scoped-count
fix is not measured yet.

The checker does not cover "Brooklyn saw 4…", invented casualties, or invented
superlatives. It is not a reliable control.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from events_briefing.models import RankedIncident
from events_briefing.normalize import local_calendar_date

_NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_COUNT_TOKEN = r"\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
_MONTHS = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}
_MONTHS.update(
    {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "sept": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
)
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTH_FIRST = re.compile(rf"\b({_MONTH_ALT})\s+(\d{{1,2}}),\s+(\d{{4}})\b", re.IGNORECASE)
_DAY_FIRST = re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_ALT})\s+(\d{{4}})\b", re.IGNORECASE)
_INCIDENT_COUNT = re.compile(rf"\b({_COUNT_TOKEN})\s+(incidents?)\b", re.IGNORECASE)
_BOROUGH_NAMES: tuple[tuple[str, str], ...] = (
    ("staten island", "Staten Island"),
    ("brooklyn", "Brooklyn"),
    ("manhattan", "Manhattan"),
    ("queens", "Queens"),
    ("bronx", "Bronx"),
)
_BOROUGH_ALT = "|".join(name for name, _canonical in _BOROUGH_NAMES)
_BOROUGH_COUNT = re.compile(
    rf"\b({_COUNT_TOKEN}|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)"
    rf"\s+(?:in|en)\s+(?:the\s+|el\s+|la\s+)?({_BOROUGH_ALT})\b",
    re.IGNORECASE,
)
# External verification only. This lab did not re-run the set.
EXTERNAL_INCORRECT_DETECTED = "13/19"
EXTERNAL_FALSE_POSITIVES = "1/10"
EXTERNAL_SOURCE = (
    "external verification VERIFY_REPORT_10, 2026-10-17, n=19 incorrect texts, "
    "small sample, not conclusive; not re-measured in this lab"
)
POST_CHANGE_RECALL = "not measured yet"
_SCOPE_AFTER = re.compile(
    rf"(?:\s+\w+){{0,6}}?\s+(?:in|en)\s+(?:the\s+|el\s+|la\s+)?({_BOROUGH_ALT})\b",
    re.IGNORECASE,
)
_SPANISH_COUNTS = {
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
}

# Longer phrases first so "this morning" is judged as today-class, not a fragment.
_RELATIVE: tuple[tuple[str, str], ...] = (
    ("this morning", "today"),
    ("this afternoon", "today"),
    ("this evening", "today"),
    ("right now", "never"),
    ("esta mañana", "today"),
    ("esta noche", "today"),
    ("tonight", "today"),
    ("yesterday", "yesterday"),
    ("recently", "never"),
    ("today", "today"),
    ("ahora", "never"),
    ("ayer", "yesterday"),
    ("hoy", "today"),
)


def category_forms(category: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", category.strip().lower())
    if text.endswith("ies") and len(text) > 3:
        return text[:-3] + "y", text
    if text.endswith("s") and not text.endswith("ss") and len(text) > 1:
        return text[:-1], text
    if text.endswith("y") and len(text) > 1 and text[-2] not in "aeiou":
        return text, text[:-1] + "ies"
    if text.endswith(("s", "x", "z", "ch", "sh")):
        return text, text + "es"
    return text, text + "s"


def validate_briefing_text(
    segments: list[dict[str, object]],
    ranked: list[RankedIncident],
    as_of: date,
) -> list[str]:
    by_id = {item.incident.id: item for item in ranked}
    errors: list[str] = []
    for index, segment in enumerate(segments, start=1):
        raw_ids = segment.get("source_incident_ids")
        if not isinstance(raw_ids, list):
            errors.append(f"segment {index} has no source ids")
            continue
        cited = [by_id[str(item)] for item in raw_ids if str(item) in by_id]
        if len(cited) != len(raw_ids):
            errors.append(f"segment {index} cites an unknown id")
        headline = str(segment.get("headline") or "")
        why = str(segment.get("why_it_matters") or "")
        errors.extend(_check_segment(index, f"{headline}\n{why}", cited, as_of))
    return errors


def _check_segment(index: int, text: str, cited: list[RankedIncident], as_of: date) -> list[str]:
    errors: list[str] = []
    occurred = {local_calendar_date(item.incident.created_at) for item in cited}
    allowed = set(occurred)
    allowed.add(as_of)
    for found in _extract_dates(text):
        if found not in allowed:
            errors.append(
                f"segment {index} mentions {found.isoformat()}, not as-of or a cited date"
            )
    for moment in sorted(occurred):
        if not _date_present(text, moment):
            errors.append(f"segment {index} omits cited date {moment.isoformat()}")
    errors.extend(_relative(index, text, occurred, as_of))
    errors.extend(_incident_count(index, text, len(cited)))
    errors.extend(_category_counts(index, text, cited))
    errors.extend(_borough_counts(index, text, cited))
    return errors


def _extract_dates(text: str) -> list[date]:
    found: list[date] = []
    for match in _ISO.finditer(text):
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed is not None:
            found.append(parsed)
    for match in _MONTH_FIRST.finditer(text):
        month = _MONTHS[match.group(1).lower()]
        parsed = _safe_date(int(match.group(3)), month, int(match.group(2)))
        if parsed is not None:
            found.append(parsed)
    for match in _DAY_FIRST.finditer(text):
        month = _MONTHS[match.group(2).lower()]
        parsed = _safe_date(int(match.group(3)), month, int(match.group(1)))
        if parsed is not None:
            found.append(parsed)
    return found


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _date_present(text: str, moment: date) -> bool:
    if moment.isoformat() in text:
        return True
    month = moment.strftime("%B")
    patterns = (
        rf"\b{month}\s+{moment.day},\s+{moment.year}\b",
        rf"\b{moment.day}\s+{month}\s+{moment.year}\b",
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _relative(index: int, text: str, occurred: set[date], as_of: date) -> list[str]:
    errors: list[str] = []
    for phrase, kind in _RELATIVE:
        if not _present(text, phrase):
            continue
        if kind == "never" or not occurred:
            errors.append(f"segment {index} uses relative time {phrase!r}, which is not supported")
            continue
        if kind == "today" and occurred != {as_of}:
            errors.append(
                f"segment {index} says {phrase!r} but cited dates are not all {as_of.isoformat()}"
            )
        if kind == "yesterday" and occurred != {as_of - timedelta(days=1)}:
            errors.append(
                f"segment {index} says {phrase!r} but cited dates are not the day before as-of"
            )
    return errors


def _incident_count(index: int, text: str, count: int) -> list[str]:
    errors: list[str] = []
    if re.search(r"\bincidents\b", text, re.IGNORECASE) and count == 1:
        errors.append(f"segment {index} uses plural 'incidents' for 1 cited incident")
    if re.search(r"\bincident\b", text, re.IGNORECASE) and count != 1:
        errors.append(f"segment {index} uses singular 'incident' for {count} cited incidents")
    for match in _INCIDENT_COUNT.finditer(text):
        number = _parse_count(match.group(1))
        word = match.group(2).lower()
        if number is None:
            continue
        if number != count:
            errors.append(f"segment {index} says {number} {word} but cites {count}")
    return errors


def _category_counts(index: int, text: str, cited: list[RankedIncident]) -> list[str]:
    errors: list[str] = []
    counts: dict[str, int] = {}
    by_borough: dict[tuple[str, str], int] = {}
    forms: dict[str, tuple[str, str]] = {}
    for item in cited:
        singular, plural = category_forms(item.incident.category)
        counts[singular] = counts.get(singular, 0) + 1
        forms[singular] = (singular, plural)
        borough = item.incident.borough or ""
        key = (singular, borough)
        by_borough[key] = by_borough.get(key, 0) + 1
    for singular, (sing, plural) in forms.items():
        count = counts[singular]
        if count == 1 and _present(text, plural):
            errors.append(f"segment {index} uses plural {plural!r} for 1 cited incident")
        if count > 1 and _present(text, sing):
            errors.append(f"segment {index} uses singular {sing!r} for {count} cited incidents")
        for phrase in (sing, plural):
            for number, scoped in _explicit_counts(text, phrase):
                if scoped is None:
                    if number != count:
                        errors.append(f"segment {index} says {number} {phrase!r} but cites {count}")
                    continue
                found = by_borough.get((singular, scoped), 0)
                if number != found:
                    errors.append(
                        f"segment {index} says {number} {phrase!r} in {scoped} but cites {found}"
                    )
    return errors


def _borough_counts(index: int, text: str, cited: list[RankedIncident]) -> list[str]:
    errors: list[str] = []
    actual: dict[str, int] = {}
    for item in cited:
        borough = item.incident.borough
        if borough:
            actual[borough] = actual.get(borough, 0) + 1
    for match in _BOROUGH_COUNT.finditer(text):
        number = _parse_count(match.group(1))
        canonical = _canonical_borough(match.group(2))
        if number is None or canonical is None:
            continue
        found = actual.get(canonical, 0)
        if number != found:
            errors.append(f"segment {index} says {number} in {canonical} but cites {found}")
    for alias, canonical in _BOROUGH_NAMES:
        if actual.get(canonical, 0) == 0 and _present(text, alias):
            errors.append(f"segment {index} names {canonical}, which has no cited incident")
    return errors


def _canonical_borough(text: str) -> str | None:
    key = text.lower()
    for alias, canonical in _BOROUGH_NAMES:
        if key == alias:
            return canonical
    return None


def _explicit_counts(text: str, phrase: str) -> list[tuple[int, str | None]]:
    body = r"\s+".join(re.escape(part) for part in phrase.split())
    pattern = re.compile(rf"\b({_COUNT_TOKEN})\s+{body}\b", re.IGNORECASE)
    found: list[tuple[int, str | None]] = []
    for match in pattern.finditer(text):
        number = _parse_count(match.group(1))
        if number is None:
            continue
        scoped = _SCOPE_AFTER.match(text, match.end())
        borough = _canonical_borough(scoped.group(1)) if scoped is not None else None
        found.append((number, borough))
    return found


def _present(text: str, phrase: str) -> bool:
    parts = [re.escape(part) for part in phrase.split()]
    return re.search(r"\b" + r"\s+".join(parts) + r"\b", text, re.IGNORECASE) is not None


def _parse_count(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    lowered = token.lower()
    if lowered in _NUMBER_WORDS:
        return _NUMBER_WORDS[lowered]
    return _SPANISH_COUNTS.get(lowered)
