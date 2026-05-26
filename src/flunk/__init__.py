"""flunk — a BS detector for AI-built Python code."""

from flunk.cli import app

__all__ = ["app", "main"]


def main() -> None:
    """Entry point for the `flunk` script (declared in pyproject.toml)."""
    app()
