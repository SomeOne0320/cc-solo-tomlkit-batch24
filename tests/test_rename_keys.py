from __future__ import annotations

import copy

from typing import Any

import pytest

import tomlkit

from tomlkit import parse
from tomlkit.container import OutOfOrderTableProxy
from tomlkit.exceptions import KeyAlreadyPresent
from tomlkit.exceptions import NonExistentKey


DEPLOYMENT = """\
# Deployment settings
title = "deploy"
env.name = "prod"
env.region = "eu-west-1"
[logging]
level = "info"
[env.limits]
cpu = 2
memory = "4Gi"
[[workers]]
name = "api"
[env.limits.network]
ingress = "open"
[logging.handlers]
file = "/var/log/app.log"
"""


def test_rename_a_group_defined_by_dotted_keys_and_a_later_header() -> None:
    # ``env`` starts as dotted keys at the top, is interrupted by ``[logging]``
    # and picks up again in ``[env.limits]``, separated from the first part by
    # ``[[workers]]`` as well.
    doc = parse(DEPLOYMENT)

    doc.rename_keys({"env": "environment"})

    assert doc.as_string() == DEPLOYMENT.replace("env.", "environment.").replace(
        "[env.", "[environment."
    )
    assert doc.unwrap()["environment"]["limits"]["network"] == {"ingress": "open"}
    assert "env" not in doc
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_rename_a_key_inside_a_nested_group() -> None:
    doc = parse(DEPLOYMENT)
    doc["logging"].rename_keys({"level": "severity"})

    assert doc.as_string() == DEPLOYMENT.replace('level = "info"', 'severity = "info"')
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_swap_two_keys_at_the_same_level() -> None:
    doc = parse('[a]\nx = "first"\n[b]\ny = "second"\n')

    doc.rename_keys({"a": "b", "b": "a"})

    assert doc.as_string() == '[b]\nx = "first"\n[a]\ny = "second"\n'
    assert doc.unwrap() == {"b": {"x": "first"}, "a": {"y": "second"}}
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_swap_a_split_group_with_another_key() -> None:
    content = "a.one = 1\na.two = 2\n[x]\ny = 3\n"
    doc = parse(content)

    doc.rename_keys({"a": "x", "x": "a"})

    assert doc.as_string() == "x.one = 1\nx.two = 2\n[a]\ny = 3\n"
    assert doc.unwrap() == {"x": {"one": 1, "two": 2}, "a": {"y": 3}}
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_longer_chain_uses_the_original_values() -> None:
    doc = parse("a = 1\nb = 2\nc = 3\n")

    doc.rename_keys({"a": "b", "b": "c", "c": "d"})

    assert doc.as_string() == "b = 1\nc = 2\nd = 3\n"
    assert doc.unwrap() == {"b": 1, "c": 2, "d": 3}


@pytest.mark.parametrize("key", ["a.b", "a b", "雪", ""])
def test_names_are_literal_and_quoted_when_needed(key: str) -> None:
    doc = parse('a = 1\n"a.b" = 2\n')

    doc.rename_keys({"a.b": key})

    assert doc.unwrap() == {"a": 1, key: 2}
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_quoted_old_name_matches_its_literal_value() -> None:
    doc = parse('"a.b" = 1\n')

    doc.rename_keys({"a.b": "c.d"})

    assert doc.as_string() == '"c.d" = 1\n'
    assert doc.unwrap() == {"c.d": 1}


def test_comments_whitespace_and_order_are_kept() -> None:
    content = (
        '# leading\nbefore  =  1  # keep\n  "old name"  =  2 # also keep\nafter = 3\n'
    )
    doc = parse(content)

    doc.rename_keys({"old name": "new"})

    assert doc.as_string() == (
        '# leading\nbefore  =  1  # keep\n  "new"  =  2 # also keep\nafter = 3\n'
    )
    assert list(doc) == ["before", "new", "after"]


def test_header_text_keeps_its_style() -> None:
    doc = parse('[ a . "b.c" ]  # comment\nx = 1\n')

    doc.rename_keys({"a": "z"})

    assert doc.as_string() == '[ z . "b.c" ]  # comment\nx = 1\n'


def test_only_the_renamed_header_component_changes() -> None:
    content = "[a]\nx = 1\n[a.b]\ny = 2\n[a.bc]\nz = 3\n"
    doc = parse(content)

    doc["a"].rename_keys({"b": "d"})

    assert doc.as_string() == "[a]\nx = 1\n[a.d]\ny = 2\n[a.bc]\nz = 3\n"
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_renaming_an_array_of_tables_updates_every_header() -> None:
    content = '[[fruit]]\nname = "apple"\n[fruit.physical]\ncolor = "red"\n'

    doc = parse(content)

    doc.rename_keys({"fruit": "fruits"})

    assert doc.as_string() == content.replace("fruit", "fruits")
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_missing_old_name_leaves_the_document_untouched() -> None:
    doc = parse("a = 1\nb = 2\n")

    with pytest.raises(NonExistentKey):
        doc.rename_keys({"a": "c", "missing": "d"})

    assert doc.as_string() == "a = 1\nb = 2\n"
    assert doc.unwrap() == {"a": 1, "b": 2}


def test_destination_used_twice_leaves_the_document_untouched() -> None:
    doc = parse("a = 1\nb = 2\n")

    with pytest.raises(KeyAlreadyPresent):
        doc.rename_keys({"a": "c", "b": "c"})

    assert doc.as_string() == "a = 1\nb = 2\n"


