"""Path resolution for the local Tesseract executable."""
from __future__ import annotations

import unittest
from pathlib import Path

from cdx_vision import tesseract_cmd


class ResolveTests(unittest.TestCase):
    def test_env_wins_when_file_exists(self) -> None:
        path = Path(__file__).resolve()
        found = tesseract_cmd.resolve_tesseract({"TESSERACT_CMD": str(path)})
        self.assertEqual(found, str(path))

    def test_missing_env_does_not_invent_a_path(self) -> None:
        original = tesseract_cmd.shutil.which
        original_known = tesseract_cmd._KNOWN
        try:
            tesseract_cmd.shutil.which = lambda _name: None
            tesseract_cmd._KNOWN = (Path("C:/does/not/exist/tesseract.exe"),)
            self.assertIsNone(tesseract_cmd.resolve_tesseract({"TESSERACT_CMD": ""}))
        finally:
            tesseract_cmd.shutil.which = original
            tesseract_cmd._KNOWN = original_known


if __name__ == "__main__":
    unittest.main()
