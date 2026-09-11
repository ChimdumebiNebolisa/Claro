# ruff: noqa: S101

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EXPERIMENT_ROOT.parents[1]
sys.path.insert(0, str(EXPERIMENT_ROOT))
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="session", autouse=True)
def built_worker() -> None:
    java = shutil.which("java")
    maven = shutil.which("mvn")
    node = shutil.which("node")
    if not java or not maven or not node:
        pytest.skip("Java 21, Maven, and Node are required for the integration spike")
    jar = EXPERIMENT_ROOT / "target" / "openpdf-integration-0.1.0-SNAPSHOT-all.jar"
    java_sources = tuple((EXPERIMENT_ROOT / "src").rglob("*.java"))
    if jar.is_file() and all(path.stat().st_mtime <= jar.stat().st_mtime for path in java_sources):
        return
    result = subprocess.run(  # noqa: S603
        [maven, "-q", "package", "-DskipTests"],
        cwd=EXPERIMENT_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout.decode("utf-8", errors="replace")
