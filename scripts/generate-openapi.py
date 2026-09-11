"""Write or verify the deterministic FastAPI OpenAPI document."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.main import create_app  # noqa: E402

OPENAPI_PATH = REPOSITORY_ROOT / "backend" / "openapi.json"


def rendered_openapi() -> str:
    schema = create_app().openapi()
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rendered = rendered_openapi()
    if args.write:
        OPENAPI_PATH.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"Wrote {OPENAPI_PATH.relative_to(REPOSITORY_ROOT)}")
        return 0

    if not OPENAPI_PATH.exists() or OPENAPI_PATH.read_text(encoding="utf-8") != rendered:
        print("FastAPI OpenAPI drift detected. Run `npm run generate:api`.")
        return 1
    print("FastAPI OpenAPI schema is current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
