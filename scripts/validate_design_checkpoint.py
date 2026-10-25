#!/usr/bin/env python3
"""Validate that a real Penpot review checkpoint has local evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

EXPECTED_EXPORTS = {
    "organizer-recommendation.json": {
        "desktop_export": "docs/design/organizer-recommendation-desktop.png",
        "mobile_export": "docs/design/organizer-recommendation-mobile.png",
    },
    "core-responsive-flows.json": {
        "desktop_export": "docs/design/core-responsive-flows-desktop.png",
        "mobile_export": "docs/design/core-responsive-flows-mobile.png",
    },
}


def validate_checkpoint(metadata_path: Path, repository: Path) -> list[str]:
    root = repository.resolve()
    metadata_path = metadata_path.resolve()
    if root not in metadata_path.parents:
        return ["checkpoint metadata must remain inside the repository"]
    if not metadata_path.is_file():
        return [f"missing checkpoint metadata: {metadata_path}"]
    try:
        data: Any = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid checkpoint metadata: {exc}"]
    if not isinstance(data, dict):
        return ["checkpoint metadata must be a JSON object"]

    errors: list[str] = []
    penpot_url = data.get("penpot_url")
    parsed = urlparse(penpot_url) if isinstance(penpot_url, str) else None
    if not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append("penpot_url must be a complete http(s) URL")
    if data.get("review_status") != "ready_for_human_review":
        errors.append("review_status must be ready_for_human_review")

    expected_exports = EXPECTED_EXPORTS.get(metadata_path.name, {})
    for field in ("desktop_export", "mobile_export"):
        value = data.get(field)
        if not isinstance(value, str) or not value:
            errors.append(f"{field} must name a repository-relative export")
            continue
        if field in expected_exports and value != expected_exports[field]:
            errors.append(f"{field} must be {expected_exports[field]}")
        relative = Path(value)
        candidate = (root / relative).resolve()
        if relative.is_absolute() or root not in candidate.parents:
            errors.append(f"{field} must remain inside the repository")
        elif not candidate.is_file() or candidate.stat().st_size == 0:
            errors.append(f"{field} does not identify a non-empty export")
    return errors


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    if len(arguments) != 1:
        print("usage: validate_design_checkpoint.py METADATA.json", file=sys.stderr)
        return 2
    repository = Path(__file__).resolve().parent.parent
    metadata = (repository / arguments[0]).resolve()
    errors = validate_checkpoint(metadata, repository)
    if errors:
        print("; ".join(errors), file=sys.stderr)
        return 1
    print(f"design checkpoint verified: {metadata.relative_to(repository)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
