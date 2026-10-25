#!/usr/bin/env python3
"""Validate that a real Penpot review checkpoint has local evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

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


PHASES = {"created", "reviewed", "repaired", "evidence"}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def validate_checkpoint(
    metadata_path: Path,
    repository: Path,
    phase: str = "evidence",
) -> list[str]:
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
    if phase not in PHASES:
        return [f"unknown validation phase: {phase}"]

    errors: list[str] = []
    if data.get("provider") != "penpot-cloud":
        errors.append("provider must be penpot-cloud")
    penpot_url = data.get("penpot_url")
    parsed = urlparse(penpot_url) if isinstance(penpot_url, str) else None
    if not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append("penpot_url must be a complete http(s) URL")
    elif parsed.username or parsed.password or any(
        any(word in key.lower() for word in ("token", "secret", "key", "auth"))
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
    ):
        errors.append("penpot_url must not contain credentials or token-like query values")
    for field in ("desktop_board_id", "mobile_board_id"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            errors.append(f"{field} must identify an editable Penpot board")

    expected_status = {
        "created": "created",
        "reviewed": "reviewed",
        "repaired": "repaired",
        "evidence": "ready_for_human_review",
    }[phase]
    if data.get("workflow_status") != expected_status:
        errors.append(f"workflow_status must be {expected_status}")

    if phase in {"reviewed", "repaired", "evidence"}:
        review = data.get("review")
        defects = review.get("defects") if isinstance(review, dict) else None
        if not isinstance(defects, list):
            errors.append("review.defects must be a list")
            defects = []
        for index, defect in enumerate(defects):
            if not isinstance(defect, dict):
                errors.append(f"review.defects[{index}] must be an object")
                continue
            for field in ("id", "description"):
                if not isinstance(defect.get(field), str) or not defect[field].strip():
                    errors.append(f"review.defects[{index}].{field} must be non-empty")
            if defect.get("status") not in {"open", "repaired"}:
                errors.append(
                    f"review.defects[{index}].status must be open or repaired"
                )
        if phase in {"repaired", "evidence"} and any(
            isinstance(defect, dict) and defect.get("status") == "open"
            for defect in defects
        ):
            errors.append(f"{phase} checkpoint must not contain open defects")

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
        elif phase == "evidence":
            if not candidate.is_file() or candidate.stat().st_size == 0:
                errors.append(f"{field} does not identify a non-empty export")
            elif candidate.read_bytes()[: len(PNG_SIGNATURE)] != PNG_SIGNATURE:
                errors.append(f"{field} is not a PNG export")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=sorted(PHASES), default="evidence")
    parser.add_argument("metadata")
    arguments = parser.parse_args(argv if argv is not None else sys.argv[1:])
    repository = Path(__file__).resolve().parent.parent
    metadata = (repository / arguments.metadata).resolve()
    errors = validate_checkpoint(metadata, repository, arguments.phase)
    if errors:
        print("; ".join(errors), file=sys.stderr)
        return 1
    print(f"design checkpoint verified: {metadata.relative_to(repository)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
