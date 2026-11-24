from __future__ import annotations

import contextvars


# Line ending convention (``"\r\n"`` or ``"\n"``) of the document currently
# being rendered, or ``None`` outside of a document render. Renderers that emit
# a newline directly instead of through trivia/whitespace (e.g. a multiline
# array built by the library, or separator newlines between rendered tables)
# consult this so their output matches the parsed document's convention.
current_linesep: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_linesep", default=None
)


def nl() -> str:
    """A newline following the line ending convention currently being rendered."""
    linesep = current_linesep.get()
    return "\r\n" if linesep == "\r\n" else "\n"
