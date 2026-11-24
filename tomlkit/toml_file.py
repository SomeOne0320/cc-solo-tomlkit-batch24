import os

from typing import TYPE_CHECKING

from tomlkit.api import loads
from tomlkit.toml_document import TOMLDocument


if TYPE_CHECKING:
    from _typeshed import StrPath as _StrPath
else:
    from typing import Union

    _StrPath = Union[str, os.PathLike]


class TOMLFile:
    """
    Represents a TOML file.

    Line endings are handled by the parsed document itself: an all-CRLF or
    all-LF file keeps its convention (including for newly added lines), mixed
    line endings are preserved line by line, and new documents or files
    without line endings keep the library default. Reusing a ``TOMLFile`` to
    read several files therefore cannot let one file's format affect another.

    :param path: path to the TOML file
    """

    def __init__(self, path: _StrPath) -> None:
        self._path = path

    def read(self) -> TOMLDocument:
        """Read the file content as a :class:`tomlkit.toml_document.TOMLDocument`."""
        with open(self._path, encoding="utf-8", newline="") as f:
            # newline="" keeps every line ending verbatim; the parser and the
            # document remember the convention instead of normalizing the
            # source (which would also rewrite multiline string contents).
            return loads(f.read())

    def write(self, data: TOMLDocument) -> None:
        """Write the TOMLDocument to the file."""
        with open(self._path, "w", encoding="utf-8", newline="") as f:
            f.write(data.as_string())
