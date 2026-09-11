"""Build and exercise the Gate 3 image through its public HTTP boundary."""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import io
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

import pikepdf

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INLINE_FIXTURE = REPOSITORY_ROOT / "backend" / "tests" / "corpus" / "01-biology-polished.pdf"
IMAGE_PATTERN = re.compile(
    r"[a-zA-Z0-9][a-zA-Z0-9._/-]*(?::[a-zA-Z0-9][a-zA-Z0-9._-]*)?"
    r"(?:@sha256:[a-fA-F0-9]{64})?"
)
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,96}")
DIGEST_PATTERN = re.compile(r"[a-f0-9]{64}")
SMOKE_TMPFS = "/tmp:rw,noexec,nosuid,nodev,size=64m"  # noqa: S108 - container tmpfs.
CONTAINER_ORIGIN = "http://127.0.0.1:8080"
TEST_COOKIE_SECRET = "gate3-smoke-owner-secret-not-for-production-0001"  # noqa: S105
TEST_REVIEW_SECRET = "gate3-smoke-review-secret-not-for-production-0001"  # noqa: S105
INLINE_ANSWER = "Mitochondria release usable energy from food."
APPENDIX_ANSWER = "Chlorophyll captures sunlight—turning CO₂ and H₂O into stored food energy."
WORKSHEET_TEXT_CANARIES = (
    "1. What organelle releases usable energy from food?",
    "2. Why do plant cells need chloroplasts?",
)


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    def json_object(self) -> dict[str, Any]:
        try:
            value = json.loads(self.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as decode_error:
            raise RuntimeError("API returned malformed JSON") from decode_error
        if not isinstance(value, dict):
            raise RuntimeError("API returned a non-object JSON response")
        return value


@dataclass(frozen=True)
class AssignmentEvidence:
    assignment_id: str
    export_id: str
    expected_placement: str
    answer_sha256: str
    question_count: int

    @classmethod
    def from_dict(cls, value: object) -> AssignmentEvidence:
        if not isinstance(value, dict):
            raise RuntimeError("smoke state assignment entry is invalid")
        expected_keys = {
            "assignment_id",
            "export_id",
            "expected_placement",
            "answer_sha256",
            "question_count",
        }
        if set(value) != expected_keys:
            raise RuntimeError("smoke state assignment fields are invalid")
        assignment_id = value["assignment_id"]
        export_id = value["export_id"]
        placement = value["expected_placement"]
        answer_sha256 = value["answer_sha256"]
        question_count = value["question_count"]
        if (
            not isinstance(assignment_id, str)
            or IDENTIFIER_PATTERN.fullmatch(assignment_id) is None
        ):
            raise RuntimeError("smoke state assignment identifier is invalid")
        if not isinstance(export_id, str) or IDENTIFIER_PATTERN.fullmatch(export_id) is None:
            raise RuntimeError("smoke state export identifier is invalid")
        if placement not in {"inline", "appendix"}:
            raise RuntimeError("smoke state placement is invalid")
        if not isinstance(answer_sha256, str) or DIGEST_PATTERN.fullmatch(answer_sha256) is None:
            raise RuntimeError("smoke state answer digest is invalid")
        if type(question_count) is not int or question_count < 2 or question_count > 40:
            raise RuntimeError("smoke state question count is invalid")
        return cls(
            assignment_id=assignment_id,
            export_id=export_id,
            expected_placement=placement,
            answer_sha256=answer_sha256,
            question_count=question_count,
        )


class HttpClient:
    """Small cookie-aware client that never logs response bodies or credentials."""

    def __init__(
        self,
        base_url: str,
        *,
        origin: str | None = None,
        allow_http: bool = False,
        owner_cookie: str | None = None,
    ) -> None:
        self.base_url = normalize_base_url(base_url, allow_http=allow_http)
        self.origin = normalize_base_url(origin or base_url, allow_http=allow_http)
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = request.build_opener(request.HTTPCookieProcessor(self._cookie_jar))
        self._owner_cookie = (
            validate_cookie_value(owner_cookie) if owner_cookie is not None else None
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        expected_status: int,
        step: str,
        timeout: float = 30,
    ) -> HttpResponse:
        if not path.startswith("/") or path.startswith("//"):
            raise RuntimeError("smoke request path must be absolute and same-origin")
        request_headers = dict(headers or {})
        if self._owner_cookie is not None:
            request_headers["Cookie"] = f"claros_owner={self._owner_cookie}"
        http_request = request.Request(  # noqa: S310 - URL is normalized and path is same-origin.
            f"{self.base_url}{path}",
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with self._opener.open(http_request, timeout=timeout) as response:
                response_body = response.read()
                result = HttpResponse(
                    status=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=response_body,
                )
        except error.HTTPError as http_error:
            response_body = http_error.read(65_537)
            if len(response_body) > 65_536:
                raise RuntimeError(f"{step} returned an oversized error response") from http_error
            result = HttpResponse(
                status=http_error.code,
                headers={key.lower(): value for key, value in http_error.headers.items()},
                body=response_body,
            )
        except (OSError, error.URLError) as network_error:
            raise RuntimeError(f"{step} could not reach the service") from network_error
        if result.status != expected_status:
            raise RuntimeError(f"{step} returned HTTP {result.status}")
        return result

    def mutation_headers(self, content_type: str) -> dict[str, str]:
        return {
            "Content-Type": content_type,
            "Origin": self.origin,
            "Sec-Fetch-Site": "same-origin",
        }

    def post_json(
        self,
        path: str,
        payload: dict[str, object],
        *,
        expected_status: int,
        step: str,
    ) -> HttpResponse:
        return self.request(
            "POST",
            path,
            body=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers=self.mutation_headers("application/json"),
            expected_status=expected_status,
            step=step,
        )

    def owner_cookie_value(self) -> str:
        if self._owner_cookie is not None:
            return self._owner_cookie
        for cookie in self._cookie_jar:
            if cookie.name == "claros_owner":
                return validate_cookie_value(cookie.value)
        raise RuntimeError("assignment creation did not issue the owner cookie")


def normalize_base_url(value: str, *, allow_http: bool) -> str:
    parsed = parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError("service URL must use HTTPS")
    if parsed.scheme == "http" and not (
        allow_http and parsed.hostname in {"127.0.0.1", "localhost"}
    ):
        raise RuntimeError("HTTP is allowed only for an explicit loopback smoke")
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.hostname is None
    ):
        raise RuntimeError(
            "service URL must be an origin without credentials, path, query, or fragment"
        )
    return f"{parsed.scheme}://{parsed.netloc}"


def validate_cookie_value(value: str) -> str:
    if not value or len(value) > 4_096 or any(character in value for character in "\r\n;"):
        raise RuntimeError("smoke owner cookie is invalid")
    return value


def require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"API field {field} is invalid")
    return value


