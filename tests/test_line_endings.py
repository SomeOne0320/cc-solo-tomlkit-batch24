"""Line ending handling on parsed documents and files.

The line ending convention belongs to the parsed document, not to the
``TOMLFile`` that read it: documents produced by ``parse``/``loads``/``load``
and ``TOMLFile.read`` from the same text follow the same rules when saved to
a file, a stream or a string.
"""

import io

from pathlib import Path

import pytest

from tomlkit import dumps
from tomlkit import load
from tomlkit import parse
from tomlkit.toml_file import TOMLFile


CRLF = "\r\n"
LF = "\n"


def test_all_crlf_document_keeps_convention_for_new_lines() -> None:
    doc = parse(f"a = 1{CRLF}b = 2{CRLF}")
    assert doc.linesep == CRLF

    doc["c"] = 3
    assert dumps(doc) == f"a = 1{CRLF}b = 2{CRLF}c = 3{CRLF}"
    # rendering must not mutate the parsed model itself
    assert doc["c"].trivia.trail == LF


def test_all_lf_document_keeps_convention_for_new_lines() -> None:
    doc = parse("a = 1\nb = 2\n")
    assert doc.linesep == LF

    doc["c"] = 3
    assert dumps(doc) == "a = 1\nb = 2\nc = 3\n"


def test_mixed_line_endings_keep_every_existing_line() -> None:
    source = f"a = 1{CRLF}b = 2{LF}c = 3{CRLF}"
    doc = parse(source)
    assert doc.linesep is None

    # unchanged documents round-trip byte for byte
    assert dumps(doc) == source

    # newly added lines use the library default, existing lines stay as they were
    doc["d"] = 4
    assert dumps(doc) == f"a = 1{CRLF}b = 2{LF}c = 3{CRLF}d = 4{LF}"


def test_file_without_line_endings_uses_the_default() -> None:
    doc = parse("a = 1")
    assert doc.linesep is None
    assert dumps(doc) == "a = 1"

    doc["b"] = 2
    assert dumps(doc) == "a = 1\nb = 2\n"


def test_newly_built_documents_use_the_default() -> None:
    from tomlkit import document

    doc = document()
    assert doc.linesep is None
    doc.add("a", 1)
    doc.add("b", 2)
    assert dumps(doc) == "a = 1\nb = 2\n"


def test_multiline_string_with_crlf_is_never_rewritten() -> None:
    for delim in ('"""', "'''"):
        source = f"a = {delim}foo{CRLF}bar{delim}{CRLF}b = 2{CRLF}"
        doc = parse(source)
        assert doc.linesep == CRLF
        assert doc["a"] == f"foo{CRLF}bar"

        doc["c"] = 3
        rendered = dumps(doc)
        # the string body keeps its CRLF even though only trivia is converted
        assert rendered == f"a = {delim}foo{CRLF}bar{delim}{CRLF}b = 2{CRLF}c = 3{CRLF}"


def test_mixed_endings_inside_multiline_string_are_preserved() -> None:
    body = f"crlf{CRLF}and{LF}lf"
    source = f'a = """{body}"""{CRLF}'
    doc = parse(source)

    rendered = dumps(doc)
    assert rendered == source
    assert doc["a"] == body


def test_rendering_does_not_mutate_the_document_and_is_repeatable() -> None:
    doc = parse(f"a = 1{CRLF}")
    doc["b"] = 2

    first = dumps(doc)
    second = dumps(doc)
    assert first == second == f"a = 1{CRLF}b = 2{CRLF}"
    # the stored trivia still uses the library default
    assert doc["b"].trivia.trail == LF


@pytest.mark.parametrize(
    ("source", "linesep"),
    [
        (f"a = 1{CRLF}", CRLF),
        ("a = 1\n", LF),
        (f"a = 1{CRLF}b = 2\n", None),
        ("a = 1", None),
    ],
)
def test_read_load_and_parse_agree_on_the_convention(
    tmp_path: Path, source: str, linesep: str | None
) -> None:
    path = tmp_path / "doc.toml"
    path.write_bytes(source.encode())

    from_file = TOMLFile(path).read()
    with open(path, encoding="utf-8", newline="") as fp:
        from_stream = load(fp)
    from_string = parse(source)

    assert from_file.linesep == linesep
    assert from_stream.linesep == linesep
    assert from_string.linesep == linesep
    assert dumps(from_file) == dumps(from_stream) == dumps(from_string) == source


