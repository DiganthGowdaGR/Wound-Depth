"""Database entrypoint kept separate for application services and tests."""

from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent / "woundlens.db"
