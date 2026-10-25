from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_design_checkpoint import PNG_SIGNATURE, validate_checkpoint


def checkpoint(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "provider": "penpot-cloud",
        "penpot_url": "https://design.example.test/file/cinebridge",
        "desktop_board_id": "desktop-board",
        "mobile_board_id": "mobile-board",
        "desktop_export": "docs/design/desktop.png",
        "mobile_export": "docs/design/mobile.png",
        "workflow_status": "created",
    }
    data.update(overrides)
    return data


class DesignCheckpointTests(unittest.TestCase):
    def test_missing_checkpoint_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            errors = validate_checkpoint(root / "missing.json", root, "created")

        self.assertIn("missing checkpoint metadata", errors[0])

    def test_created_checkpoint_does_not_require_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "checkpoint.json"
            metadata.write_text(json.dumps(checkpoint()), encoding="utf-8")

            created_errors = validate_checkpoint(metadata, root, "created")
            evidence_errors = validate_checkpoint(metadata, root)

        self.assertEqual(created_errors, [])
        self.assertTrue(any("workflow_status" in error for error in evidence_errors))
        self.assertEqual(
            sum("non-empty export" in error for error in evidence_errors),
            2,
        )

    def test_reviewed_checkpoint_records_open_defects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "checkpoint.json"
            metadata.write_text(
                json.dumps(
                    checkpoint(
                        workflow_status="reviewed",
                        review={
                            "defects": [
                                {
                                    "id": "hierarchy-1",
                                    "description": "Top pick is not dominant.",
                                    "status": "open",
                                }
                            ]
                        },
                    )
                ),
                encoding="utf-8",
            )

            errors = validate_checkpoint(metadata, root, "reviewed")

        self.assertEqual(errors, [])

    def test_repaired_checkpoint_rejects_open_defects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "checkpoint.json"
            metadata.write_text(
                json.dumps(
                    checkpoint(
                        workflow_status="repaired",
                        review={
                            "defects": [
                                {
                                    "id": "hierarchy-1",
                                    "description": "Top pick is not dominant.",
                                    "status": "open",
                                }
                            ]
                        },
                    )
                ),
                encoding="utf-8",
            )

            errors = validate_checkpoint(metadata, root, "repaired")

        self.assertIn("repaired checkpoint must not contain open defects", errors)

    def test_real_exports_and_review_link_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exports = root / "docs" / "design"
            exports.mkdir(parents=True)
            (exports / "desktop.png").write_bytes(PNG_SIGNATURE + b"desktop")
            (exports / "mobile.png").write_bytes(PNG_SIGNATURE + b"mobile")
            metadata = exports / "checkpoint.json"
            metadata.write_text(
                json.dumps(
                    checkpoint(
                        workflow_status="ready_for_human_review",
                        review={"defects": []},
                    )
                ),
                encoding="utf-8",
            )

            errors = validate_checkpoint(metadata, root)

        self.assertEqual(errors, [])

    def test_export_outside_repository_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "checkpoint.json"
            metadata.write_text(
                json.dumps(
                    checkpoint(
                        desktop_export="/tmp/desktop.png",
                        mobile_export="../mobile.png",
                    )
                ),
                encoding="utf-8",
            )

            errors = validate_checkpoint(metadata, root, "created")

        self.assertEqual(sum("inside the repository" in error for error in errors), 2)

    def test_named_checkpoint_requires_stable_export_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exports = root / "docs" / "design"
            exports.mkdir(parents=True)
            metadata = exports / "organizer-recommendation.json"
            metadata.write_text(json.dumps(checkpoint()), encoding="utf-8")

            errors = validate_checkpoint(metadata, root, "created")

        self.assertEqual(sum("must be docs/design" in error for error in errors), 2)

    def test_credentialized_penpot_url_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "checkpoint.json"
            metadata.write_text(
                json.dumps(
                    checkpoint(
                        penpot_url="https://design.example.test/file/cinebridge?userToken=secret"
                    )
                ),
                encoding="utf-8",
            )

            errors = validate_checkpoint(metadata, root, "created")

        self.assertTrue(any("credentials" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
