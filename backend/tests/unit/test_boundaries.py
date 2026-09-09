"""import-linter enforces the layer rules from IMPLEMENTATION.md section 2.3."""

import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
LINT_IMPORTS = Path(sys.executable).with_name("lint-imports")
PROBE = BACKEND_DIR / "src" / "nuroli" / "conversations" / "domain" / "_boundary_probe.py"


def run_lint_imports() -> subprocess.CompletedProcess[str]:
    # Fixed executable from the active virtualenv; no user input reaches the command.
    return subprocess.run(  # noqa: S603
        [str(LINT_IMPORTS)], cwd=BACKEND_DIR, capture_output=True, text=True, check=False
    )


def test_clean_tree_satisfies_every_contract() -> None:
    result = run_lint_imports()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Contracts: 8 kept, 0 broken" in result.stdout


def test_domain_importing_another_modules_infrastructure_fails_lint() -> None:
    PROBE.write_text("from nuroli.identity.infrastructure import x  # noqa: F401\n")
    try:
        result = run_lint_imports()
    finally:
        PROBE.unlink()
    assert result.returncode != 0
    assert "domain imports only the standard library" in result.stdout
    assert "identity internals are private to identity" in result.stdout
    assert "BROKEN" in result.stdout