def test_destination_that_stays_put_aborts_the_whole_call() -> None:
    doc = parse("[a]\nx = 1\n[b.p]\ny = 2\n[c]\n[b.q]\nz = 3\n")

    with pytest.raises(KeyAlreadyPresent):
        doc.rename_keys({"a": "b"})

    assert doc.as_string() == "[a]\nx = 1\n[b.p]\ny = 2\n[c]\n[b.q]\nz = 3\n"


def test_renaming_a_split_table_moves_all_its_parts() -> None:
    # ``a`` is split over three places; renaming it has to rename the dotted
    # key and both headers together, and the document must still parse back
    # with the values under the new name.
    content = "a.one = 1\n[x]\ny = 2\n[a.two]\nz = 3\n"
    doc = parse(content)

    doc.rename_keys({"a": "b"})

    assert doc.as_string() == "b.one = 1\n[x]\ny = 2\n[b.two]\nz = 3\n"
    assert doc.unwrap() == {"b": {"one": 1, "two": {"z": 3}}, "x": {"y": 2}}
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_renamed_split_table_can_still_be_appended_to() -> None:
    content = "[a]\nx = 1\n[a.b]\ny = 2\n[c]\n[a.bd]\nz = 3\n"
    doc = parse(content)

    doc.rename_keys({"a": "z"})
    doc["z"]["extra"] = 4

    assert doc.unwrap() == {
        "z": {"x": 1, "extra": 4, "b": {"y": 2}, "bd": {"z": 3}},
        "c": {},
    }
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_rename_inside_a_split_table() -> None:
    content = "a.one = 1\n[x]\ny = 2\n[a.two]\nz = 3\n"
    doc = parse(content)
    table = doc["a"]
    assert isinstance(table, OutOfOrderTableProxy)

    table.rename_keys({"one": "uno", "two": "dos"})

    assert doc.as_string() == "a.uno = 1\n[x]\ny = 2\n[a.dos]\nz = 3\n"
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_rename_inside_a_split_table_swap() -> None:
    content = "a.one = 1\n[x]\ny = 2\n[a.two]\nz = 3\n"
    doc = parse(content)

    doc["a"].rename_keys({"one": "two", "two": "one"})

    assert doc.as_string() == "a.two = 1\n[x]\ny = 2\n[a.one]\nz = 3\n"
    assert doc.unwrap() == {"a": {"two": 1, "one": {"z": 3}}, "x": {"y": 2}}
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_split_table_is_still_editable_after_renaming() -> None:
    doc = parse("a.one = 1\n[x]\ny = 2\n[a.two]\nz = 3\n")
    table = doc["a"]

    table.rename_keys({"one": "uno", "two": "dos"})
    table["three"] = 4
    del table["uno"]

    assert doc.unwrap() == {"a": {"three": 4, "dos": {"z": 3}}, "x": {"y": 2}}
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_programmatic_document_rename() -> None:
    doc = tomlkit.document()
    doc["first"] = 1
    doc["second"] = {"x": 2, "y": 3}

    doc.rename_keys({"first": "second", "second": "first"})

    assert doc.as_string() == "second = 1\n\n[first]\nx = 2\ny = 3\n"
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_inline_table_rename() -> None:
    doc = parse("t = {a = 1, b = 2}\n")

    doc["t"].rename_keys({"a": "b", "b": "a"})

    assert doc.as_string() == "t = {b = 1, a = 2}\n"
    assert doc.unwrap() == {"t": {"b": 1, "a": 2}}


@pytest.mark.parametrize(
    "start,path,mapping,expected",
    [
        ("a = 1\nb = 2\n", (), {"a": "a"}, "a = 1\nb = 2\n"),
        ("a = 1\n", (), {}, "a = 1\n"),
        ('"a" = 1\n', (), {"a": "b"}, '"b" = 1\n'),
        ("'a' = 1\n", (), {"a": "b"}, "'b' = 1\n"),
        ("[a]\nx = 1\n", ("a",), {"x": "y"}, "[a]\ny = 1\n"),
        (
            "[[a]]\nx = 1\n[b]\ny = 2\n",
            (),
            {"a": "b", "b": "a"},
            "[[b]]\nx = 1\n[a]\ny = 2\n",
        ),
    ],
)
def test_rename_round_trips(
    start: str, path: tuple[str, ...], mapping: dict[str, str], expected: str
) -> None:
    doc = parse(start)
    table: Any = doc
    for name in path:
        table = table[name]

    table.rename_keys(mapping)

    assert doc.as_string() == expected
    assert parse(doc.as_string()).unwrap() == doc.unwrap()


def test_rename_does_not_touch_other_documents() -> None:
    original = parse(DEPLOYMENT)
    doc = copy.deepcopy(original)

    doc.rename_keys({"env": "environment"})

    assert original.as_string() == DEPLOYMENT
    assert "environment" not in original
    assert "environment" in doc


def test_rename_in_a_real_config(example: Any) -> None:
    content = example("pyproject")
    doc = parse(content)

    doc["tool"]["poetry"].rename_keys({"dev-dependencies": "dev_dependencies"})

    assert doc.as_string() == content.replace(
        "[tool.poetry.dev-dependencies]", "[tool.poetry.dev_dependencies]"
    )
    assert doc.unwrap()["tool"]["poetry"]["dev_dependencies"]["pytest"] == "^3.4"
    assert parse(doc.as_string()).unwrap() == doc.unwrap()
