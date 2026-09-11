from __future__ import annotations

import json
import re
import runpy
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import uvicorn

from backend.config import Settings
from backend.main import create_app

ROOT = Path(__file__).resolve().parents[3]
SMOKE_PATH = ROOT / "scripts" / "gate3-container-smoke.py"
RENDER_PATH = ROOT / "scripts" / "gate3-container-render.py"
OWNER_TEST_SECRET = "container-owner-secret-with-sufficient-entropy"  # noqa: S105
REVIEW_TEST_SECRET = "container-review-secret-with-sufficient-entropy"  # noqa: S105


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _start_server(storage_root: Path) -> tuple[uvicorn.Server, threading.Thread, str]:
    port = _free_port()
    origin = f"http://127.0.0.1:{port}"
    dist_path = storage_root.parent / "dist"
    dist_path.mkdir(parents=True, exist_ok=True)
    (dist_path / "index.html").write_text(
        '<!doctype html><html><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    settings = Settings(
        environment="test",
        storage_backend="local",
        local_storage_path=storage_root,
        public_origin=origin,
        cookie_secret=OWNER_TEST_SECRET,
        review_token_secret=REVIEW_TEST_SECRET,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings=settings, dist_path=dist_path),
            host="127.0.0.1",
            port=port,
            access_log=False,
            log_level="critical",
            proxy_headers=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("test HTTP server did not start")
    return server, thread, origin


def _stop_server(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive()


def test_full_http_smoke_survives_process_replacement(tmp_path: Path) -> None:
    shared = runpy.run_path(str(SMOKE_PATH), run_name="gate3_smoke_test")
    storage_root = tmp_path / "objects"
    first_server, first_thread, first_origin = _start_server(storage_root)
    try:
        first_client = shared["HttpClient"](first_origin, allow_http=True)
        evidence = shared["run_full_typed_flow"](first_client, secure_cookie=False)
        owner_cookie = first_client.owner_cookie_value()
        assert {item.expected_placement for item in evidence} == {"inline", "appendix"}
        shared["assert_cross_owner_denied"](first_client, evidence)
        shared["assert_forwarded_header_does_not_select_rate_limit_key"](
            first_origin,
            prior_uploads=len(evidence),
        )
    finally:
        _stop_server(first_server, first_thread)

    second_server, second_thread, second_origin = _start_server(storage_root)
    try:
        second_client = shared["HttpClient"](
            second_origin,
            allow_http=True,
            owner_cookie=owner_cookie,
        )
        shared["verify_persisted_flow"](second_client, evidence)
        shared["assert_cross_owner_denied"](second_client, evidence)
        artifact_dir = tmp_path / "smoke-artifacts"
        artifact_dir.mkdir()
        exports = shared["capture_export_artifacts"](
            second_client,
            evidence,
            artifact_dir,
        )
        assert set(exports) == {"inline", "appendix"}
        assert {path.name for path in artifact_dir.iterdir()} == {
            "completed-appendix.pdf",
            "completed-inline.pdf",
        }
    finally:
        _stop_server(second_server, second_thread)


def test_smoke_state_is_origin_bound_and_excludes_exact_answers(tmp_path: Path) -> None:
    shared = runpy.run_path(str(SMOKE_PATH), run_name="gate3_state_test")
    evidence_type = shared["AssignmentEvidence"]
    evidence = [
        evidence_type("asn_inline", "exp_inline", "inline", "a" * 64, 2),
        evidence_type("asn_appendix", "exp_appendix", "appendix", "b" * 64, 3),
    ]
    state_path = tmp_path / "smoke-state.json"
    shared["write_smoke_state"](
        state_path,
        base_url="https://claros-staging.example",
        owner_cookie="signed-cookie-value",
        evidence=evidence,
    )
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    serialized = json.dumps(raw)
    assert "Mitochondria" not in serialized
    assert "Chlorophyll" not in serialized
    assert all(set(item) >= {"answer_sha256"} for item in raw["assignments"])
    cookie, restored = shared["read_smoke_state"](
        state_path, expected_base_url="https://claros-staging.example"
    )
    assert cookie == "signed-cookie-value"
    assert restored == evidence
    with pytest.raises(RuntimeError, match="different origin"):
        shared["read_smoke_state"](state_path, expected_base_url="https://attacker.example")


def test_container_log_scan_rejects_worksheet_answer_and_cookie_canaries() -> None:
    shared = runpy.run_path(str(SMOKE_PATH), run_name="gate3_log_test")
    canaries = (
        "worksheet question canary",
        "exact answer canary",
        "signed owner cookie canary",
    )

    shared["assert_privacy_safe_log_text"]("bounded event labels only", canaries)
    for canary in canaries:
        with pytest.raises(RuntimeError, match="logs exposed"):
            shared["assert_privacy_safe_log_text"](
                f"safe prefix {canary} safe suffix",
                canaries,
            )


def test_pdf_reopen_check_rejects_an_invalid_pdf_envelope() -> None:
    shared = runpy.run_path(str(SMOKE_PATH), run_name="gate3_pdf_reopen_test")
    with pytest.raises(RuntimeError, match="could not be reopened"):
        shared["verify_pdf_reopens"](b"%PDF-1.7\nnot-a-pdf\n%%EOF", minimum_pages=1)


@pytest.mark.parametrize(
    "url",
    (
        "http://claros.example",
        "https://user:password@claros.example",
        "https://claros.example/path",
        "https://claros.example?cookie=leak",
    ),
)
def test_deployed_smoke_rejects_unsafe_service_urls(url: str) -> None:
    shared = runpy.run_path(str(SMOKE_PATH), run_name="gate3_url_test")
    with pytest.raises(RuntimeError):
        shared["normalize_base_url"](url, allow_http=False)


def test_cloud_run_renderer_accepts_only_digest_and_numeric_secret_versions() -> None:
    renderer = runpy.run_path(str(RENDER_PATH), run_name="gate3_render_test")
    template = (ROOT / "deploy" / "cloud-run.service.template.yaml").read_text(encoding="utf-8")
    valid: dict[str, Any] = {
        "project_id": "claros-prod1",
        "region": "us-central1",
        "service_name": "claros-staging",
        "image_uri": (
            "us-central1-docker.pkg.dev/claros-prod1/cloud-run-source-deploy/claros@sha256:"
            + "a" * 64
        ),
        "gcs_bucket": "claros-private-prod1",
        "public_origin": "https://claros-staging.example",
        "release_sha": "b" * 40,
        "cookie_secret_version": "3",
        "review_secret_version": "4",
        "openai_secret_version": "5",
    }
    rendered = renderer["render_template"](template, **valid)
    assert "{{" not in rendered
    assert "key: latest" not in rendered
    assert 'key: "3"' in rendered
    assert f' image: "{valid["image_uri"]}"'.strip() in rendered

    for field, bad_value in (
        ("image_uri", "us-central1-docker.pkg.dev/claros-prod1/claros/claros:latest"),
        ("cookie_secret_version", "latest"),
        ("public_origin", "http://claros-staging.example"),
        ("service_name", "--project=attacker"),
    ):
        invalid = {**valid, field: bad_value}
        with pytest.raises(ValueError):
            renderer["render_template"](template, **invalid)


def test_terraform_enforces_private_storage_keyless_ci_and_narrow_runtime_access() -> None:
    terraform = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "deploy" / "terraform").glob("*.tf"))
    )
    assert 'public_access_prevention    = "enforced"' in terraform
    assert "uniform_bucket_level_access = true" in terraform
    assert "retention_duration_seconds = 0" in terraform
    assert "age        = 1" in terraform
    assert 'role   = "roles/storage.objectUser"' in terraform
    assert 'role      = "roles/secretmanager.secretAccessor"' in terraform
    assert "assertion.repository_id" in terraform
    assert "assertion.repository_owner_id" in terraform
    assert "assertion.workflow_ref" in terraform
    assert 'role               = "roles/iam.workloadIdentityUser"' in terraform
    assert "service-account-key" not in terraform.lower()
    assert "private_key" not in terraform.lower()