def require_int(value: object, field: str) -> int:
    if type(value) is not int:
        raise RuntimeError(f"API field {field} is invalid")
    return value


def require_list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"API field {field} is invalid")
    return value


def assert_etag(response: HttpResponse, version: int) -> None:
    if response.headers.get("etag") != f'"assignment-version-{version}"':
        raise RuntimeError("versioned API response omitted the expected ETag")


def assert_error_code(response: HttpResponse, expected_code: str) -> None:
    error_payload = response.json_object().get("error")
    if not isinstance(error_payload, dict) or error_payload.get("code") != expected_code:
        raise RuntimeError("API error response omitted the expected stable code")


def verify_pdf_reopens(pdf_bytes: bytes, *, minimum_pages: int) -> int:
    if not pdf_bytes.startswith(b"%PDF-") or b"%%EOF" not in pdf_bytes[-1_024:]:
        raise RuntimeError("export download was not a complete PDF envelope")
    try:
        with pikepdf.Pdf.open(io.BytesIO(pdf_bytes)) as pdf:
            page_count = len(pdf.pages)
    except (OSError, pikepdf.PdfError) as pdf_error:
        raise RuntimeError("export download could not be reopened by pikepdf") from pdf_error
    if page_count < minimum_pages:
        raise RuntimeError("reopened export omitted expected pages")
    return page_count


def assert_health_and_shell(client: HttpClient) -> None:
    health = client.request("GET", "/health", expected_status=200, step="health check")
    if health.json_object() != {"status": "ok"}:
        raise RuntimeError("health response was not the stable contract")
    shell = client.request("GET", "/app", expected_status=200, step="application shell")
    html = shell.body.decode("utf-8")
    if '<div id="root"></div>' not in html:
        raise RuntimeError("FastAPI did not serve the Vite application shell")
    if shell.headers.get("x-content-type-options") != "nosniff":
        raise RuntimeError("application shell omitted security headers")


