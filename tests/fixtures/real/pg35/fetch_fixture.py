from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://www.gutenberg.org/ebooks/35.epub3.images"
EXPECTED_SHA256 = "5bb9169caeca3866d7e62eac8ea24ba8be98cc6cf7d004acd227ddd12a110126"
DESTINATION = Path(__file__).with_name("pg35-images-3.epub")


def main() -> None:
    request = Request(URL, headers={"User-Agent": "pubparser test fixture fetcher"})
    with urlopen(request, timeout=30) as response:
        data = response.read()

    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(
            "Downloaded Project Gutenberg fixture does not match the recorded sample.\n"
            f"Expected: {EXPECTED_SHA256}\n"
            f"Actual:   {digest}\n"
            "Project Gutenberg may have regenerated the EPUB; review before updating the fixture hash."
        )

    DESTINATION.write_bytes(data)
    print(f"Wrote {DESTINATION} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
