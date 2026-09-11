"""Document-worker fixture that never finishes without parent termination."""

from __future__ import annotations

import time


def main() -> None:
    time.sleep(60)


if __name__ == "__main__":
    main()
