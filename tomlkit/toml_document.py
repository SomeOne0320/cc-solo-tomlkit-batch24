from __future__ import annotations

import contextlib

from collections.abc import Iterator
from typing import TYPE_CHECKING
from typing import Any

from tomlkit._linesep import current_linesep
from tomlkit._utils import to_linesep
from tomlkit.container import Container
from tomlkit.items import AoT
from tomlkit.items import Array
from tomlkit.items import InlineTable
from tomlkit.items import Table
from tomlkit.items import Trivia
from tomlkit.items import Whitespace


if TYPE_CHECKING:
    from tomlkit.items import Item


def _structural_text_holders(item: Item) -> Iterator[Whitespace | Trivia]:
    """Yield every piece of structural text owned by ``item``.

    Structural text is the whitespace and trivia (indentation, comments and
    trailing newlines) rendered outside of string literals. Newlines inside
    ``String`` items are part of the value -- including the body of multiline
    strings -- and are therefore never yielded, so applying a line ending
    convention here cannot alter string contents.
    """
    if isinstance(item, Whitespace):
        yield item
        return

    trivia = getattr(item, "_trivia", None)
    if isinstance(trivia, Trivia):
        yield trivia

    if isinstance(item, (Table, InlineTable)):
        # Table and inline-table bodies both render their children. A dotted
        # key inside an inline table materializes as a super Table nested in
        # its body, so the descent cannot stop at the first Table; recurse
        # into every container, including nested ones.
        for _, child in item.value.body:
            yield from _structural_text_holders(child)
    elif isinstance(item, AoT):
        for table in item.body:
            yield from _structural_text_holders(table)
    elif isinstance(item, Array):
        # Inline tables can appear as array elements.
        for group in item._value:
            for child in group:
                yield from _structural_text_holders(child)


class TOMLDocument(Container):
    """
    A TOML document.
    """

    def __init__(self, parsed: bool = False) -> None:
        super().__init__(parsed)
        # Line ending convention of the source text: "\r\n", "\n" or None.
        # None means a new document, a file without line endings, or mixed line
        # endings -- in all of those cases new lines use the library default
        # ("\n") and existing lines are left untouched.
        self._linesep: str | None = None

    @property
    def linesep(self) -> str | None:
        """The line ending convention detected in the source text.

        ``"\\r\\n"`` for an all-CRLF document, ``"\\n"`` for an all-LF one and
        ``None`` for new documents, line-ending-free files and documents with
        mixed line endings.
        """
        return self._linesep

    @contextlib.contextmanager
    def _apply_linesep(self) -> Iterator[None]:
        """Temporarily apply the document's line ending convention.

        Only structural whitespace/trivia is rewritten, and only bare line
        feeds are converted, so existing CRLF lines and multiline string
        contents survive untouched. The original text is restored afterwards,
        leaving the parsed model unchanged between two ``as_string()`` calls.
        """
        linesep = self._linesep
        if linesep is None:
            yield
            return

        token = current_linesep.set(linesep)
        snapshots: list[tuple[Whitespace | Trivia, str, str]] = []
        for _, item in self._body:
            for holder in _structural_text_holders(item):
                if isinstance(holder, Whitespace):
                    original = holder.s
                    converted = to_linesep(original, linesep)
                    if converted != original:
                        holder._s = converted
                        snapshots.append((holder, original, "_s"))
                else:
                    for field in ("indent", "comment_ws", "comment", "trail"):
                        original = getattr(holder, field)
                        converted = to_linesep(original, linesep)
                        if converted != original:
                            setattr(holder, field, converted)
                            snapshots.append((holder, original, field))

        try:
            yield
        finally:
            current_linesep.reset(token)
            for holder, original, field in snapshots:
                if isinstance(holder, Whitespace):
                    holder._s = original
                else:
                    setattr(holder, field, original)

    def as_string(self) -> str:
        """Render as TOML string, following the source line ending convention."""
        with self._apply_linesep():
            return super().as_string()

    def __copy__(self) -> TOMLDocument:
        copied = super().__copy__()
        copied._linesep = self._linesep
        return copied

    def __deepcopy__(self, memo: dict[int, object]) -> TOMLDocument:
        copied = super().__deepcopy__(memo)
        copied._linesep = self._linesep
        return copied

    def __reduce_ex__(  # type: ignore[override]
        self, protocol: int
    ) -> tuple[type, tuple[bool], tuple[Any, ...]]:
        # Container.__reduce_ex__ builds (cls, constructor args, body state);
        # carry the line ending convention alongside the body state so a
        # pickled document keeps it on round-trip.
        cls, args, state = super().__reduce_ex__(protocol)
        return cls, args, (*state, self._linesep)

    def __setstate__(self, state: tuple[Any, ...]) -> None:
        # The extended document state appends the line ending convention to
        # the four fields Container's reduction stores.
        linesep: str | None = state[4] if len(state) > 4 else None
        super().__setstate__(state[:4])
        self._linesep = linesep