def test_toml_file_write_and_stream_dump_produce_identical_output(
    tmp_path: Path,
) -> None:
    path = tmp_path / "doc.toml"
    path.write_bytes(f"a = 1{CRLF}b = 2{CRLF}".encode())

    doc = TOMLFile(path).read()
    doc["c"] = 3

    TOMLFile(path).write(doc)
    file_bytes = path.read_bytes()

    stream = io.StringIO()
    import tomlkit

    tomlkit.dump(doc, stream)

    assert stream.getvalue().encode() == file_bytes
    assert file_bytes == f"a = 1{CRLF}b = 2{CRLF}c = 3{CRLF}".encode()


def test_round_tripped_file_reparses_to_the_same_values(tmp_path: Path) -> None:
    path = tmp_path / "doc.toml"
    path.write_bytes(
        f'[tool]{CRLF}name = "demo"{CRLF}text = """line1{CRLF}line2"""{CRLF}'.encode()
    )

    toml_file = TOMLFile(path)
    doc = toml_file.read()
    doc["tool"]["new"] = ["x", "y"]
    toml_file.write(doc)

    reparsed = parse(open(path, encoding="utf-8", newline="").read())
    assert reparsed["tool"]["name"] == "demo"
    assert reparsed["tool"]["new"] == ["x", "y"]
    assert reparsed["tool"]["text"] == f"line1{CRLF}line2"
    assert reparsed.linesep == CRLF


def test_reading_two_files_with_one_toml_file_keeps_formats_isolated(
    tmp_path: Path,
) -> None:
    windows = tmp_path / "windows.toml"
    unix = tmp_path / "unix.toml"
    windows.write_bytes(f"a = 1{CRLF}".encode())
    unix.write_bytes("b = 2\n".encode())

    toml_file = TOMLFile(windows)
    windows_doc = toml_file.read()

    toml_file._path = unix
    unix_doc = toml_file.read()

    assert windows_doc.linesep == CRLF
    assert unix_doc.linesep == LF
    assert dumps(windows_doc) == f"a = 1{CRLF}"
    assert dumps(unix_doc) == "b = 2\n"


def test_crlf_document_with_table_and_comment(tmp_path: Path) -> None:
    source = f"# header{CRLF}[section]{CRLF}key = 1  # inline{CRLF}"
    path = tmp_path / "doc.toml"
    path.write_bytes(source.encode())

    doc = TOMLFile(path).read()
    doc["section"]["added"] = 2
    TOMLFile(path).write(doc)

    expected = f"# header{CRLF}[section]{CRLF}key = 1  # inline{CRLF}added = 2{CRLF}"
    assert path.read_bytes() == expected.encode()
    # comments keep their own text, only the structural newline changed
    with open(path, encoding="utf-8", newline="") as fp:
        assert parse(fp.read())["section"]["added"] == 2


def test_lf_document_normalizes_a_crlf_trivia_trail() -> None:
    doc = parse("a = 1\nb = 2\n")
    doc["c"] = 3
    doc["c"].trivia.trail = CRLF

    assert dumps(doc) == "a = 1\nb = 2\nc = 3\n"


def test_new_multiline_array_in_crlf_document_uses_crlf() -> None:
    from tomlkit import array

    doc = parse(f"a = 1{CRLF}")
    arr = array()
    arr.multiline(True)
    arr.extend([1, 2, 3])
    doc["b"] = arr

    rendered = dumps(doc)
    assert (
        rendered == f"a = 1{CRLF}b = [{CRLF}    1,{CRLF}    2,{CRLF}    3,{CRLF}]{CRLF}"
    )
    # re-parse and check the value
    assert parse(rendered)["b"] == [1, 2, 3]


