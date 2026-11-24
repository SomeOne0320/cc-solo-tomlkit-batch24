from __future__ import annotations

import re

from collections.abc import Collection
from collections.abc import Mapping
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from datetime import timezone
from typing import Any

from tomlkit._compat import decode


RFC_3339_LOOSE = re.compile(
    "^"
    r"(?P<date>(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2}))?"  # Date
    "("
    "(?P<sep>[Tt ])?"  # Separator
    r"(?P<time>(?P<hour>\d{2}):(?P<minute>\d{2})(:(?P<second>\d{2})(\.(?P<fraction>[0-9]+))?)?)"  # Time
    r"(?P<tz>([Zz])|([\+\-]([01][0-9]|2[0-3]):([0-5][0-9])))?"  # Timezone
    ")?"
    "$"
)

RFC_3339_DATETIME = re.compile(
    "^"
    r"(?P<year>\d{4})-(?P<month>0[1-9]|1[012])-(?P<day>0[1-9]|[12][0-9]|3[01])"  # Date
    "[Tt ]"  # Separator
    r"(?P<hour>[01][0-9]|2[0-3]):(?P<minute>[0-5][0-9])"  # Time
    r"(:(?P<second>[0-5][0-9]|60)(\.(?P<fraction>[0-9]+))?)?"
    r"(?P<tz>([Zz])|([\+\-]([01][0-9]|2[0-3]):([0-5][0-9])))?"  # Timezone
    "$"
)

RFC_3339_DATE = re.compile("^([0-9]+)-(0[1-9]|1[012])-(0[1-9]|[12][0-9]|3[01])$")

RFC_3339_TIME = re.compile(
    r"^(?P<hour>[01][0-9]|2[0-3]):(?P<minute>[0-5][0-9])"
    r"(:(?P<second>[0-5][0-9]|60)(\.(?P<fraction>[0-9]+))?)?$"
)

_utc = timezone(timedelta(), "UTC")


def parse_rfc3339(string: str) -> datetime | date | time:
    m = RFC_3339_DATETIME.match(string)
    if m:
        year = int(m.group("year"))
        month = int(m.group("month"))
        day = int(m.group("day"))
        hour = int(m.group("hour"))
        minute = int(m.group("minute"))
        second = int(m.group("second") or 0)
        microsecond = 0

        if m.group("fraction"):
            microsecond = int((f"{m.group('fraction'):<06s}")[:6])

        if m.group("tz"):
            # Timezone
            tz = m.group("tz")
            if tz.upper() == "Z":
                tzinfo = _utc
            else:
                sign = tz[0]
                hour_offset, minute_offset = map(int, tz[1:].split(":"))
                offset = timedelta(seconds=hour_offset * 3600 + minute_offset * 60)
                if sign == "-":
                    offset = -offset

                tzinfo = timezone(offset, tz)

            return datetime(
                year, month, day, hour, minute, second, microsecond, tzinfo=tzinfo
            )
        else:
            return datetime(year, month, day, hour, minute, second, microsecond)

    m = RFC_3339_DATE.match(string)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3))

        return date(year, month, day)

    m = RFC_3339_TIME.match(string)
    if m:
        hour = int(m.group("hour"))
        minute = int(m.group("minute"))
        second = int(m.group("second") or 0)
        microsecond = 0

        if m.group("fraction"):
            microsecond = int((f"{m.group('fraction'):<06s}")[:6])

        return time(hour, minute, second, microsecond)

    raise ValueError("Invalid RFC 3339 string")


# https://toml.io/en/v1.0.0#string
CONTROL_CHARS = frozenset(chr(c) for c in range(0x20)) | {chr(0x7F)}
_escaped = {
    "b": "\b",
    "t": "\t",
    "n": "\n",
    "f": "\f",
    "r": "\r",
    "e": "\x1b",
    '"': '"',
    "\\": "\\",
}
_compact_escapes = {
    # ``\e`` is TOML 1.1 only; write ESC as ``\u001b`` so TOML 1.0 parsers
    # (e.g. ``tomllib``) can read the output.
    **{v: f"\\{k}" for k, v in _escaped.items() if k != "e"},
    '"""': '""\\"',
}
_basic_escapes = CONTROL_CHARS | {'"', "\\"}


