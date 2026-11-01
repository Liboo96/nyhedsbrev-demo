from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Lav en lokal browserpreview af et genereret nyhedsbrev")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    html_path = args.run_dir / "newsletter.html"
    image_path = args.run_dir / "infographic.png"
    if not html_path.is_file() or not image_path.is_file():
        parser.error("run_dir skal indeholde newsletter.html og infographic.png")

    args.destination.mkdir(parents=True, exist_ok=True)
    html = html_path.read_text(encoding="utf-8").replace(
        "cid:newsletter-infographic", "infographic.png"
    )
    (args.destination / "newsletter-preview.html").write_text(html, encoding="utf-8")
    (args.destination / "infographic.png").write_bytes(image_path.read_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
