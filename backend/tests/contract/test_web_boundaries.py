from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app

PRODUCTION_COOKIE_SECRET = "production-owner-secret-with-sufficient-entropy"  # noqa: S105
PRODUCTION_REVIEW_SECRET = "production-review-secret-with-sufficient-entropy"  # noqa: S105


def _production_settings() -> Settings:
    return Settings(
        environment="production",
        storage_backend="gcs",
        gcs_bucket="private-bucket",
        public_origin="https://claros.example",
        cookie_secret=PRODUCTION_COOKIE_SECRET,
        review_token_secret=PRODUCTION_REVIEW_SECRET,
    )


def test_foreign_origin_and_cross_site_fetch_metadata_block_api_mutations() -> None:
    app = create_app(settings=Settings(environment="test", public_origin="https://claros.test"))
    client = TestClient(app)

    foreign = client.post(
        "/api/v2/assignments",
        headers={"Origin": "https://attacker.test"},
    )
    fetch_metadata = client.post(
        "/api/v2/assignments",
        headers={"Sec-Fetch-Site": "cross-site"},
    )

    for response in (foreign, fetch_metadata):
        assert response.status_code == 403
        assert response.json() == {
            "error": {
                "code": "origin_forbidden",
                "message": "This request did not come from the Claros application.",
                "recoverable": False,
            }
        }


def test_same_origin_reaches_validation_and_missing_origin_fails_closed() -> None:
    app = create_app(settings=Settings(environment="test", public_origin="https://claros.test"))
    client = TestClient(app)

    same_origin = client.post(
        "/api/v2/assignments",
        headers={"Origin": "https://claros.test"},
    )
    no_origin = client.post("/api/v2/assignments")

    assert same_origin.status_code == 422
    assert no_origin.status_code == 403
    assert no_origin.json()["error"]["code"] == "origin_forbidden"


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "null",
        "https://claros.test/",
        "https://claros.test/app",
        "https://claros.test?next=app",
        "https://claros.test#app",
        "https://student@claros.test",
        "https://claros.test:invalid",
        "https://claros.test:65536",
        "https://claros.test:0",
        "https://[::1]",
        "https://claros.test\\@attacker.test",
        "https://claros.test,https://attacker.test",
        " https://claros.test",
        "https://claros.test ",
        "https://" + ("a" * 506),
    ],
)
def test_malformed_origins_return_the_stable_forbidden_envelope(origin: str) -> None:
    client = TestClient(
        create_app(settings=Settings(environment="test", public_origin="https://claros.test"))
    )

    response = client.post("/api/v2/assignments", headers={"Origin": origin})

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "origin_forbidden",
            "message": "This request did not come from the Claros application.",
            "recoverable": False,
        }
    }


def test_control_character_and_duplicate_origins_fail_closed() -> None:
    client = TestClient(
        create_app(settings=Settings(environment="test", public_origin="https://claros.test"))
    )

    nul = client.post(
        "/api/v2/assignments",
        headers={"Origin": "https://claros.test\x00.attacker.test"},
    )
    duplicate = client.post(
        "/api/v2/assignments",
        headers=[
            ("Origin", "https://claros.test"),
            ("Origin", "https://claros.test"),
        ],
    )

    assert nul.status_code == 403
    assert duplicate.status_code == 403
    assert nul.json()["error"]["code"] == "origin_forbidden"
    assert duplicate.json()["error"]["code"] == "origin_forbidden"


def test_origin_matching_is_canonical_but_rejects_conflicting_fetch_metadata() -> None:
    client = TestClient(
        create_app(settings=Settings(environment="test", public_origin="https://claros.test"))
    )

    equivalent = client.post(
        "/api/v2/assignments",
        headers={"Origin": "HTTPS://CLAROS.TEST:443", "Sec-Fetch-Site": "same-origin"},
    )
    conflicting = client.post(
        "/api/v2/assignments",
        headers={"Origin": "https://claros.test", "Sec-Fetch-Site": "cross-site"},
    )

    assert equivalent.status_code == 422
    assert conflicting.status_code == 403


def test_safe_and_preflight_methods_do_not_run_mutation_origin_check() -> None:
    client = TestClient(
        create_app(settings=Settings(environment="test", public_origin="https://claros.test"))
    )

    get_response = client.get(
        "/api/v2/not-a-route",
        headers={"Origin": "https://attacker.test", "Sec-Fetch-Site": "cross-site"},
    )
    head_response = client.head(
        "/api/v2/not-a-route",
        headers={"Origin": "https://attacker.test", "Sec-Fetch-Site": "cross-site"},
    )
    options_response = client.options(
        "/api/v2/assignments",
        headers={"Origin": "https://attacker.test", "Sec-Fetch-Site": "cross-site"},
    )

    assert get_response.status_code == 404
    assert head_response.status_code == 404
    assert options_response.status_code == 405


def test_host_allowlist_rejects_untrusted_hosts_but_keeps_health_probe_reachable() -> None:
    client = TestClient(
        create_app(settings=Settings(environment="test", public_origin="https://claros.test"))
    )

    trusted = client.get("/api/v2/not-a-route", headers={"Host": "claros.test:443"})
    untrusted = client.get("/api/v2/not-a-route", headers={"Host": "attacker.test"})
    probe = client.get("/health", headers={"Host": "10.0.0.4:8080"})

    assert trusted.status_code == 404
    assert untrusted.status_code == 400
    assert untrusted.text == "Invalid host header"
    assert untrusted.headers["x-content-type-options"] == "nosniff"
    assert probe.status_code == 200
    assert probe.json() == {"status": "ok"}


def test_production_disables_runtime_openapi_and_test_host_fallback() -> None:
    app = create_app(settings=_production_settings(), assignment_service=object())
    client = TestClient(app)
    test_client = TestClient(create_app(settings=Settings(environment="test")))

    schema_response = client.get(
        "/api/v2/openapi.json",
        headers={"Host": "claros.example"},
    )
    default_test_host = client.get("/health/not-the-probe")

    assert schema_response.status_code == 404
    assert default_test_host.status_code == 400
    assert app.openapi()["info"]["title"] == "Claros V2 API"
    assert test_client.get("/api/v2/openapi.json").status_code == 200


def test_security_headers_cover_health_and_errors() -> None:
    client = TestClient(create_app(settings=Settings(environment="test")))

    for response in (client.get("/health"), client.get("/api/v2/not-a-route")):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_static_assets_and_spa_fallback_stay_out_of_api_namespace(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<main>Claros V2</main>", encoding="utf-8")
    (assets / "app.js").write_text("export {};", encoding="utf-8")
    app = create_app(settings=Settings(environment="test"), dist_path=dist)
    client = TestClient(app)

    assert client.get("/").text == "<main>Claros V2</main>"
    assert client.get("/app/assignment_1/review").status_code == 200
    assert client.get("/legacy").status_code == 200
    assert client.get("/assets/app.js").text == "export {};"
    assert client.get("/assets/missing.js").status_code == 404
    missing_api = client.get("/api/v2/not-a-route")
    assert missing_api.status_code == 404
    assert missing_api.json()["error"]["code"] == "route_not_found"


def test_static_path_traversal_does_not_escape_distribution_root(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("index", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("private", encoding="utf-8")
    client = TestClient(create_app(settings=Settings(environment="test"), dist_path=dist))

    response = client.get("/assets/..%2Fsecret.txt")

    assert response.status_code == 404
    assert "private" not in response.text
