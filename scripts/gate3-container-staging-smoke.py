"""Seed and verify a deployed GCS-backed service across a revision replacement."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHARED_SCRIPT = ROOT / "scripts" / "gate3-container-smoke.py"


def shared_functions() -> dict[str, Any]:
    module = runpy.run_path(str(SHARED_SCRIPT), run_name="gate3_container_shared")
    required = {
        "HttpClient",
        "assert_cross_owner_denied",
        "assert_forwarded_header_does_not_select_rate_limit_key",
        "read_smoke_state",
        "run_full_typed_flow",
        "verify_persisted_flow",
        "write_smoke_state",
    }
    if not required <= set(module):
        raise RuntimeError("container smoke helpers are incomplete")
    return module


def base_url(argument: str | None) -> str:
    value = argument or os.environ.get("CLAROS_STAGING_BASE_URL")
    if not value:
        raise RuntimeError("set CLAROS_STAGING_BASE_URL or pass --base-url")
    return value


def seed(
    url: str,
    state_file: Path,
    shared: dict[str, Any],
    *,
    verify_proxy_identity: bool,
) -> dict[str, object]:
    http_client: Callable[..., Any] = shared["HttpClient"]
    assert_owner: Callable[..., None] = shared["assert_cross_owner_denied"]
    assert_proxy_identity: Callable[..., None] = shared[
        "assert_forwarded_header_does_not_select_rate_limit_key"
    ]
    run_flow: Callable[..., Any] = shared["run_full_typed_flow"]
    write_state: Callable[..., None] = shared["write_smoke_state"]
    client = http_client(url)
    evidence = run_flow(client, secure_cookie=True)
    assert_owner(client, evidence)
    write_state(
        state_file,
        base_url=url,
        owner_cookie=client.owner_cookie_value(),
        evidence=evidence,
    )
    if verify_proxy_identity:
        assert_proxy_identity(url, prior_uploads=len(evidence))
    return {
        "assignments": len(evidence),
        "ownership_isolation": "ok",
        "phase": "seed",
        "placements": sorted(item.expected_placement for item in evidence),
        "proxy_identity": "ok" if verify_proxy_identity else "not_requested",
        "typed_flow": "ok",
    }


def verify(url: str, state_file: Path, shared: dict[str, Any]) -> dict[str, object]:
    http_client: Callable[..., Any] = shared["HttpClient"]
    assert_owner: Callable[..., None] = shared["assert_cross_owner_denied"]
    read_state: Callable[..., Any] = shared["read_smoke_state"]
    verify_flow: Callable[..., None] = shared["verify_persisted_flow"]
    owner_cookie, evidence = read_state(state_file, expected_base_url=url)
    client = http_client(url, owner_cookie=owner_cookie)
    verify_flow(client, evidence)
    assert_owner(client, evidence)
    return {
        "assignments": len(evidence),
        "gcs_revision_persistence": "ok",
        "ownership_isolation": "ok",
        "phase": "verify",
        "placements": sorted(item.expected_placement for item in evidence),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("seed", "verify"))
    parser.add_argument("--base-url")
    parser.add_argument("--state-file", required=True, type=Path)
    parser.add_argument("--verify-proxy-identity", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        url = base_url(arguments.base_url)
        shared = shared_functions()
        if arguments.phase == "seed":
            summary = seed(
                url,
                arguments.state_file,
                shared,
                verify_proxy_identity=arguments.verify_proxy_identity,
            )
        else:
            if arguments.verify_proxy_identity:
                raise RuntimeError("--verify-proxy-identity is valid only during seed")
            summary = verify(url, arguments.state_file, shared)
        print(json.dumps(summary, sort_keys=True))
    except (OSError, RuntimeError) as smoke_error:
        print(f"staging smoke failed: {smoke_error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
