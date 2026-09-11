# ruff: noqa: S607

"""Privacy-safe failure worker for process-boundary injection tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    mode = sys.argv[1]
    root = Path(sys.argv[2])
    if mode == "crash":
        return 17
    if mode == "timeout":
        time.sleep(30)
        return 0
    if mode == "malformed":
        (root / "worker-status.json").write_bytes(b"{malformed")
        return 0
    job = json.loads((root / "job.json").read_text(encoding="utf-8"))
    if mode in {"wrong-coordinate", "wrong-text", "mutate-contract"}:
        original = (root / "job.json").read_bytes()
        if mode == "wrong-coordinate":
            job["answers"][0]["lines"][0]["x_mpt"] += 50_000
        elif mode == "wrong-text":
            wrong = "ofce"
            job["answers"][0]["committed_text"] = wrong
            job["answers"][0]["committed_text_sha256"] = hashlib.sha256(wrong.encode()).hexdigest()
            job["answers"][0]["lines"] = [{
                **job["answers"][0]["lines"][0],
                "text": wrong,
                "separator_after": "",
            }]
        else:
            job["source"]["evidence_version"] = "attacker-mutated"
        (root / "job.json").chmod(0o600)
        (root / "job.json").write_text(
            json.dumps(job, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        if mode == "mutate-contract":
            return 0
        experiment = Path(__file__).resolve().parents[2]
        completed = subprocess.run(  # noqa: S603
            [
                "java",
                "-Xmx192m",
                "-jar",
                str(experiment / "target" / "openpdf-integration-0.1.0-SNAPSHOT-all.jar"),
                "--job-dir",
                str(root),
                "--font-dir",
                str(experiment.parents[1] / "assets" / "fonts" / "noto-sans"),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        (root / "job.json").write_bytes(original)
        return completed.returncode
    quarantine = root / "quarantine"
    quarantine.mkdir()
    derivative = quarantine / "derivative.pdf"
    if mode == "invalid-pdf":
        derivative.write_bytes(b"%PDF-1.7\ninvalid\n%%EOF")
    elif mode == "copy-source":
        shutil.copyfile(root / "source.pdf", derivative)
    elif mode == "oversize":
        derivative.write_bytes(b"%PDF-" + b"0" * job["limits"]["max_output_bytes"])
    else:
        return 19
    payload = derivative.read_bytes()
    source = (root / "source.pdf").read_bytes()
    status = {
        "schema_version": 1,
        "status": "ok",
        "job_id": job["job_id"],
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "output_sha256": hashlib.sha256(payload).hexdigest(),
        "output_bytes": len(payload),
        "source_pages": job["source"]["page_count"],
        "continuation_pages": 0,
        "output_pages": job["source"]["page_count"],
        "reader_rebuilt": False,
        "incremental": True,
        "render_millis": 1,
    }
    (root / "worker-status.json").write_text(json.dumps(status), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
