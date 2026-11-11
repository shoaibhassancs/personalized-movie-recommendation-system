"""Smoke test: the package is installed and importable."""

import pmrs


def test_package_imports_and_has_version() -> None:
    assert pmrs.__version__ == "0.1.0"
