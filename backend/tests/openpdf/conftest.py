from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WORKER_ROOT = ROOT / "workers" / "openpdf"
WORKER_JAR = WORKER_ROOT / "target" / "claros-openpdf-worker-0.1.0-SNAPSHOT-all.jar"


@pytest.fixture(scope="session")
def openpdf_worker_jar() -> Path:
    java = shutil.which("java")
    maven = shutil.which("mvn")
    if not java or not maven:
        pytest.skip("Java 21 and Maven are required for OpenPDF integration tests")
    sources = tuple((WORKER_ROOT / "src").rglob("*.java"))
    if not WORKER_JAR.is_file() or any(
        source.stat().st_mtime > WORKER_JAR.stat().st_mtime for source in sources
    ):
        result = subprocess.run(  # noqa: S603
            [maven, "-q", "-f", str(WORKER_ROOT / "pom.xml"), "package", "-DskipTests"],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
        assert result.returncode == 0, result.stdout.decode("utf-8", errors="replace")
    return WORKER_JAR


@pytest.fixture(scope="session")
def qpdf_executable() -> Path:
    configured = os.environ.get("CLAROS_TEST_QPDF_PATH")
    found = configured or shutil.which("qpdf")
    if not found or not Path(found).is_file():
        pytest.skip("qpdf is required for OpenPDF integration tests")
    return Path(found).resolve()