def assert_owner_cookie(response: HttpResponse, *, secure: bool) -> None:
    set_cookie = response.headers.get("set-cookie", "").lower()
    required = ("claros_owner=", "httponly", "samesite=lax", "path=/")
    if any(item not in set_cookie for item in required):
        raise RuntimeError("owner cookie omitted a required scope or security attribute")
    if ("secure" in set_cookie) is not secure:
        raise RuntimeError("owner cookie Secure policy did not match the environment")


def create_sample_assignment(client: HttpClient, *, secure_cookie: bool) -> dict[str, Any]:
    body = parse.urlencode({"sample_id": "biology-short-answer"}).encode("ascii")
    response = client.request(
        "POST",
        "/api/v2/assignments",
        body=body,
        headers=client.mutation_headers("application/x-www-form-urlencoded"),
        expected_status=201,
        step="sample assignment creation",
        timeout=60,
    )
    assert_owner_cookie(response, secure=secure_cookie)
    payload = response.json_object()
    assert_etag(response, require_int(payload.get("version"), "version"))
    return payload


def multipart_pdf(pdf_path: Path) -> tuple[bytes, str]:
    resolved = pdf_path.resolve()
    corpus_root = (REPOSITORY_ROOT / "backend" / "tests" / "corpus").resolve()
    if resolved.parent != corpus_root or resolved.suffix.lower() != ".pdf":
        raise RuntimeError("inline smoke fixture must be a checked-in gold-corpus PDF")
    pdf_bytes = resolved.read_bytes()
    if not pdf_bytes.startswith(b"%PDF-") or len(pdf_bytes) > 10 * 1024 * 1024:
        raise RuntimeError("inline smoke fixture is not a supported PDF")
    boundary = f"ClarosGate3{secrets.token_hex(12)}"
    disposition = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="{resolved.name}"\r\nContent-Type: application/pdf\r\n\r\n'
    ).encode("ascii")
    body = disposition + pdf_bytes + f"\r\n--{boundary}--\r\n".encode("ascii")
    return body, f"multipart/form-data; boundary={boundary}"


def create_inline_assignment(client: HttpClient, pdf_path: Path) -> dict[str, Any]:
    body, content_type = multipart_pdf(pdf_path)
    response = client.request(
        "POST",
        "/api/v2/assignments",
        body=body,
        headers=client.mutation_headers(content_type),
        expected_status=201,
        step="inline assignment creation",
        timeout=60,
    )
    payload = response.json_object()
    assert_etag(response, require_int(payload.get("version"), "version"))
    return payload


def assert_source_range(client: HttpClient, assignment_id: str) -> None:
    response = client.request(
        "GET",
        f"/api/v2/assignments/{assignment_id}/source",
        headers={"Range": "bytes=0-31"},
        expected_status=206,
        step="authorized source Range read",
    )
    if len(response.body) != 32 or not response.body.startswith(b"%PDF-"):
        raise RuntimeError("source Range response did not return the immutable PDF bytes")
    if not response.headers.get("content-range", "").startswith("bytes 0-31/"):
        raise RuntimeError("source Range response omitted Content-Range")


