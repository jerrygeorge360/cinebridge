from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_design_checkpoint import validate_checkpoint


class DesignCheckpointTests(unittest.TestCase):
    def test_missing_checkpoint_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            errors = validate_checkpoint(root / "missing.json", root)

        self.assertIn("missing checkpoint metadata", errors[0])

    def test_real_exports_and_review_link_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exports = root / "docs" / "design"
            exports.mkdir(parents=True)
            (exports / "desktop.png").write_bytes(b"desktop")
            (exports / "mobile.png").write_bytes(b"mobile")
            metadata = exports / "checkpoint.json"
            metadata.write_text(
                json.dumps(
                    {
                        "penpot_url": "https://design.example.test/file/cinebridge",
                        "desktop_export": "docs/design/desktop.png",
                        "mobile_export": "docs/design/mobile.png",
                        "review_status": "ready_for_human_review",
                    }
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
                    {
                        "penpot_url": "https://design.example.test/file/cinebridge",
                        "desktop_export": "/tmp/desktop.png",
                        "mobile_export": "../mobile.png",
                        "review_status": "ready_for_human_review",
                    }
                ),
                encoding="utf-8",
            )

            errors = validate_checkpoint(metadata, root)

        self.assertEqual(sum("inside the repository" in error for error in errors), 2)

    def test_named_checkpoint_requires_stable_export_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exports = root / "docs" / "design"
            exports.mkdir(parents=True)
            (exports / "desktop.png").write_bytes(b"desktop")
            (exports / "mobile.png").write_bytes(b"mobile")
            metadata = exports / "organizer-recommendation.json"
            metadata.write_text(
                json.dumps(
                    {
                        "penpot_url": "https://design.example.test/file/cinebridge",
                        "desktop_export": "docs/design/desktop.png",
                        "mobile_export": "docs/design/mobile.png",
                        "review_status": "ready_for_human_review",
                    }
                ),
                encoding="utf-8",
            )

            errors = validate_checkpoint(metadata, root)

        self.assertEqual(sum("must be docs/design" in error for error in errors), 2)


if __name__ == "__main__":
    unittest.main()
