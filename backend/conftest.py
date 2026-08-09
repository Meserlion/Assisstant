"""Ensures the backend package root is importable when pytest is invoked as a bare
`pytest` from the backend/ directory (CI runs `pytest -q`, not `python -m pytest`,
so the cwd is not automatically added to sys.path). pytest inserts the directory
containing this conftest.py onto sys.path, which makes `config`, `main`, etc. importable.
"""
