"""Tests for the CLI entry point (cli/analyze.py)."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLI_PATH = ROOT / "cli" / "analyze.py"


def _load_cli():
    """Load cli/analyze.py as a module (it is not an importable package)."""
    spec = importlib.util.spec_from_file_location("_cli_analyze", CLI_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCliModule:
    def test_module_imports_cleanly(self):
        mod = _load_cli()
        assert hasattr(mod, "main")
        assert hasattr(mod, "_run_web")
        assert hasattr(mod, "_run_local")

    def test_run_web_does_not_reference_undefined_urllib(self):
        """M-3 regression: the browser-open probe used `urllib.request.urlopen`
        but only `urllib.request as urlreq` was imported, so the bare `urllib`
        name was undefined. The resulting NameError was swallowed by a broad
        `except Exception`, silently making the browser-open path dead code.

        Guard the exact broken token so the alias must stay consistent.
        """
        src = CLI_PATH.read_text(encoding="utf-8")
        assert "urllib.request.urlopen" not in src, (
            "bare urllib.request.urlopen is undefined here — use the urlreq alias"
        )

    def test_run_web_code_has_no_bare_urllib_global(self):
        """Complementary check at the bytecode level: _run_web must not reference
        a bare `urllib` global (which would raise NameError at runtime)."""
        mod = _load_cli()
        assert "urllib" not in mod._run_web.__code__.co_names
