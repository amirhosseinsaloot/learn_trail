"""Smoke test: the package imports under the configured toolchain."""

import nuroli


def test_package_imports() -> None:
    assert nuroli.__name__ == "nuroli"