def test_new_table_in_crlf_document_uses_crlf_separator() -> None:
    from tomlkit import table

    doc = parse(f"a = 1{CRLF}")
    section = table()
    section["x"] = 1
    doc["section"] = section

    rendered = dumps(doc)
    assert rendered == f"a = 1{CRLF}{CRLF}[section]{CRLF}x = 1{CRLF}"
    assert parse(rendered)["section"]["x"] == 1


def test_emptied_array_of_tables_fallback_uses_document_linesep() -> None:
    doc = parse(f"[[t]]{CRLF}x = 1{CRLF}[[t]]{CRLF}x = 2{CRLF}")
    elements = doc["t"]
    del elements[0]
    del elements[0]

    assert dumps(doc) == f"t = []{CRLF}"


def test_mixed_document_new_multiline_array_uses_library_default() -> None:
    from tomlkit import array

    doc = parse(f"a = 1{CRLF}b = 2{LF}")
    assert doc.linesep is None

    arr = array()
    arr.multiline(True)
    arr.extend([1])
    doc["c"] = arr

    rendered = dumps(doc)
    # existing lines keep their endings; the brand new structure uses LF
    assert rendered == f"a = 1{CRLF}b = 2{LF}c = [{LF}    1,{LF}]{LF}"


def test_render_context_does_not_leak_between_documents() -> None:
    from tomlkit import array

    crlf_doc = parse(f"a = 1{CRLF}")
    crlf_doc["b"] = array().multiline(True)
    crlf_doc["b"].extend([1])

    lf_doc = parse("a = 1\n")
    lf_doc["b"] = array().multiline(True)
    lf_doc["b"].extend([1])

    crlf_rendered = dumps(crlf_doc)
    lf_rendered = dumps(lf_doc)
    # rendering the CRLF document first must not switch the LF document
    assert crlf_rendered == f"a = 1{CRLF}b = [{CRLF}    1,{CRLF}]{CRLF}"
    assert lf_rendered == "a = 1\nb = [\n    1,\n]\n"
    # and a second render still works
    assert dumps(crlf_doc) == crlf_rendered


def test_lf_document_with_parsed_multiline_array_round_trips() -> None:
    source = "a = [\n  1,\n  2,\n]\nb = 2\n"
    doc = parse(source)
    doc["a"].append(3)

    rendered = dumps(doc)
    assert "\r" not in rendered
    assert parse(rendered)["a"] == [1, 2, 3]


def test_crlf_document_pickle_and_copy_round_trip(tmp_path: Path) -> None:
    import copy
    import pickle

    source = f"a = 1{CRLF}b = 2{CRLF}"
    path = tmp_path / "doc.toml"
    path.write_bytes(source.encode())
    doc = TOMLFile(path).read()
    doc["c"] = 3

    expected = f"a = 1{CRLF}b = 2{CRLF}c = 3{CRLF}"
    assert dumps(pickle.loads(pickle.dumps(doc))) == expected
    assert dumps(copy.copy(doc)) == expected
    assert dumps(copy.deepcopy(doc)) == expected


def test_dotted_keys_in_inline_table_keep_crlf_convention() -> None:
    # A dotted key inside an inline table is stored as a nested super Table
    # whose trivia trails must be converted like any other structural text;
    # the inline-table renderer also strips those trails without leaving a
    # bare CR behind.
    source = (
        f"[[arr]]{CRLF}"
        f"t = {{a.b=1}}{CRLF}"
        f"T = {{a.b=1}}{CRLF}"
        f"{CRLF}"
        f"[[arr]]{CRLF}"
        f"t = {{a.b=2}}{CRLF}"
        f"T = {{a.b=2}}{CRLF}"
    )
    doc = parse(source)

    assert dumps(doc) == source
    assert parse(dumps(doc))["arr"][0]["t"]["a"]["b"] == 1


def test_multiline_inline_table_keeps_crlf_convention() -> None:
    source = f"a = {{{CRLF} x = 1,{CRLF} y = 2,{CRLF}}}{CRLF}"
    doc = parse(source)

    rendered = dumps(doc)
    assert rendered == source
    # no bare LF may survive in an all-CRLF document
    assert "\n" not in rendered.replace(CRLF, "")
