"""Tests for backend.analyzer.dependencies — import parsing and graph building."""
import ast
import pytest
from pathlib import Path

from backend.analyzer.dependencies import (
    parse_imports,
    _module_id,
    build_dependency_graph,
    graph_to_json,
)


class TestParseImports:
    def test_simple_import(self):
        assert "os" in parse_imports("import os")

    def test_from_import(self):
        assert "pathlib" in parse_imports("from pathlib import Path")

    def test_dotted_import(self):
        assert "os.path" in parse_imports("import os.path")

    def test_multiple_imports(self):
        src = "import os\nimport sys\nfrom pathlib import Path"
        result = parse_imports(src)
        assert "os" in result
        assert "sys" in result
        assert "pathlib" in result

    def test_relative_import_no_module_id_no_crash(self):
        # Without module_id we can't resolve — should return empty, not crash
        result = parse_imports("from . import sibling")
        assert isinstance(result, list)
        assert "sibling" not in result  # can't resolve without context

    def test_relative_import_same_package(self):
        # from . import sibling  in  backend.api.main  →  backend.api.sibling
        result = parse_imports("from . import sibling", module_id="backend.api.main")
        assert "backend.api.sibling" in result

    def test_relative_import_with_module(self):
        # from .utils import helper  in  backend.api.main  →  backend.api.utils
        result = parse_imports("from .utils import helper", module_id="backend.api.main")
        assert "backend.api.utils" in result

    def test_relative_import_parent_package(self):
        # from ..analyzer import core  in  backend.api.main  →  backend.analyzer
        result = parse_imports("from ..analyzer import core", module_id="backend.api.main")
        assert "backend.analyzer" in result

    def test_relative_import_grandparent(self):
        # from .. import something  in  a.b.c  →  a.something
        result = parse_imports("from .. import something", module_id="a.b.c")
        assert "a.something" in result

    def test_relative_import_multiple_names(self):
        # from . import foo, bar  →  pkg.foo, pkg.bar
        result = parse_imports("from . import foo, bar", module_id="pkg.module")
        assert "pkg.foo" in result
        assert "pkg.bar" in result

    def test_syntax_error_returns_empty(self):
        assert parse_imports("def foo(: ...") == []

    def test_empty_source_returns_empty(self):
        assert parse_imports("") == []

    def test_uses_provided_tree(self):
        src = "import json"
        tree = ast.parse(src)
        result = parse_imports(src, tree=tree)
        assert "json" in result

    def test_no_imports_returns_empty(self):
        assert parse_imports("x = 1\ny = 2") == []


class TestModuleId:
    def test_simple_file(self, tmp_path):
        f = tmp_path / "mymodule.py"
        assert _module_id(f, tmp_path) == "mymodule"

    def test_nested_file(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        f = pkg / "mod.py"
        assert _module_id(f, tmp_path) == "pkg.mod"

    def test_init_file_drops_init(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        f = pkg / "__init__.py"
        assert _module_id(f, tmp_path) == "pkg"

    def test_deeply_nested(self, tmp_path):
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        f = deep / "c.py"
        assert _module_id(f, tmp_path) == "a.b.c"


class TestBuildDependencyGraph:
    def test_empty_inputs(self, tmp_path):
        G, cycles = build_dependency_graph([], tmp_path, {})
        assert len(G.nodes) == 0
        assert cycles == []

    def test_nodes_created_for_all_files(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("")
        b.write_text("")
        imports_map = {"a": [], "b": []}
        G, cycles = build_dependency_graph([a, b], tmp_path, imports_map)
        assert G.has_node("a")
        assert G.has_node("b")

    def test_edge_created_for_import(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("import b")
        b.write_text("")
        imports_map = {"a": ["b"], "b": []}
        G, _ = build_dependency_graph([a, b], tmp_path, imports_map)
        assert G.has_edge("a", "b")

    def test_no_cycles_detected_for_dag(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("")
        b.write_text("")
        imports_map = {"a": ["b"], "b": []}
        _, cycles = build_dependency_graph([a, b], tmp_path, imports_map)
        assert cycles == []

    def test_cycle_detected(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("")
        b.write_text("")
        imports_map = {"a": ["b"], "b": ["a"]}
        _, cycles = build_dependency_graph([a, b], tmp_path, imports_map)
        assert len(cycles) > 0

    def test_stdlib_import_classified(self, tmp_path):
        a = tmp_path / "a.py"
        a.write_text("import os")
        imports_map = {"a": ["os"]}
        G, _ = build_dependency_graph([a], tmp_path, imports_map)
        assert G.nodes["os"]["kind"] == "stdlib"


class TestGraphToJson:
    def test_output_has_required_keys(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("")
        b.write_text("")
        G, cycles = build_dependency_graph([a, b], tmp_path, {"a": ["b"], "b": []})
        result = graph_to_json(G, cycles)
        assert "nodes" in result
        assert "edges" in result
        assert "cycles" in result

    def test_nodes_have_id_and_kind(self, tmp_path):
        a = tmp_path / "a.py"
        a.write_text("")
        G, cycles = build_dependency_graph([a], tmp_path, {"a": []})
        result = graph_to_json(G, cycles)
        for node in result["nodes"]:
            assert "id" in node
            assert "kind" in node

    def test_cycle_nodes_flagged(self, tmp_path):
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("")
        b.write_text("")
        G, cycles = build_dependency_graph([a, b], tmp_path, {"a": ["b"], "b": ["a"]})
        result = graph_to_json(G, cycles)
        cycle_node_ids = {n["id"] for n in result["nodes"] if n.get("in_cycle")}
        assert "a" in cycle_node_ids
        assert "b" in cycle_node_ids

    def test_risk_map_applied_to_nodes(self, tmp_path):
        a = tmp_path / "a.py"
        a.write_text("")
        G, cycles = build_dependency_graph([a], tmp_path, {"a": []})
        result = graph_to_json(G, cycles, risk_map={"a": 75.0})
        a_node = next(n for n in result["nodes"] if n["id"] == "a")
        assert a_node["risk"] == 75.0
