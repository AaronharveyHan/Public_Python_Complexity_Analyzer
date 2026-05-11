"""
Import dependency analysis.

Builds a directed graph (module → imported module) from AST import nodes.
Detects cycles using networkx.
Only project-internal imports are used for cycle detection; all imports
are recorded for visualization.
"""
from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path
from typing import List, Dict, Tuple, Set

import networkx as nx


STDLIB_TOP = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()

# common third-party roots to recognise (heuristic)
_THIRD_PARTY_HINTS = {
    "openai", "anthropic", "fastapi", "uvicorn", "pydantic",
    "networkx", "radon", "requests", "numpy", "pandas", "flask",
    "django", "sqlalchemy", "celery", "redis", "pytest",
    "aiofiles", "aiohttp", "httpx", "click", "rich",
}


def _is_stdlib(name: str) -> bool:
    root = name.split(".")[0]
    return root in STDLIB_TOP


def _is_third_party(name: str) -> bool:
    root = name.split(".")[0]
    return root in _THIRD_PARTY_HINTS


def _resolve_relative(
    level: int,
    module: str | None,
    names: list[str],
    importer_id: str,
) -> list[str]:
    """Resolve a relative import to absolute module IDs.

    For ``from .utils import foo`` (level=1, module="utils") in package
    ``backend.api.main`` → ``backend.api.utils``.

    For ``from . import foo`` (level=1, module=None) → ``backend.api.foo``
    (each name is treated as a sibling sub-module).
    """
    parts = importer_id.split(".")
    # Package = all components except the module leaf.
    package_parts = parts[:-1]
    # Each extra dot (beyond the first) goes one step higher.
    n_up = level - 1
    if n_up >= len(package_parts):
        base_parts: list[str] = []
    else:
        base_parts = package_parts[: len(package_parts) - n_up]

    if module:
        resolved = ".".join(base_parts + [module]) if base_parts else module
        return [resolved]
    # ``from . import foo, bar`` — treat each name as a sibling sub-module.
    if base_parts:
        return [".".join(base_parts + [n]) for n in names]
    return list(names)


class _ImportCollector(ast.NodeVisitor):
    """Collect all imported names from a module."""

    def __init__(self, module_id: str = "") -> None:
        self.imports: list[str] = []
        self._module_id = module_id

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level and node.level > 0:
            if self._module_id:
                names = [alias.name for alias in node.names]
                self.imports.extend(
                    _resolve_relative(node.level, node.module, names, self._module_id)
                )
            # Without module_id we can't resolve — skip rather than emit garbage.
        elif node.module:
            self.imports.append(node.module)


def parse_imports(
    source: str,
    tree: ast.AST | None = None,
    module_id: str = "",
) -> list[str]:
    """Return list of all import names in *source* (may contain dots).

    If *tree* is provided (pre-parsed AST) it is used directly, saving a
    redundant ``ast.parse`` call when the caller already holds the tree.
    Pass *module_id* (dotted module name, e.g. ``backend.api.main``) to
    resolve relative imports such as ``from . import sibling``.
    """
    if tree is None:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
    collector = _ImportCollector(module_id)
    collector.visit(tree)
    return collector.imports


def _module_id(py_path: Path, root: Path) -> str:
    """Convert a file path to a dotted module id relative to *root*."""
    try:
        rel = py_path.relative_to(root)
    except ValueError:
        rel = py_path
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else py_path.stem


def build_dependency_graph(
    files: List[Path],
    project_root: Path,
    imports_map: Dict[str, List[str]],
) -> Tuple[nx.DiGraph, List[List[str]]]:
    """
    Build a directed graph and detect cycles.

    Parameters
    ----------
    files        : all .py files in the project
    project_root : root directory
    imports_map  : {module_id: [imported_names, ...]}

    Returns
    -------
    graph  : DiGraph (nodes = all unique modules/packages imported)
    cycles : list of cycles (each cycle = list of node ids)
    """
    # Map from module_id to its file path
    module_ids: Dict[str, Path] = {
        _module_id(f, project_root): f for f in files
    }
    # Stem → module_id for fuzzy matching, but only for *unambiguous* stems.
    # If two modules share the same leaf name (e.g. backend.utils and cli.utils)
    # a stem lookup would silently resolve to whichever was inserted last, so
    # we exclude ambiguous stems entirely and fall back to stdlib/third-party.
    stem_counts: Counter[str] = Counter(
        mid.split(".")[-1] for mid in module_ids if mid
    )
    stem_map: Dict[str, str] = {
        mid.split(".")[-1]: mid
        for mid in module_ids
        if mid and stem_counts[mid.split(".")[-1]] == 1
    }

    G = nx.DiGraph()

    # Add all project modules as nodes
    for mid in module_ids:
        G.add_node(mid, kind="project", path=str(module_ids[mid]))

    for mid, imported_list in imports_map.items():
        G.add_node(mid, kind="project", path=str(module_ids.get(mid, "")))
        for imp in imported_list:
            root_imp = imp.split(".")[0]

            # Resolve to project module?
            if imp in module_ids:
                target = imp
                kind   = "project"
            elif root_imp in stem_map:
                target = stem_map[root_imp]
                kind   = "project"
            elif _is_stdlib(imp):
                target = root_imp
                kind   = "stdlib"
            elif _is_third_party(imp):
                target = root_imp
                kind   = "third_party"
            else:
                target = root_imp
                kind   = "unknown"

            if not G.has_node(target):
                G.add_node(target, kind=kind, path="")
            G.add_edge(mid, target)

    # Cycle detection (only within project nodes)
    project_nodes = {n for n, d in G.nodes(data=True) if d.get("kind") == "project"}
    subgraph = G.subgraph(project_nodes)
    try:
        cycles = list(nx.simple_cycles(subgraph))
    except Exception:
        cycles = []

    return G, cycles


def graph_to_json(
    G: nx.DiGraph,
    cycles: List[List[str]],
    risk_map: Dict[str, float] | None = None,
) -> dict:
    """Serialize graph for the frontend (ECharts-compatible structure)."""
    cycle_nodes: Set[str] = set()
    cycle_edges: Set[Tuple[str, str]] = set()
    for cycle in cycles:
        for n in cycle:
            cycle_nodes.add(n)
        for i in range(len(cycle)):
            cycle_edges.add((cycle[i], cycle[(i + 1) % len(cycle)]))

    nodes = []
    for node, data in G.nodes(data=True):
        nodes.append({
            "id":   node,
            "name": node,
            "kind": data.get("kind", "unknown"),
            "risk": risk_map.get(node, 0) if risk_map else 0,
            "in_cycle": node in cycle_nodes,
        })

    edges = []
    for src, dst in G.edges():
        edges.append({
            "source":   src,
            "target":   dst,
            "in_cycle": (src, dst) in cycle_edges,
        })

    return {
        "nodes":  nodes,
        "edges":  edges,
        "cycles": cycles,
    }