def validate_comment(comment: str, *, multiline: bool = False) -> None:
    """Reject forbidden controls, optionally allowing LF and CRLF line endings."""
    if not multiline and ("\n" in comment or "\r" in comment):
        raise ValueError("Comment cannot contain line breaks")
    for char in comment.replace("\r\n", "\n"):
        if char in CONTROL_CHARS and char not in "\t\n":
            raise ValueError(f"Comment cannot contain control character {char!r}")


def _unicode_escape(seq: str) -> str:
    return "".join(f"\\u{ord(c):04x}" for c in seq)


def _escape_match(match: re.Match[str]) -> str:
    seq = match.group()
    return _compact_escapes.get(seq) or _unicode_escape(seq)


def escape_string(s: str, escape_sequences: Collection[str] = _basic_escapes) -> str:
    s = decode(s)

    found_sequences = [seq for seq in escape_sequences if seq in s]
    if not found_sequences:
        # always return a plain str, also for str subclasses such as String
        return str(s)

    # Replace every sequence in a single left-to-right pass. Longer sequences
    # come first so that '"""' is matched as a whole.
    pattern = "|".join(
        re.escape(seq) for seq in sorted(found_sequences, key=len, reverse=True)
    )
    return re.sub(pattern, _escape_match, s)


def merge_dicts(d1: dict[str, Any], d2: dict[str, Any]) -> None:
    for k, v in d2.items():
        if k in d1 and isinstance(d1[k], dict) and isinstance(v, Mapping):
            merge_dicts(d1[k], dict(v))
        elif k in d1 and type(d1[k]) is list and type(v) is list:
            # AoT.value creates plain lists for each fragment. Arrays retain
            # their Array wrapper and must keep the usual replacement behavior.
            d1[k].extend(v)
        else:
            d1[k] = d2[k]


# A line feed that does not belong to a CRLF pair, i.e. a bare LF line ending.
_BARE_LF = re.compile(r"(?<!\r)\n")


def detect_linesep(content: str) -> str | None:
    """Return the line ending convention of ``content``.

    The result is ``"\\r\\n"`` when every line ending is CRLF, ``"\\n"`` when
    they are all bare LF, and ``None`` for mixed line endings or content that
    contains no line endings at all (a single-line file or a new document).
    Counting the raw source -- including newlines inside multiline strings --
    matches how the text was stored on disk.
    """
    num_newline = content.count("\n")
    if num_newline == 0:
        return None

    num_crlf = content.count("\r\n")
    if num_crlf == num_newline:
        return "\r\n"
    if num_crlf == 0:
        return "\n"
    return None


def strip_linesep(text: str) -> str:
    """Remove structural line endings (CRLF or bare LF) from ``text``.

    Inline tables render on one line, so trivia trails that carry a line
    ending in the source have it dropped on rendering -- including the CR of a
    CRLF pair, which a plain ``replace("\\n", "")`` would leave behind.
    """
    return text.replace("\r\n", "").replace("\n", "")


def to_linesep(text: str, linesep: str) -> str:
    """Apply a line ending convention to structural text (trivia/whitespace).

    Only bare line feeds are rewritten; existing CRLF pairs are left untouched,
    so the call is idempotent and never produces ``\\r\\r\\n``. This must not
    be used on string literals, whose newlines -- including those inside
    multiline strings -- are part of the value and have to be preserved.
    """
    if linesep == "\r\n":
        if "\n" not in text:
            return text
        return _BARE_LF.sub("\r\n", text)
    if linesep == "\n":
        if "\r" not in text:
            return text
        return text.replace("\r\n", "\n")
    return text