def complete_one_answer(
    client: HttpClient,
    assignment: dict[str, Any],
    *,
    expected_placement: str,
    answer: str,
    label: str,
) -> AssignmentEvidence:
    assignment_id = require_string(assignment.get("assignment_id"), "assignment_id")
    version = require_int(assignment.get("version"), "version")
    questions = require_list(assignment.get("questions"), "questions")
    if len(questions) < 2 or not isinstance(questions[0], dict):
        raise RuntimeError(f"{label} fixture must expose at least two grounded questions")
    question = questions[0]
    question_id = require_string(question.get("question_id"), "question_id")
    expected_capability = "inline_possible" if expected_placement == "inline" else "appendix_only"
    if question.get("placement_capability") != expected_capability:
        raise RuntimeError(f"{label} fixture did not produce the expected placement capability")

    assert_source_range(client, assignment_id)
    candidate_response = client.post_json(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/candidates",
        {
            "assignment_version": version,
            "text": answer,
            "origin": "student_verbatim",
            "interaction": {"kind": "direct_typed"},
        },
        expected_status=200,
        step=f"{label} candidate creation",
    )
    candidate_payload = candidate_response.json_object()
    candidate = candidate_payload.get("candidate")
    if not isinstance(candidate, dict) or candidate.get("text") != answer:
        raise RuntimeError(f"{label} candidate did not preserve exact text")
    version = require_int(candidate_payload.get("version"), "version")
    assert_etag(candidate_response, version)

    review_response = client.post_json(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/review",
        {
            "assignment_version": version,
            "candidate_id": require_string(candidate.get("candidate_id"), "candidate_id"),
            "candidate_version": require_int(
                candidate.get("candidate_version"), "candidate_version"
            ),
        },
        expected_status=200,
        step=f"{label} exact review creation",
    )
    review = review_response.json_object()
    if review.get("placement") != expected_placement:
        raise RuntimeError(f"{label} exact review returned the wrong placement")
    if not isinstance(review.get("candidate"), dict) or review["candidate"].get("text") != answer:
        raise RuntimeError(f"{label} exact review changed the candidate")
    version = require_int(review.get("version"), "version")
    assert_etag(review_response, version)

    confirm_response = client.post_json(
        f"/api/v2/assignments/{assignment_id}/questions/{question_id}/confirm",
        {
            "assignment_version": version,
            "review_token": require_string(review.get("review_token"), "review_token"),
            "candidate_id": require_string(candidate.get("candidate_id"), "candidate_id"),
            "candidate_version": require_int(
                candidate.get("candidate_version"), "candidate_version"
            ),
        },
        expected_status=200,
        step=f"{label} exact confirmation",
    )
    confirmation = confirm_response.json_object()
    confirmed_answer = confirmation.get("confirmed_answer")
    if not isinstance(confirmed_answer, dict) or confirmed_answer.get("exact_text") != answer:
        raise RuntimeError(f"{label} confirmation changed the approved answer")
    if (
        confirmed_answer.get("placement") != expected_placement
        or confirmation.get("replayed") is not False
    ):
        raise RuntimeError(f"{label} confirmation did not preserve the reviewed placement")
    version = require_int(confirmation.get("version"), "version")
    assert_etag(confirm_response, version)

    export_response = client.post_json(
        f"/api/v2/assignments/{assignment_id}/exports",
        {
            "assignment_version": version,
            "idempotency_key": f"gate3-{label}-partial-export-0001",
        },
        expected_status=201,
        step=f"{label} partial export creation",
    )
    export_payload = export_response.json_object()
    if export_payload.get("status") != "complete":
        raise RuntimeError(f"{label} partial export did not complete")
    export_id = require_string(export_payload.get("export_id"), "export_id")
    assert_etag(export_response, require_int(export_payload.get("version"), "version"))

    status_response = client.request(
        "GET",
        f"/api/v2/assignments/{assignment_id}/exports/{export_id}",
        expected_status=200,
        step=f"{label} export status",
    )
    if status_response.json_object().get("status") != "complete":
        raise RuntimeError(f"{label} export status was not reload-safe")
    download = client.request(
        "GET",
        f"/api/v2/assignments/{assignment_id}/exports/{export_id}/download",
        expected_status=200,
        step=f"{label} authenticated export download",
    )
    verify_pdf_reopens(
        download.body,
        minimum_pages=2 if expected_placement == "appendix" else 1,
    )

    restored = client.request(
        "GET",
        f"/api/v2/assignments/{assignment_id}",
        expected_status=200,
        step=f"{label} assignment reload",
    ).json_object()
    restored_questions = require_list(restored.get("questions"), "questions")
    confirmed_count = sum(
        isinstance(item, dict) and item.get("confirmed_answer") is not None
        for item in restored_questions
    )
    if confirmed_count != 1 or len(restored_questions) != len(questions):
        raise RuntimeError(f"{label} export was not a partial confirmed-answer export")

    return AssignmentEvidence(
        assignment_id=assignment_id,
        export_id=export_id,
        expected_placement=expected_placement,
        answer_sha256=hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        question_count=len(questions),
    )


def run_full_typed_flow(
    client: HttpClient,
    *,
    inline_fixture: Path = INLINE_FIXTURE,
    secure_cookie: bool,
) -> list[AssignmentEvidence]:
    assert_health_and_shell(client)
    appendix_assignment = create_sample_assignment(client, secure_cookie=secure_cookie)
    inline_assignment = create_inline_assignment(client, inline_fixture)
    return [
        complete_one_answer(
            client,
            inline_assignment,
            expected_placement="inline",
            answer=INLINE_ANSWER,
            label="inline",
        ),
        complete_one_answer(
            client,
            appendix_assignment,
            expected_placement="appendix",
            answer=APPENDIX_ANSWER,
            label="appendix",
        ),
    ]


