"""
Phase 0 — Smoke test to verify the project setup is working.
Run with: pytest tests/ -v

If this test passes, your Python environment is correctly configured.
"""


def test_python_setup():
    """Verify Python can import core dependencies."""
    import fastapi
    import pydantic
    import pandas
    import numpy

    assert fastapi.__version__ is not None
    assert pydantic.__version__ is not None
    assert pandas.__version__ is not None
    assert numpy.__version__ is not None


def test_engine_import():
    """Verify the engine package is importable."""
    import engine

    assert engine is not None
