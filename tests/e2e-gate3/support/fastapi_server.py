"""Run the built Claros application for the real-browser Gate 3 suite."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from backend.config import Settings
from backend.main import create_app


class Gate3BrowserSettings(Settings):
    """Exercise the production cookie attribute on a trustworthy loopback origin."""

    @property
    def secure_cookie(self) -> bool:
        return True


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    dist_path = repository_root / "dist"
    if not (dist_path / "index.html").is_file():
        raise RuntimeError("Build the Vite application before starting the Gate 3 browser server")

    port = int(_required_environment("CLAROS_GATE3_PORT"))
    if not 1 <= port <= 65_535:
        raise RuntimeError("CLAROS_GATE3_PORT must be a valid TCP port")

    storage_path = Path(_required_environment("CLAROS_GATE3_STORAGE_PATH")).resolve()
    settings = Gate3BrowserSettings(
        environment="test",
        storage_backend="local",
        local_storage_path=storage_path,
        public_origin=f"http://localhost:{port}",
        owner_cookie_name="claros_gate3_owner",
        cookie_secret="gate3-browser-owner-secret-with-sufficient-entropy",  # noqa: S106
        review_token_secret="gate3-browser-review-secret-with-sufficient-entropy",  # noqa: S106
        upload_rate_limit=100,
    )
    app = create_app(settings=settings, dist_path=dist_path)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        workers=1,
        access_log=False,
        server_header=False,
        proxy_headers=False,
        timeout_keep_alive=5,
    )


if __name__ == "__main__":
    main()
