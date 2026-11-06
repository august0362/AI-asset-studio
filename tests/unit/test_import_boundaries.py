"""Module boundaries (ARCHITECTURE §1.1): models and kaggle_connector never import each other or interface."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STDLIB = set(sys.stdlib_module_names)
FIRST_PARTY = {"models", "kaggle_connector", "aas_backend", "interface", "tests"}

ALLOWED_THIRD_PARTY = {
    "models": {"pydantic", "PIL"},
    "kaggle_connector": {"pydantic"},
    "kaggle_connector/runtime": {"psutil", "pynvml"},  # runs in the notebook: stdlib + optional metrics libs
    "models/adapters/remote": {"PIL"},  # remote entrypoints: stdlib + Pillow only
}
FORBIDDEN_FIRST_PARTY = {
    "models": {"kaggle_connector", "aas_backend", "interface"},
    "kaggle_connector": {"models", "aas_backend", "interface"},
}


def top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def files(package: str) -> list[Path]:
    return sorted((ROOT / package).rglob("*.py"))


@pytest.mark.parametrize("package", ["models", "kaggle_connector"])
def test_no_forbidden_first_party_imports(package):
    for path in files(package):
        bad = top_level_imports(path) & FORBIDDEN_FIRST_PARTY[package]
        assert not bad, f"{path.relative_to(ROOT)} imports {bad}"


@pytest.mark.parametrize("package", ["models", "kaggle_connector"])
def test_only_allowed_third_party_dependencies(package):
    for path in files(package):
        allowed = ALLOWED_THIRD_PARTY[package]
        if "runtime" in path.parts:
            allowed = ALLOWED_THIRD_PARTY["kaggle_connector/runtime"]
        third_party = top_level_imports(path) - STDLIB - FIRST_PARTY
        assert third_party <= allowed, f"{path.relative_to(ROOT)} uses {third_party - allowed}"


def test_notebook_runner_and_remote_entrypoints_are_self_contained():
    runner = ROOT / "kaggle_connector" / "runtime" / "runner.py"
    assert top_level_imports(runner) - STDLIB <= ALLOWED_THIRD_PARTY["kaggle_connector/runtime"]
    for entry in (ROOT / "models" / "adapters").rglob("remote_entry.py"):
        tree = ast.parse(entry.read_text(encoding="utf-8"))
        assert not any(isinstance(n, ast.ImportFrom) and n.level > 0 for n in ast.walk(tree)), entry
        assert top_level_imports(entry) - STDLIB <= ALLOWED_THIRD_PARTY["models/adapters/remote"], entry


def test_backend_never_runs_the_kaggle_cli_directly():
    for path in files("interface/backend"):
        source = path.read_text(encoding="utf-8")
        assert "subprocess" not in source, (
            f"{path.relative_to(ROOT)} must leave CLI calls to kaggle_connector"
        )
