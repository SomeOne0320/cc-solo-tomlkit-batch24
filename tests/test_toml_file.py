import os

from collections.abc import Callable
from pathlib import Path

from tomlkit import dumps
from tomlkit.toml_document import TOMLDocument
from tomlkit.toml_file import TOMLFile


def test_toml_file(example: Callable[[str], str]) -> None:
    original_content = example("example")

    toml_file = os.path.join(os.path.dirname(__file__), "examples", "example.toml")
    toml = TOMLFile(toml_file)

    content = toml.read()
    assert isinstance(content, TOMLDocument)
    assert content["owner"]["organization"] == "GitHub"

    toml.write(content)

    try:
        with open(toml_file, encoding="utf-8") as f:
            assert original_content == f.read()
    finally:
        with open(toml_file, "w", encoding="utf-8", newline="") as f:
            assert f.write(original_content)


def test_keep_old_eol(tmp_path: Path) -> None:
    toml_path = tmp_path / "pyproject.toml"
    with open(toml_path, "wb+") as fh:
        fh.write(b"a = 1\r\nb = 2\r\n")

    toml_f = TOMLFile(toml_path)
    content = toml_f.read()
    content["b"] = 3
    toml_f.write(content)

    with open(toml_path, "rb") as fh:
        assert fh.read() == b"a = 1\r\nb = 3\r\n"


def test_keep_old_eol_2(tmp_path: Path) -> None:
    toml_path = tmp_path / "pyproject.toml"
    with open(toml_path, "wb+") as fh:
        fh.write(b"a = 1\nb = 2\n")

    toml_f = TOMLFile(toml_path)
    content = toml_f.read()
    content["b"] = 3
    toml_f.write(content)

    with open(toml_path, "rb") as fh:
        assert fh.read() == b"a = 1\nb = 3\n"


def test_mixed_eol(tmp_path: Path) -> None:
    toml_path = tmp_path / "pyproject.toml"
    with open(toml_path, "wb+") as fh:
        fh.write(b"a = 1\r\nrb = 2\n")

    toml_f = TOMLFile(toml_path)
    toml_f.write(toml_f.read())

    with open(toml_path, "rb") as fh:
        assert fh.read() == b"a = 1\r\nrb = 2\n"


def test_consistent_eol(tmp_path: Path) -> None:
    toml_path = tmp_path / "pyproject.toml"
    with open(toml_path, "wb+") as fh:
        fh.write(b"a = 1\r\nb = 2\r\n")

    toml_f = TOMLFile(toml_path)
    content = toml_f.read()
    content["c"] = 3
    toml_f.write(content)

    with open(toml_path, "rb") as fh:
        assert fh.read() == b"a = 1\r\nb = 2\r\nc = 3\r\n"


def test_consistent_eol_2(tmp_path: Path) -> None:
    toml_path = tmp_path / "pyproject.toml"
    with open(toml_path, "wb+") as fh:
        fh.write(b"a = 1\nb = 2\n")

    toml_f = TOMLFile(toml_path)
    content = toml_f.read()
    content["c"] = 3
    content["c"].trivia.trail = "\r\n"
    toml_f.write(content)

    with open(toml_path, "rb") as fh:
        assert fh.read() == b"a = 1\nb = 2\nc = 3\n"


def test_new_documents_keep_the_library_default_linesep(tmp_path: Path) -> None:
    toml_path = tmp_path / "pyproject.toml"
    toml_f = TOMLFile(toml_path)
    content = TOMLDocument()
    content.append("a", 1)
    content.append("b", 2)
    toml_f.write(content)

    # A document that was not parsed from a file carries no line ending
    # convention, so the library default ("\n") is used and nothing is
    # rewritten through an os.linesep-dependent state on the file object.
    with open(toml_path, "rb") as fh:
        assert fh.read() == b"a = 1\nb = 2\n"


def test_toml_file_does_not_carry_linesep_between_files(tmp_path: Path) -> None:
    crlf_path = tmp_path / "windows.toml"
    lf_path = tmp_path / "unix.toml"
    crlf_path.write_bytes(b"a = 1\r\n")
    lf_path.write_bytes(b"b = 2\n")

    toml_f = TOMLFile(crlf_path)
    crlf_doc = toml_f.read()
    assert crlf_doc.linesep == "\r\n"

    # The same file object then reads another file: the first file's CRLF
    # convention must not leak onto the second document or its output.
    toml_f._path = lf_path
    lf_doc = toml_f.read()
    assert lf_doc.linesep == "\n"
    assert dumps(lf_doc) == "b = 2\n"
    assert dumps(crlf_doc) == "a = 1\r\n"


def test_readwrite_eol_windows(tmp_path: Path) -> None:
    toml_path = tmp_path / "pyproject.toml"
    doc = TOMLDocument()
    doc.add("a", 1)
    toml_f = TOMLFile(toml_path)
    toml_f.write(doc)
    readback = toml_f.read()
    assert doc.as_string() == readback.as_string()