def verify_persisted_flow(client: HttpClient, evidence: list[AssignmentEvidence]) -> None:
    assert_health_and_shell(client)
    if {item.expected_placement for item in evidence} != {"inline", "appendix"}:
        raise RuntimeError("persistence evidence must cover inline and appendix outcomes")
    for item in evidence:
        assignment = client.request(
            "GET",
            f"/api/v2/assignments/{item.assignment_id}",
            expected_status=200,
            step=f"{item.expected_placement} assignment persistence",
        ).json_object()
        questions = require_list(assignment.get("questions"), "questions")
        if len(questions) != item.question_count:
            raise RuntimeError("persisted assignment question count changed")
        confirmed = [
            question.get("confirmed_answer")
            for question in questions
            if isinstance(question, dict) and isinstance(question.get("confirmed_answer"), dict)
        ]
        if len(confirmed) != 1:
            raise RuntimeError("persisted assignment lost its single confirmed answer")
        exact_text = require_string(confirmed[0].get("exact_text"), "exact_text")
        if hashlib.sha256(exact_text.encode("utf-8")).hexdigest() != item.answer_sha256:
            raise RuntimeError("persisted assignment changed exact confirmed text")
        if confirmed[0].get("placement") != item.expected_placement:
            raise RuntimeError("persisted assignment changed reviewed placement")
        assert_source_range(client, item.assignment_id)
        status = client.request(
            "GET",
            f"/api/v2/assignments/{item.assignment_id}/exports/{item.export_id}",
            expected_status=200,
            step=f"{item.expected_placement} persisted export status",
        ).json_object()
        if status.get("status") != "complete":
            raise RuntimeError("persisted export status changed")
        download = client.request(
            "GET",
            f"/api/v2/assignments/{item.assignment_id}/exports/{item.export_id}/download",
            expected_status=200,
            step=f"{item.expected_placement} persisted export download",
        )
        verify_pdf_reopens(
            download.body,
            minimum_pages=2 if item.expected_placement == "appendix" else 1,
        )


def assert_cross_owner_denied(client: HttpClient, evidence: list[AssignmentEvidence]) -> None:
    if not evidence:
        raise RuntimeError("ownership check requires assignment evidence")
    outsider = HttpClient(
        client.base_url,
        origin=client.origin,
        allow_http=client.base_url.startswith("http://"),
    )
    response = outsider.request(
        "GET",
        f"/api/v2/assignments/{evidence[0].assignment_id}",
        expected_status=404,
        step="cross-owner assignment denial",
    )
    assert_error_code(response, "assignment_not_found")


def assert_forwarded_header_does_not_select_rate_limit_key(
    base_url: str,
    *,
    prior_uploads: int,
) -> None:
    upload_limit = 10
    if not 0 <= prior_uploads < upload_limit:
        raise RuntimeError("proxy identity probe received an invalid prior-upload count")
    form_body = parse.urlencode({"sample_id": "missing-proxy-probe"}).encode("ascii")
    allowed_probes = upload_limit - prior_uploads
    allow_http = base_url.startswith("http://")
    for index in range(allowed_probes):
        probe = HttpClient(base_url, allow_http=allow_http)
        headers = probe.mutation_headers("application/x-www-form-urlencoded")
        headers["X-Forwarded-For"] = f"203.0.113.{index + 1}"
        response = probe.request(
            "POST",
            "/api/v2/assignments",
            body=form_body,
            headers=headers,
            expected_status=404,
            step="proxy identity allowed probe",
        )
        assert_error_code(response, "sample_not_found")

    blocked_probe = HttpClient(base_url, allow_http=allow_http)
    blocked_headers = blocked_probe.mutation_headers("application/x-www-form-urlencoded")
    blocked_headers["X-Forwarded-For"] = "198.51.100.254"
    blocked = blocked_probe.request(
        "POST",
        "/api/v2/assignments",
        body=form_body,
        headers=blocked_headers,
        expected_status=429,
        step="proxy identity blocked probe",
    )
    assert_error_code(blocked, "rate_limit_exceeded")


