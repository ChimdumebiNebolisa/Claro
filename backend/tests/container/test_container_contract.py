from __future__ import annotations

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_dockerfile_has_reproducible_two_stage_least_privilege_runtime() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.startswith(
        "# syntax=docker/dockerfile:1.7@sha256:"
        "a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e"
    )
    assert (
        "FROM node:22.23.2-bookworm-slim@sha256:"
        "83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS web-build"
        in dockerfile
    )
    assert (
        "FROM python:3.11.16-slim-bookworm@sha256:"
        "528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84 AS runtime" in dockerfile
    )
    assert (
        "FROM maven:3.9.11-eclipse-temurin-21@sha256:"
        "6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS openpdf-build"
        in dockerfile
    )
    assert "npm ci --no-audit --no-fund" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert "python -m pip install --require-hashes --only-binary=:all:" in dockerfile
    assert "COPY --from=web-build" in dockerfile
    assert (
        "apt-get install --yes --no-install-recommends fontconfig libfreetype6 qpdf" in dockerfile
    )
    assert "COPY --from=openpdf-build --chown=0:0 /opt/java/openjdk /opt/java/openjdk" in dockerfile
    assert "claros-openpdf-worker-0.1.0-SNAPSHOT-all.jar" in dockerfile
    assert "CLAROS_PDF_ENGINE=openpdf" not in dockerfile
    assert "PYTHONPATH=/app" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert 'ENTRYPOINT ["python", "scripts/gate3-container-entrypoint.py"]' in dockerfile
    assert "--reload" not in dockerfile
    assert "OPENAI_API_KEY=" not in dockerfile
    assert "GOOGLE_APPLICATION_CREDENTIALS=" not in dockerfile


def test_docker_context_excludes_local_secrets_and_generated_state() -> None:
    ignored = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert {
        ".git",
        ".env",
        ".env.*",
        ".venv",
        ".local",
        "node_modules",
        "dist",
        "gha-creds-*.json",
    } <= ignored
    assert {"private-pdfs", "local-corpus", "provider-cache", "artifacts"} <= ignored
    assert "workers/openpdf/target" in ignored


def test_remote_cloud_build_uses_pinned_buildkit_without_credentials() -> None:
    cloud_build = (ROOT / "deploy" / "cloudbuild.yaml").read_text(encoding="utf-8")

    assert "gcr.io/cloud-builders/docker@sha256:" in cloud_build
    assert "DOCKER_BUILDKIT=1" in cloud_build
    assert "${_IMAGE_URI}" in cloud_build
    assert "images:" in cloud_build
    assert "OPENAI_API_KEY" not in cloud_build
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in cloud_build


def test_entrypoint_validates_port_and_never_enables_development_server_modes() -> None:
    module = runpy.run_path(str(ROOT / "scripts" / "gate3-container-entrypoint.py"))
    parse_port = module["parse_port"]
    uvicorn_options = module["uvicorn_options"]

    assert parse_port("8080") == 8080
    for invalid in ("0", "65536", "8080;echo", "-1", ""):
        with pytest.raises(ValueError):
            parse_port(invalid)

    options = uvicorn_options(8080)
    assert options["app"] == "backend.main:app"
    assert options["host"] == "0.0.0.0"  # noqa: S104 - required container bind.
    assert options["port"] == 8080
    assert options["workers"] == 1
    assert options["access_log"] is False
    assert options["proxy_headers"] is False
    assert "reload" not in options


def test_cloud_run_template_freezes_the_p0_envelope_and_secret_boundaries() -> None:
    service = (ROOT / "deploy" / "cloud-run.service.template.yaml").read_text(encoding="utf-8")

    assert "app.kubernetes.io/" not in service
    assert 'release_sha: "{{RELEASE_SHA}}"' in service
    assert 'image: "{{IMAGE_URI}}"' in service
    assert "containerConcurrency: 4" in service
    assert "timeoutSeconds: 300" in service
    assert 'name: CLAROS_REQUEST_TIMEOUT_SECONDS\n              value: "270"' in service
    assert 'autoscaling.knative.dev/minScale: "1"' in service
    assert 'autoscaling.knative.dev/maxScale: "1"' in service
    assert 'cpu: "2"' in service
    assert "memory: 2Gi" in service
    assert service.count("path: /health") == 2
    assert "name: CLAROS_ENVIRONMENT\n              value: production" in service
    assert "name: CLAROS_STORAGE_BACKEND\n              value: gcs" in service
    assert "name: CLAROS_PDF_ENGINE\n              value: current" in service
    assert "name: claros-cookie-secret" in service
    assert "name: claros-review-token-secret" in service
    assert "name: claros-openai-api-key" in service
    assert service.count('key: "{{') == 3
    assert "key: latest" not in service
    assert 'run.googleapis.com/invoker-iam-disabled: "true"' in service
    assert "dev-only-change-me" not in service
    assert "dev-only-review-secret" not in service
