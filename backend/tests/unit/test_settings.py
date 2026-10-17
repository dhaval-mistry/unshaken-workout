"""Configuration failures must never echo supplied credentials during application bootstrap."""

import os
import subprocess
import sys
from pathlib import Path


def test_malformed_database_url_does_not_appear_in_process_output() -> None:
    secret = "startup-credential-must-not-appear"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"postgresql+asyncpg://user:{secret}@"
    environment["PYTHONPATH"] = str(Path(__file__).parents[2])

    result = subprocess.run(
        [sys.executable, "-c", "from app.main import app; print(app.title)"],
        cwd=Path(__file__).parents[2],
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert "Unshaken API" in result.stdout