def write_private_bytes(path: Path, value: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as output_file:
        output_file.write(value)


def write_private_json(path: Path, value: dict[str, object]) -> None:
    serialized = json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2).encode("utf-8")
    write_private_bytes(path, serialized + b"\n")


def capture_export_artifacts(
    client: HttpClient,
    evidence: list[AssignmentEvidence],
    artifact_dir: Path,
) -> dict[str, object]:
    exports: dict[str, object] = {}
    for item in evidence:
        download = client.request(
            "GET",
            f"/api/v2/assignments/{item.assignment_id}/exports/{item.export_id}/download",
            expected_status=200,
            step=f"{item.expected_placement} artifact export download",
        )
        page_count = verify_pdf_reopens(
            download.body,
            minimum_pages=2 if item.expected_placement == "appendix" else 1,
        )
        filename = f"completed-{item.expected_placement}.pdf"
        write_private_bytes(artifact_dir / filename, download.body)
        exports[item.expected_placement] = {
            "filename": filename,
            "pages": page_count,
            "sha256": hashlib.sha256(download.body).hexdigest(),
        }
    return exports


def write_smoke_state(
    path: Path,
    *,
    base_url: str,
    owner_cookie: str,
    evidence: list[AssignmentEvidence],
) -> None:
    normalized_url = normalize_base_url(base_url, allow_http=False)
    payload = {
        "schema": 1,
        "base_url": normalized_url,
        "owner_cookie": validate_cookie_value(owner_cookie),
        "assignments": [asdict(item) for item in evidence],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as state_file:
        json.dump(payload, state_file, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        state_file.write("\n")


def read_smoke_state(path: Path, *, expected_base_url: str) -> tuple[str, list[AssignmentEvidence]]:
    try:
        if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise RuntimeError("staging smoke state must be readable only by its owner")
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as state_error:
        raise RuntimeError("staging smoke state is unavailable or malformed") from state_error
    if not isinstance(raw, dict) or set(raw) != {
        "schema",
        "base_url",
        "owner_cookie",
        "assignments",
    }:
        raise RuntimeError("staging smoke state fields are invalid")
    if raw["schema"] != 1:
        raise RuntimeError("staging smoke state schema is unsupported")
    normalized_url = normalize_base_url(expected_base_url, allow_http=False)
    if raw["base_url"] != normalized_url:
        raise RuntimeError("staging smoke state belongs to a different origin")
    owner_cookie = raw["owner_cookie"]
    if not isinstance(owner_cookie, str):
        raise RuntimeError("staging smoke owner cookie is invalid")
    assignments = raw["assignments"]
    if not isinstance(assignments, list) or len(assignments) != 2:
        raise RuntimeError("staging smoke state has incomplete assignment evidence")
    return validate_cookie_value(owner_cookie), [
        AssignmentEvidence.from_dict(item) for item in assignments
    ]


def docker(
    *arguments: str,
    check: bool = True,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("docker")
    if executable is None:
        raise RuntimeError("docker is not installed or is not on PATH")
    return subprocess.run(  # noqa: S603 - fixed Docker executable, no shell.
        [executable, *arguments],
        cwd=REPOSITORY_ROOT,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def require_docker() -> None:
    result = docker("info", "--format", "{{.ServerVersion}}", check=False, timeout=30)
    if result.returncode != 0:
        raise RuntimeError("the Docker daemon is unavailable")


def wait_for_health(container_id: str, timeout_seconds: int = 60) -> str:
    published = docker("port", container_id, "8080/tcp", timeout=30).stdout.strip()
    if not published:
        raise RuntimeError("Docker did not publish container port 8080")
    _host, separator, port_text = published.rpartition(":")
    if separator == "" or not port_text.isdigit():
        raise RuntimeError("Docker returned an invalid port mapping")
    base_url = f"http://127.0.0.1:{int(port_text)}"
    client = HttpClient(base_url, origin=CONTAINER_ORIGIN, allow_http=True)

    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            health = client.request(
                "GET", "/health", expected_status=200, step="container health", timeout=3
            )
            if health.json_object() == {"status": "ok"}:
                return base_url
        except RuntimeError as health_error:
            last_error = health_error
        time.sleep(0.5)
    raise RuntimeError(f"container did not become healthy: {type(last_error).__name__}")


def assert_production_fails_closed(image: str) -> None:
    result = docker(
        "run",
        "--rm",
        "--env",
        "CLAROS_ENVIRONMENT=production",
        "--env",
        "CLAROS_STORAGE_BACKEND=local",
        image,
        check=False,
        timeout=30,
    )
    combined_output = f"{result.stdout}\n{result.stderr}"
    if result.returncode == 0:
        raise RuntimeError("production accepted a local storage configuration")
    if "production requires GCS storage" not in combined_output:
        diagnostic = " ".join(combined_output.split())[-2_000:]
        raise RuntimeError(
            "production rejected local storage with unexpected diagnostics "
            f"(exit={result.returncode}, output={diagnostic!r})"
        )


def start_container(image: str, *, volume_name: str, container_name: str) -> tuple[str, str]:
    container_id = docker(
        "run",
        "--detach",
        "--rm",
        "--name",
        container_name,
        "--read-only",
        "--tmpfs",
        SMOKE_TMPFS,
        "--mount",
        f"type=volume,src={volume_name},dst=/var/lib/claros",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=256",
        "--memory=2g",
        "--cpus=2",
        "--publish",
        "127.0.0.1::8080",
        "--env",
        "CLAROS_ENVIRONMENT=test",
        "--env",
        "CLAROS_STORAGE_BACKEND=local",
        "--env",
        "CLAROS_LOCAL_STORAGE_PATH=/var/lib/claros",
        "--env",
        "CLAROS_PDF_ENGINE=openpdf",
        "--env",
        f"CLAROS_PUBLIC_ORIGIN={CONTAINER_ORIGIN}",
        "--env",
        f"CLAROS_COOKIE_SECRET={TEST_COOKIE_SECRET}",
        "--env",
        f"CLAROS_REVIEW_TOKEN_SECRET={TEST_REVIEW_SECRET}",
        image,
        timeout=30,
    ).stdout.strip()
    if not container_id:
        raise RuntimeError("Docker did not return a container ID")
    return container_id, wait_for_health(container_id)


def assert_image_contract(image: str, container_id: str) -> tuple[str, str]:
    runtime_uid = docker("exec", container_id, "id", "-u", timeout=30).stdout.strip()
    image_user = docker(
        "image", "inspect", image, "--format", "{{.Config.User}}", timeout=30
    ).stdout.strip()
    if runtime_uid != "10001" or image_user != "10001:10001":
        raise RuntimeError("container did not run as the fixed non-root identity")
    image_env = json.loads(
        docker("image", "inspect", image, "--format", "{{json .Config.Env}}", timeout=30).stdout
    )
    forbidden = ("OPENAI_API_KEY=", "CLAROS_OPENAI_API_KEY=", "GOOGLE_APPLICATION_CREDENTIALS=")
    if not isinstance(image_env, list) or any(
        isinstance(item, str) and item.startswith(forbidden) for item in image_env
    ):
        raise RuntimeError("image metadata contains a provider credential")
    return image_user, runtime_uid


def assert_privacy_safe_log_text(log_text: str, canaries: tuple[str, ...]) -> None:
    if any(canary and canary in log_text for canary in canaries):
        raise RuntimeError("container logs exposed a worksheet, answer, or session canary")


def assert_container_logs_are_private(
    container_id: str,
    *,
    owner_cookie: str,
    artifact_path: Path | None = None,
) -> None:
    captured = docker("logs", container_id, check=False, timeout=30)
    if captured.returncode != 0:
        raise RuntimeError("Docker logs could not be captured for privacy inspection")
    log_text = f"{captured.stdout}\n{captured.stderr}"
    assert_privacy_safe_log_text(
        log_text,
        (*WORKSHEET_TEXT_CANARIES, INLINE_ANSWER, APPENDIX_ANSWER, owner_cookie),
    )
    if artifact_path is not None:
        write_private_bytes(artifact_path, log_text.encode("utf-8"))


def prepare_empty_volume(image: str, volume_name: str) -> None:
    docker(
        "run",
        "--rm",
        "--read-only",
        "--network=none",
        "--user",
        "0:0",
        "--cap-drop=ALL",
        "--cap-add=CHOWN",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=64",
        "--mount",
        f"type=volume,src={volume_name},dst=/var/lib/claros",
        "--entrypoint",
        "/bin/chown",
        image,
        "10001:10001",
        "/var/lib/claros",
        timeout=30,
    )


def smoke(image: str, *, artifact_dir: Path | None = None) -> dict[str, object]:
    suffix = secrets.token_hex(6)
    volume_name = f"claros-gate3-{suffix}"
    first_name = f"claros-gate3-first-{suffix}"
    second_name = f"claros-gate3-second-{suffix}"
    docker("volume", "create", volume_name, timeout=30)
    prepare_empty_volume(image, volume_name)
    first_id: str | None = None
    second_id: str | None = None
    owner_cookie = ""
    try:
        first_id, first_url = start_container(
            image, volume_name=volume_name, container_name=first_name
        )
        image_user, runtime_uid = assert_image_contract(image, first_id)
        first_client = HttpClient(first_url, origin=CONTAINER_ORIGIN, allow_http=True)
        evidence = run_full_typed_flow(first_client, secure_cookie=False)
        owner_cookie = first_client.owner_cookie_value()
        assert_cross_owner_denied(first_client, evidence)
        assert_container_logs_are_private(
            first_id,
            owner_cookie=owner_cookie,
            artifact_path=(artifact_dir / "first-container.log") if artifact_dir else None,
        )
        docker("rm", "--force", first_id, check=False, timeout=30)
        first_id = None

        second_id, second_url = start_container(
            image, volume_name=volume_name, container_name=second_name
        )
        second_client = HttpClient(
            second_url,
            origin=CONTAINER_ORIGIN,
            allow_http=True,
            owner_cookie=owner_cookie,
        )
        verify_persisted_flow(second_client, evidence)
        assert_cross_owner_denied(second_client, evidence)
        assert_container_logs_are_private(
            second_id,
            owner_cookie=owner_cookie,
            artifact_path=(artifact_dir / "second-container.log") if artifact_dir else None,
        )
        exports = (
            capture_export_artifacts(second_client, evidence, artifact_dir)
            if artifact_dir is not None
            else {}
        )
        summary: dict[str, object] = {
            "assignments": len(evidence),
            "exports": exports,
            "health": "ok",
            "image": image,
            "image_user": image_user,
            "ownership_isolation": "ok",
            "placements": sorted(item.expected_placement for item in evidence),
            "privacy_logs": "ok",
            "restart_persistence": "ok",
            "runtime_uid": runtime_uid,
            "status": "passed",
            "typed_flow": "ok",
        }
        if artifact_dir is not None:
            write_private_json(artifact_dir / "smoke-result.json", summary)
        print(json.dumps(summary, sort_keys=True))
        return summary
    except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        if artifact_dir is not None:
            for label, container_id in (("first", first_id), ("second", second_id)):
                if container_id is not None:
                    assert_container_logs_are_private(
                        container_id,
                        owner_cookie=owner_cookie,
                        artifact_path=artifact_dir / f"failure-{label}-container.log",
                    )
        raise
    finally:
        if first_id is not None:
            docker("rm", "--force", first_id, check=False, timeout=30)
        if second_id is not None:
            docker("rm", "--force", second_id, check=False, timeout=30)
        docker("volume", "rm", "--force", volume_name, check=False, timeout=30)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="claros-v2:gate3-smoke")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--artifact-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    artifact_dir = arguments.artifact_dir.resolve() if arguments.artifact_dir else None
    try:
        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            if not artifact_dir.is_dir():
                raise RuntimeError("--artifact-dir is not a directory")
        if IMAGE_PATTERN.fullmatch(arguments.image) is None:
            raise RuntimeError("--image is not a valid local image reference")
        require_docker()
        if not arguments.skip_build:
            docker(
                "build",
                "--pull",
                "--tag",
                arguments.image,
                "--build-arg",
                "VCS_REF=gate3-local-smoke",
                "--build-arg",
                "BUILD_DATE=1970-01-01T00:00:00Z",
                ".",
                timeout=1_800,
            )
        assert_production_fails_closed(arguments.image)
        smoke(arguments.image, artifact_dir=artifact_dir)
    except (
        RuntimeError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as smoke_error:
        if artifact_dir is not None and artifact_dir.is_dir():
            result_path = artifact_dir / "smoke-result.json"
            if not result_path.exists():
                write_private_json(
                    result_path,
                    {
                        "error_class": type(smoke_error).__name__,
                        "status": "failed",
                    },
                )
        print(f"container smoke failed: {smoke_error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
