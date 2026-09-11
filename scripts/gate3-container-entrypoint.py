"""Validated, shell-free Uvicorn entrypoint for the production image."""

from __future__ import annotations

import os
import re

import uvicorn

_PORT_PATTERN = re.compile(r"[1-9][0-9]{0,4}")


def parse_port(value: str) -> int:
    """Return a valid TCP port without passing arbitrary text to the process."""
    if _PORT_PATTERN.fullmatch(value) is None:
        raise ValueError("PORT must be an integer from 1 through 65535")
    port = int(value)
    if port > 65_535:
        raise ValueError("PORT must be an integer from 1 through 65535")
    return port


def uvicorn_options(port: int) -> dict[str, object]:
    """Build the single-process Cloud Run options without development flags."""
    return {
        "app": "backend.main:app",
        "host": "0.0.0.0",  # noqa: S104 - Cloud Run requires the container interface.
        "port": port,
        "workers": 1,
        "access_log": False,
        "server_header": False,
        "proxy_headers": False,
        "timeout_keep_alive": 5,
    }


def main() -> None:
    port = parse_port(os.environ.get("PORT", "8080"))
    uvicorn.run(**uvicorn_options(port))


if __name__ == "__main__":
    main()
