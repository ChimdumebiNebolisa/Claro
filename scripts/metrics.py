#!/usr/bin/env python3
"""
Claros metrics script: print counts for resume bullet points.
Run from project root: python scripts/metrics.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BACKEND_FILES = ["main.py", "parser.py", "exporter.py", "agent.py"]


def backend_loc() -> int:
    """Count lines (non-empty, excluding pure comment lines) in backend Python modules."""
    total = 0
    for name in BACKEND_FILES:
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            total += 1
    return total


def api_route_count() -> int:
    """Count FastAPI route decorators in main.py."""
    path = ROOT / "main.py"
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    return len(re.findall(r"@app\.(get|post|put|delete|patch)\s*\(", text))


def test_assignment_questions() -> int:
    """Infer number of questions in test assignment from generate_test_pdf.py or test_assignment.py."""
    for name in ["generate_test_pdf.py", "test_assignment.py"]:
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        matches = re.findall(r"Question\s+(\d+)\s*:", text)
        if matches:
            return len(matches)
        # Numbered list format: "1.", "2." in paragraph content
        numbered = re.findall(r"<b>(\d+)\.</b>", text)
        if numbered:
            return len(numbered)
    return 0


def test_count() -> int | None:
    """Run pytest --collect-only and parse test count. Returns None if pytest fails."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # e.g. "15 tests collected" or "15 tests collected in 0.05s"
        match = re.search(r"(\d+)\s+test", result.stdout + result.stderr)
        return int(match.group(1)) if match else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def coverage_pct() -> float | None:
    """Run pytest with coverage and return TOTAL coverage percentage. Returns None if fails."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_parser.py",
                "tests/test_exporter.py",
                "tests/test_agent.py",
                "--cov=parser",
                "--cov=exporter",
                "--cov=agent",
                "--cov-report=term",
                "--no-cov-on-fail",
                "-q",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Last line of stdout often has "TOTAL ... XX%"
        for line in (result.stdout or "").splitlines():
            if "TOTAL" in line:
                match = re.search(r"(\d+)%", line)
                if match:
                    return float(match.group(1))
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def main() -> None:
    import json as _json
    use_json = "--json" in sys.argv
    with_tests = "--with-tests" in sys.argv

    loc = backend_loc()
    routes = api_route_count()
    questions = test_assignment_questions()
    tests = test_count() if with_tests else None
    cov = coverage_pct() if with_tests else None

    if use_json:
        out = {
            "backend_loc": loc,
            "api_routes": routes,
            "test_assignment_questions": questions,
            "test_count": tests,
            "coverage_pct": cov,
        }
        print(_json.dumps(out, indent=2))
        return

    print("Claros metrics")
    print("  Backend LOC (code):", loc)
    print("  API routes:         ", routes)
    print("  Test assignment:    ", questions, "questions")
    if with_tests:
        print("  Tests:              ", tests if tests is not None else "—")
        print("  Coverage:           ", f"{cov}%" if cov is not None else "—")
    else:
        print("  (Use --with-tests to include test count and coverage)")


if __name__ == "__main__":
    main()
