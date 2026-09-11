"""Render the Cloud Run template after validating every substitution."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib import parse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "deploy" / "cloud-run.service.template.yaml"
PROJECT_PATTERN = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]")
REGION_PATTERN = re.compile(r"[a-z]+-[a-z0-9]+[0-9]")
SERVICE_PATTERN = re.compile(r"[a-z]([-a-z0-9]{0,61}[a-z0-9])?")
BUCKET_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]")
RELEASE_PATTERN = re.compile(r"[0-9a-f]{40}")
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
VERSION_PATTERN = re.compile(r"[1-9][0-9]*")
PLACEHOLDER_PATTERN = re.compile(r"\{\{[A-Z_]+\}\}")


def validate_origin(value: str) -> str:
    parsed = parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("--public-origin must be a credential-free HTTPS origin")
    return f"https://{parsed.netloc}"


def validate_version(value: str, name: str) -> str:
    if VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a numeric Secret Manager version")
    return value


def render_template(
    template: str,
    *,
    project_id: str,
    region: str,
    service_name: str,
    image_uri: str,
    gcs_bucket: str,
    public_origin: str,
    release_sha: str,
    cookie_secret_version: str,
    review_secret_version: str,
    openai_secret_version: str,
) -> str:
    validations = (
        (PROJECT_PATTERN, project_id, "--project-id"),
        (REGION_PATTERN, region, "--region"),
        (SERVICE_PATTERN, service_name, "--service-name"),
        (BUCKET_PATTERN, gcs_bucket, "--gcs-bucket"),
        (RELEASE_PATTERN, release_sha, "--release-sha"),
    )
    for pattern, value, name in validations:
        if pattern.fullmatch(value) is None:
            raise ValueError(f"{name} is invalid")
    expected_prefix = f"{region}-docker.pkg.dev/{project_id}/cloud-run-source-deploy/claros@"
    if (
        not image_uri.startswith(expected_prefix)
        or DIGEST_PATTERN.fullmatch(image_uri.removeprefix(expected_prefix)) is None
    ):
        raise ValueError("--image-uri must be the Claros Artifact Registry image by digest")

    substitutions = {
        "{{SERVICE_NAME}}": service_name,
        "{{PROJECT_ID}}": project_id,
        "{{IMAGE_URI}}": image_uri,
        "{{GCS_BUCKET}}": gcs_bucket,
        "{{PUBLIC_ORIGIN}}": validate_origin(public_origin),
        "{{RELEASE_SHA}}": release_sha,
        "{{COOKIE_SECRET_VERSION}}": validate_version(
            cookie_secret_version, "--cookie-secret-version"
        ),
        "{{REVIEW_SECRET_VERSION}}": validate_version(
            review_secret_version, "--review-secret-version"
        ),
        "{{OPENAI_SECRET_VERSION}}": validate_version(
            openai_secret_version, "--openai-secret-version"
        ),
    }
    expected_placeholders = set(PLACEHOLDER_PATTERN.findall(template))
    if expected_placeholders != set(substitutions):
        raise ValueError("Cloud Run template placeholders do not match the renderer contract")
    rendered = template
    for placeholder, value in substitutions.items():
        rendered = rendered.replace(placeholder, value)
    if PLACEHOLDER_PATTERN.search(rendered) or "key: latest" in rendered:
        raise ValueError("Cloud Run template still contains an unresolved or mutable secret")
    return rendered


def write_exclusive(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
        output.write(content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--service-name", required=True)
    parser.add_argument("--image-uri", required=True)
    parser.add_argument("--gcs-bucket", required=True)
    parser.add_argument("--public-origin", required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--cookie-secret-version", required=True)
    parser.add_argument("--review-secret-version", required=True)
    parser.add_argument("--openai-secret-version", required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        template = arguments.template.read_text(encoding="utf-8")
        rendered = render_template(
            template,
            project_id=arguments.project_id,
            region=arguments.region,
            service_name=arguments.service_name,
            image_uri=arguments.image_uri,
            gcs_bucket=arguments.gcs_bucket,
            public_origin=arguments.public_origin,
            release_sha=arguments.release_sha,
            cookie_secret_version=arguments.cookie_secret_version,
            review_secret_version=arguments.review_secret_version,
            openai_secret_version=arguments.openai_secret_version,
        )
        write_exclusive(arguments.output, rendered)
    except (OSError, ValueError) as render_error:
        print(f"Cloud Run render failed: {render_error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
