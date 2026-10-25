from __future__ import annotations

import re
import unittest
from pathlib import Path


class RepositoryIndependenceTests(unittest.TestCase):
    def test_product_code_has_no_factory_dependency(self) -> None:
        root = Path(__file__).resolve().parents[1]
        product_files = [
            path
            for area in (root / "web", root / "api")
            for path in area.rglob("*")
            if path.is_file()
            and "node_modules" not in path.parts
            and ".venv" not in path.parts
            and ".next" not in path.parts
        ]
        forbidden = re.compile(
            r"(?:from|import)\s+(?:ai_)?factory\b|ai-factory|/projects/cinebridge\.json"
        )
        violations = [
            str(path.relative_to(root))
            for path in product_files
            if forbidden.search(path.read_text(encoding="utf-8", errors="ignore"))
        ]
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()

