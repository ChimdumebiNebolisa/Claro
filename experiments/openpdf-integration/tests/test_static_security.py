# ruff: noqa: S101

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_container_spec_declares_intended_worker_restrictions() -> None:
    dockerfile = (ROOT / "worker" / "Dockerfile").read_text(encoding="utf-8")
    launcher = (ROOT / "scripts" / "run-worker-container.ps1").read_text(encoding="utf-8")
    assert "USER 10001:10001" in dockerfile
    assert "/opt/claros/fonts/NotoSans-Regular.ttf" in dockerfile
    assert "-Xmx192m" in dockerfile
    for control in (
        "--network none",
        "--read-only",
        "--cap-drop ALL",
        "no-new-privileges:true",
        "--pids-limit 64",
        "--memory 256m",
        "--cpus 1",
        "--user 10001:10001",
        "size=96m",
    ):
        assert control in launcher


def test_worker_uses_proven_text_configuration_and_has_no_fetch_or_html_path() -> None:
    worker = (ROOT / "src" / "main" / "java" / "org" / "claros" /
              "openpdfintegration" / "WorkerMain.java").read_text(encoding="utf-8")
    contract = (ROOT / "openpdf_integration" / "contract.py").read_text(encoding="utf-8")
    assert "setGlyphSubstitutionEnabled(false)" in worker
    assert "BaseFont.IDENTITY_H" in worker
    assert "BaseFont.EMBEDDED" in worker
    assert "new PdfStamper(reader, bounded, null, true)" in worker
    assert "reader.isRebuilt()" in worker
    forbidden = ("HttpClient", "URLConnection", "Jsoup", "XMLWorker", "file_path", "font_path")
    assert all(item not in worker for item in forbidden)
    assert all(item not in contract for item in ("url:", "html:", "shell:", "font_path:"))
