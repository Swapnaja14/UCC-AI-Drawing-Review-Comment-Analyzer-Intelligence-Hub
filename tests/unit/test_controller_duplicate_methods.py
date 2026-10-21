"""
A0 regression guard: AppController must not shadow its own methods.

Python keeps only the last definition when a class body defines the same name
twice, so earlier copies are dead code that silently diverges from the live one.
"""
import ast
from collections import Counter
from pathlib import Path

import pytest

CONTROLLER_PATH = Path(__file__).resolve().parents[2] / "app" / "controllers" / "app_controller.py"


def _method_name_counts(class_name: str = "AppController") -> Counter:
    tree = ast.parse(CONTROLLER_PATH.read_text(encoding="utf-8"))
    cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    names = [
        node.name for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return Counter(names)


def test_no_duplicate_method_definitions_in_app_controller():
    duplicates = {
        name: count
        for name, count in _method_name_counts().items()
        if count > 1 and not _is_property_setter_pair(name)
    }
    assert not duplicates, f"AppController defines these methods more than once: {duplicates}"


def _is_property_setter_pair(name: str) -> bool:
    """A name defined twice is legitimate when the second is a @<name>.setter."""
    tree = ast.parse(CONTROLLER_PATH.read_text(encoding="utf-8"))
    cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AppController"
    )
    setter_decorated = set()
    for node in cls.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Attribute)
                and dec.attr == "setter"
                and isinstance(dec.value, ast.Name)
            ):
                setter_decorated.add(dec.value.id)
    return name in setter_decorated


@pytest.mark.parametrize(
    "method_name",
    [
        "get_all_departments",
        "get_all_drawings",
        "get_all_categories",
        "get_all_projects",
        "export_data",
    ],
)
def test_previously_duplicated_methods_now_unique(method_name):
    assert _method_name_counts()[method_name] == 1


def test_current_project_id_is_a_property_with_setter():
    """current_project_id legitimately appears twice: getter plus setter."""
    counts = _method_name_counts()
    assert counts["current_project_id"] == 2
    assert _is_property_setter_pair("current_project_id")