def test_local_container_smoke_applies_runtime_isolation_and_restart_storage() -> None:
    smoke = SMOKE_PATH.read_text(encoding="utf-8")
    assert '"--read-only"' in smoke
    assert '"--cap-drop=ALL"' in smoke
    assert '"--security-opt=no-new-privileges:true"' in smoke
    assert '"--pids-limit=256"' in smoke
    assert '"--memory=2g"' in smoke
    assert '"--cpus=2"' in smoke
    assert '"--entrypoint",\n        "/bin/chown"' in smoke
    assert '"10001:10001"' in smoke
    assert "type=volume,src=" in smoke
    assert "verify_persisted_flow(second_client, evidence)" in smoke
    assert 'docker("logs", container_id' in smoke
    assert smoke.count("assert_container_logs_are_private(") >= 3
    assert "failure-{label}-container.log" in smoke
    container_run = smoke.split("def start_container", 1)[1].split("def assert_image_contract", 1)[
        0
    ]
    assert '"CLAROS_PDF_ENGINE=openpdf"' in container_run
    assert "CLAROS_OPENAI_API_KEY=" not in container_run


def test_workflows_pin_actions_scan_supply_chain_and_promote_one_digest() -> None:
    workflows = list((ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows
    text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)
    action_references = re.findall(r"uses:\s+[^\s]+@([^\s]+)", text)
    assert action_references
    assert all(re.fullmatch(r"[0-9a-f]{40}", revision) for revision in action_references)
    assert "workload_identity_provider" in text
    assert "service_account" in text
    assert "service_account_key" not in text
    assert "${{ secrets." not in text
    assert "scanners: vuln,secret,misconfig" in text
    assert "format: cyclonedx" in text
    assert "provenance: mode=max" in text
    assert "sbom: true" in text
    assert text.count("needs.build.outputs.image_uri") >= 2
    assert "promote_to_production" in text


def test_remote_container_smoke_is_dispatchable_and_persists_safe_artifacts() -> None:
    workflow = (ROOT / ".github" / "workflows" / "gate3-container.yml").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "container-smoke:" in workflow
    assert "scripts/gate3-container-smoke.py" in workflow
    assert "--artifact-dir artifacts/gate3-container-smoke" in workflow
    assert "if: ${{ always() && steps.container_smoke.outcome != 'skipped' }}" in workflow
    assert "actions/upload-artifact@" in workflow
    assert "if-no-files-found: error" in workflow
    assert "gha-creds-*.json" in gitignore
    assert "gha-creds-*.json" in dockerignore


def test_deployment_remains_single_cloud_run_and_gcs_architecture() -> None:
    deployment_text = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (ROOT / "deploy", ROOT / ".github" / "workflows")
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and ".terraform" not in path.parts
        and path.suffix in {".md", ".py", ".tf", ".yaml", ".yml"}
    ).lower()

    assert not (ROOT / "vercel.json").exists()
    assert "vercel blob" not in deployment_text
    assert "@vercel/" not in deployment_text
    assert "cloud run" in deployment_text
    assert "gcs" in deployment_text
